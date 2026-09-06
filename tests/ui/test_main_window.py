import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QDialog

from lithoshape3d.ai.segmentation import MockSegmentationBackend
from lithoshape3d.core.scene.models import ColorStrategy, CompositionMode, ReliefMode, ShapeType
from lithoshape3d.ui import main_window as main_window_module
from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=64, height=48):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_initial_state_has_everything_disabled(main_window):
    assert main_window._state is AppState.NO_IMAGE
    assert not main_window.generate_button.isEnabled()
    assert not main_window.export_button.isEnabled()


def test_loading_image_enables_generate_but_not_export(main_window, tmp_path):
    _load(main_window, tmp_path)

    assert main_window._state is AppState.IMAGE_LOADED
    assert main_window.generate_button.isEnabled()
    assert not main_window.export_button.isEnabled()
    assert "64" in main_window.dimensions_label.text()
    assert "48" in main_window.dimensions_label.text()


def test_ratio_logic_updates_height_display(main_window, tmp_path):
    _load(main_window, tmp_path, width=200, height=100)  # ratio 2:1

    main_window.width_spin.setValue(80.0)

    assert main_window.height_display.text().strip() == "40.0 mm"


def test_param_change_before_generation_stays_image_loaded(main_window, tmp_path):
    _load(main_window, tmp_path)

    main_window.resolution_spin.setValue(0.5)

    assert main_window._state is AppState.IMAGE_LOADED


def test_successful_generation_reaches_mesh_ready_and_enables_export(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.resolution_spin.setValue(3.0)  # grille modeste pour un test rapide

    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    main_window._on_generation_succeeded(mesh)

    assert main_window._state is AppState.MESH_READY
    assert main_window.export_button.isEnabled()
    assert main_window._current_mesh is mesh


def test_param_change_after_mesh_ready_invalidates_it(main_window, tmp_path):
    _load(main_window, tmp_path)
    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)
    assert main_window._state is AppState.MESH_READY

    main_window.max_thickness_spin.setValue(5.0)

    assert main_window._state is AppState.PARAMS_DIRTY
    assert not main_window.export_button.isEnabled()
    # le mesh perime reste en memoire mais ne doit jamais etre exportable
    assert main_window._current_mesh is mesh


def test_generation_failure_reaches_error_state_without_raising(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)
    main_window.min_thickness_spin.setValue(2.0)
    main_window.max_thickness_spin.setValue(2.0)  # invalide : min >= max

    main_window._on_generation_failed("Mesh invalide : max_thickness_mm doit etre superieur")

    assert main_window._state is AppState.ERROR
    assert not main_window.export_button.isEnabled()


def test_export_without_mesh_does_nothing(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    called = []
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: called.append(True) or ("", ""),
    )

    main_window._on_export_clicked()

    assert not called  # jamais atteint : pas de mesh pret


def test_export_writes_a_valid_stl(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.export.stl_export import load_stl
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)

    output_path = tmp_path / "export.stl"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(output_path), "STL (*.stl)"),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    main_window._on_export_clicked()

    assert output_path.exists()
    reloaded = load_stl(output_path)
    assert validate_mesh(reloaded).is_valid


def test_export_shows_a_busy_cursor_while_writing_the_file(main_window, tmp_path, monkeypatch):
    """Retour terrain : l'export (ecriture STL bloquante sur le thread
    principal, pas de worker Qt) ne montrait aucun visuel d'attente --
    verifie que `_busy_export` bascule bien un curseur sablier le temps de
    l'ecriture, puis le restaure (voir `_on_export_clicked`)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    _load(main_window, tmp_path)
    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)

    output_path = tmp_path / "export_busy.stl"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(output_path), "STL (*.stl)"),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    cursor_during_export = []
    original_export_stl = main_window_module.export_stl

    def _spy_export_stl(mesh, path):
        cursor_during_export.append(QApplication.instance().overrideCursor())
        return original_export_stl(mesh, path)

    monkeypatch.setattr("lithoshape3d.ui.main_window.export_stl", _spy_export_stl)

    main_window._on_export_clicked()

    assert cursor_during_export
    assert cursor_during_export[0] is not None
    assert cursor_during_export[0].shape() == Qt.CursorShape.WaitCursor
    assert QApplication.instance().overrideCursor() is None  # restaure apres coup


def test_reset_restores_default_parameters(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.width_spin.setValue(250.0)
    main_window.invert_checkbox.setChecked(True)

    main_window._on_reset_clicked()

    assert main_window.width_spin.value() == 100.0
    assert main_window.invert_checkbox.isChecked() is False


def test_end_to_end_generate_via_thread_pool(qapp, main_window, tmp_path, monkeypatch):
    """Verifie le cablage reel worker -> QThreadPool -> signal -> UI thread."""
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)
    main_window.resolution_spin.setValue(3.0)

    main_window._on_generate_clicked()
    assert main_window._state is AppState.GENERATING
    assert not main_window.generate_button.isEnabled()

    deadline = time.monotonic() + 10
    while main_window._state is AppState.GENERATING and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert main_window._state is AppState.MESH_READY
    assert main_window.export_button.isEnabled()
    assert main_window._current_mesh is not None


def test_switching_zone_does_not_corrupt_relief_or_composition_mode(main_window, tmp_path):
    """Regression : passer d'une zone a l'autre dans le panneau ne doit pas
    ecraser relief_mode/composition_mode de la zone qui vient d'etre chargee
    avec une valeur perimee de l'autre combo (bug de signaux non bloques)."""
    _load(main_window, tmp_path)
    zone_a = main_window._active_zone()
    zone_a.relief_mode = ReliefMode.LITHOPHANE
    zone_a.composition_mode = CompositionMode.BASE

    main_window._on_new_zone_clicked()
    zone_b = main_window._active_zone()
    zone_b.relief_mode = ReliefMode.SOLID
    zone_b.composition_mode = CompositionMode.ADD
    main_window._refresh_zones_list()

    main_window.zones_list.setCurrentRow(0)
    main_window.zones_list.setCurrentRow(1)

    assert zone_a.relief_mode is ReliefMode.LITHOPHANE
    assert zone_a.composition_mode is CompositionMode.BASE
    assert zone_b.relief_mode is ReliefMode.SOLID
    assert zone_b.composition_mode is CompositionMode.ADD


def test_lithogift_bambu_mono_preset_sets_width_and_thickness_for_the_frame_slot(main_window, tmp_path):
    """Preset boitier tiers (hugo.workshop, MakerWorld #1036463) : la fente
    du cadre attend 3.2mm max pour une litho mono -- doit rester exact."""
    _load(main_window, tmp_path)
    main_window.width_spin.setValue(999.0)  # valeur witness, doit etre ecrasee par le preset

    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    assert main_window.width_spin.value() == 140.0
    assert main_window.max_thickness_spin.value() == 3.2
    assert main_window.min_thickness_spin.value() == 0.8
    assert main_window.resolution_spin.value() == 0.2


def test_quality_only_presets_do_not_touch_width(main_window, tmp_path):
    """Les presets qualite existants (Moyen/Fin/Brouillon) n'ont pas de
    width_mm -- ne doivent jamais toucher la largeur deja choisie par
    l'utilisateur (comportement inchange, non-regression)."""
    _load(main_window, tmp_path)
    main_window.width_spin.setValue(77.0)

    main_window._apply_preset("Moyen (standard)")

    assert main_window.width_spin.value() == 77.0


def _active_workflow_steps(main_window) -> list[str]:
    return [
        button.text()
        for button in main_window._workflow_step_buttons
        if button.property("active")
    ]


def test_workflow_indicator_highlights_image_step_before_any_image(main_window):
    assert main_window._state is AppState.NO_IMAGE
    assert _active_workflow_steps(main_window) == ["Image"]


def test_workflow_indicator_highlights_zones_and_geometry_after_loading_image(main_window, tmp_path):
    _load(main_window, tmp_path)

    assert set(_active_workflow_steps(main_window)) == {"Zones", "Geometrie / Backlight"}


def test_workflow_indicator_highlights_apercu_and_export_once_mesh_ready(qapp, main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_generate_clicked()
    deadline = time.monotonic() + 10
    while main_window._state is AppState.GENERATING and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert main_window._state is AppState.MESH_READY
    assert set(_active_workflow_steps(main_window)) == {"Apercu", "Export"}


def _workflow_button(main_window, name: str):
    return next(b for b in main_window._workflow_step_buttons if b.text() == name)


def test_workflow_tab_image_opens_the_image_chooser(main_window, monkeypatch):
    """Onglet cliquable (retour terrain) : "Image" doit vraiment declencher
    l'ouverture du selecteur de fichier, pas juste illustrer l'etape."""
    called = {}
    monkeypatch.setattr(main_window, "_choose_image", lambda: called.setdefault("done", True))

    _workflow_button(main_window, "Image").click()

    assert called.get("done") is True


def test_workflow_tab_geometrie_scrolls_params_panel_to_composition(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    called = {}
    monkeypatch.setattr(
        main_window.params_scroll_area,
        "ensureWidgetVisible",
        lambda widget: called.setdefault("widget", widget),
    )

    _workflow_button(main_window, "Geometrie / Backlight").click()

    assert called.get("widget") is main_window.composition_group


def test_workflow_tab_apercu_triggers_generation_when_not_ready(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    called = {}
    monkeypatch.setattr(main_window, "_on_generate_clicked", lambda: called.setdefault("done", True))

    _workflow_button(main_window, "Apercu").click()

    assert called.get("done") is True


def test_workflow_tab_export_triggers_export_when_mesh_ready(qapp, main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    main_window._on_generate_clicked()
    deadline = time.monotonic() + 10
    while main_window._state is AppState.GENERATING and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert main_window._state is AppState.MESH_READY

    called = {}
    monkeypatch.setattr(main_window, "_on_export_clicked", lambda: called.setdefault("done", True))

    _workflow_button(main_window, "Export").click()

    assert called.get("done") is True


def test_workflow_tab_export_shows_status_message_when_not_ready(main_window):
    assert main_window._state is AppState.NO_IMAGE

    _workflow_button(main_window, "Export").click()

    assert "Generez d'abord" in main_window.statusBar().currentMessage()


def test_remove_background_auto_button_enabled_with_image_regardless_of_sam2_backend(
    main_window, tmp_path
):
    main_window._segmentation_backend = None
    _load(main_window, tmp_path)

    assert main_window.remove_background_button.isEnabled()


def test_remove_background_auto_button_disabled_without_image(main_window):
    main_window._set_state(main_window._state)

    assert not main_window.remove_background_button.isEnabled()


def test_remove_background_manual_button_disabled_without_backend_even_with_image(
    main_window, tmp_path
):
    main_window._segmentation_backend = None
    _load(main_window, tmp_path)

    assert not main_window.remove_background_manual_button.isEnabled()


def test_remove_background_manual_button_disabled_without_image_even_with_backend(main_window):
    main_window._segmentation_backend = MockSegmentationBackend()
    main_window._set_state(main_window._state)

    assert not main_window.remove_background_manual_button.isEnabled()


def test_remove_background_manual_button_enabled_with_image_and_backend(main_window, tmp_path):
    main_window._segmentation_backend = MockSegmentationBackend()
    _load(main_window, tmp_path)

    assert main_window.remove_background_manual_button.isEnabled()


def test_remove_background_manual_exports_rgba_png_from_alpha_mask(main_window, tmp_path, monkeypatch):
    from PIL import Image

    main_window._segmentation_backend = MockSegmentationBackend()
    image_path = _load(main_window, tmp_path)
    width, height = Image.open(image_path).size

    alpha_mask = np.zeros((height, width), dtype=np.float32)
    alpha_mask[height // 2, width // 2] = 1.0

    class _FakeDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

        def resulting_alpha_mask(self):
            return alpha_mask

    monkeypatch.setattr(main_window_module, "MaskEditorDialog", _FakeDialog)

    out_path = tmp_path / "gradient-detoure.png"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "PNG (*.png)"),
    )

    main_window._on_remove_background_manual_clicked()

    assert out_path.exists()
    exported = Image.open(out_path)
    assert exported.mode == "RGBA"
    exported_alpha = np.asarray(exported)[:, :, 3]
    assert exported_alpha[height // 2, width // 2] == 255
    assert exported_alpha[0, 0] == 0


def test_remove_background_auto_downloaded_model_runs_directly_and_exports(
    main_window, tmp_path, monkeypatch, qapp
):
    from PIL import Image

    image_path = _load(main_window, tmp_path)
    width, height = Image.open(image_path).size

    monkeypatch.setattr("lithoshape3d.ai.background_removal.is_downloaded", lambda: True)

    alpha_mask = np.zeros((height, width), dtype=np.float32)
    alpha_mask[height // 2, width // 2] = 1.0
    monkeypatch.setattr(
        "lithoshape3d.ai.background_removal.remove_background", lambda image: alpha_mask
    )

    out_path = tmp_path / "gradient-detoure-auto.png"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "PNG (*.png)"),
    )

    main_window._on_remove_background_auto_clicked()

    deadline = time.monotonic() + 10
    while not out_path.exists() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert out_path.exists()
    exported = Image.open(out_path)
    assert exported.mode == "RGBA"
    exported_alpha = np.asarray(exported)[:, :, 3]
    assert exported_alpha[height // 2, width // 2] == 255
    assert exported_alpha[0, 0] == 0
    assert main_window.remove_background_button.isEnabled()


def test_remove_background_as_shape_button_enabled_with_image(main_window, tmp_path):
    assert not main_window.remove_background_as_shape_button.isEnabled()
    _load(main_window, tmp_path)
    assert main_window.remove_background_as_shape_button.isEnabled()


def test_remove_background_as_shape_shortcut_sets_shape_to_image_without_a_dialog(
    main_window, tmp_path, monkeypatch, qapp
):
    """Reproduit le raccourci demande : detourer automatiquement puis
    decouper directement la piece a la silhouette du sujet, sans passer
    par une boite de dialogue d'export ni un reimport manuel."""
    from PIL import Image

    image_path = _load(main_window, tmp_path)
    width, height = Image.open(image_path).size

    monkeypatch.setattr("lithoshape3d.ai.background_removal.is_downloaded", lambda: True)

    alpha_mask = np.zeros((height, width), dtype=np.float32)
    alpha_mask[height // 2, width // 2] = 1.0
    monkeypatch.setattr("lithoshape3d.ai.background_removal.remove_background", lambda image: alpha_mask)

    save_dialog_called = []
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: save_dialog_called.append(True) or ("", ""),
    )

    main_window._on_remove_background_as_shape_clicked()

    expected_path = Path(image_path).with_name(f"{Path(image_path).stem}-detoure.png")
    deadline = time.monotonic() + 10
    while not expected_path.exists() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert expected_path.exists()  # ecrit directement, sans dialogue
    assert not save_dialog_called
    shape = main_window._project.scene.shape
    assert shape.shape_type == ShapeType.IMAGE
    assert shape.source_image_path == str(expected_path)
    assert main_window.remove_background_as_shape_button.isEnabled()

    shape_mask = main_window._current_shape_mask()
    assert shape_mask is not None
    assert shape_mask.any()  # une silhouette non vide a bien ete decoupee

    # Regression : le raccourci basculait bien la Shape en ShapeType.IMAGE,
    # mais le mode de generation par defaut ("Zone active") ignore
    # completement la Shape Composer (seul le mode "Composition" la respecte,
    # voir _on_generate_clicked) -- sans ce bascule automatique, "Generer"
    # produisait toujours un rectangle plein malgre la silhouette decoupee.
    assert main_window.view_composition_button.isChecked()


def test_remove_background_auto_offers_download_when_model_missing(
    main_window, tmp_path, monkeypatch
):
    _load(main_window, tmp_path)
    monkeypatch.setattr(
        "lithoshape3d.ai.background_removal.is_downloaded", lambda: False
    )
    asked = {}
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *args, **kwargs: asked.setdefault("called", True)
        or main_window_module.QMessageBox.StandardButton.No,
    )

    main_window._on_remove_background_auto_clicked()

    assert asked.get("called") is True


def _select_shape_type(main_window, shape_type):
    index = main_window.shape_type_combo.findData(shape_type)
    main_window.shape_type_combo.setCurrentIndex(index)


def test_offset_spins_visible_only_for_text_shape(main_window):
    # isVisible() exige toute la chaine de fenetres affichee (jamais le cas
    # en test headless) -- isHidden() reflete le flag setVisible() applique
    # par _update_shape_visibility(), independamment de l'affichage reel.
    _select_shape_type(main_window, ShapeType.TEXT)
    assert not main_window.shape_offset_x_spin.isHidden()
    assert not main_window.shape_offset_y_spin.isHidden()

    _select_shape_type(main_window, ShapeType.RECTANGLE)
    assert main_window.shape_offset_x_spin.isHidden()
    assert main_window.shape_offset_y_spin.isHidden()


def test_selecting_a_non_rectangle_shape_switches_to_composition_mode(main_window):
    """Regression : le mode "Zone active" (par defaut) ignore la Shape
    Composer -- toute forme non-rectangulaire (Cercle, Coeur, Etoile, Texte,
    Image/SVG importee...) doit forcer le mode "Composition", seul mode qui
    la respecte reellement pendant la generation (_on_generate_clicked)."""
    assert main_window.view_zone_button.isChecked()

    _select_shape_type(main_window, ShapeType.HEART)
    assert main_window.view_composition_button.isChecked()

    main_window.view_zone_button.setChecked(True)
    _select_shape_type(main_window, ShapeType.RECTANGLE)
    assert main_window.view_zone_button.isChecked()


def test_on_shape_changed_writes_offsets_as_fractions(main_window):
    _select_shape_type(main_window, ShapeType.TEXT)
    main_window.shape_offset_x_spin.setValue(15.0)
    main_window.shape_offset_y_spin.setValue(-30.0)

    assert main_window._project.scene.shape.offset_x == pytest.approx(0.15)
    assert main_window._project.scene.shape.offset_y == pytest.approx(-0.30)


def test_arrow_key_nudges_text_offset_and_updates_spinboxes(main_window):
    _select_shape_type(main_window, ShapeType.TEXT)
    main_window.shape_offset_x_spin.setValue(0.0)
    main_window.shape_offset_y_spin.setValue(0.0)

    main_window._on_preview_arrow_key(1, 0)

    shape = main_window._project.scene.shape
    assert shape.offset_x == pytest.approx(0.01)
    assert shape.offset_y == pytest.approx(0.0)
    assert main_window.shape_offset_x_spin.value() == pytest.approx(1.0)


def test_arrow_key_is_a_no_op_outside_text_shape(main_window):
    _select_shape_type(main_window, ShapeType.RECTANGLE)

    main_window._on_preview_arrow_key(1, 1)

    shape = main_window._project.scene.shape
    assert shape.offset_x == 0.0
    assert shape.offset_y == 0.0


def test_shape_to_backlight_button_hidden_outside_text_shape(main_window):
    _select_shape_type(main_window, ShapeType.TEXT)
    assert not main_window.shape_to_backlight_button.isHidden()

    _select_shape_type(main_window, ShapeType.RECTANGLE)
    assert main_window.shape_to_backlight_button.isHidden()


def test_shape_to_backlight_creates_a_red_insert_zone_from_the_text_mask(main_window, tmp_path):
    import dataclasses

    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.geometry.shape import build_shape_mask

    _load(main_window, tmp_path)
    _select_shape_type(main_window, ShapeType.TEXT)
    main_window.shape_text_edit.setText("HI")
    main_window.shape_text_edit.editingFinished.emit()
    zones_before = len(main_window._project.scene.zones)
    active_zone_id_before = main_window._project.scene.active_zone_id
    text_shape_before = dataclasses.replace(main_window._project.scene.shape)
    geometry_before = main_window._current_geometry_parameters()

    main_window._on_shape_to_backlight_clicked()

    scene = main_window._project.scene
    assert len(scene.zones) == zones_before + 1
    new_zone = scene.zones[-1]
    assert new_zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT
    assert new_zone.material.color == (1.0, 0.0, 0.0)
    # La zone active ne doit PAS basculer sur la nouvelle zone : sinon un
    # simple clic sur "Generer" en mode "Zone active" (coche par defaut) ne
    # produirait plus que cette zone isolee, faisant "disparaitre" la
    # lithophanie de base (regression constatee et corrigee).
    assert scene.active_zone_id == active_zone_id_before
    # Le mode "Composition" doit etre active : c'est le seul qui compose
    # reellement panneau + insert Backlight.
    assert main_window.view_composition_button.isChecked()

    mask = main_window._zone_masks[new_zone.id]
    assert mask.any()
    rows, cols = grid_dimensions(geometry_before)
    expected = build_shape_mask(text_shape_before, rows, cols).astype(np.float32)
    np.testing.assert_array_equal(mask, expected)

    # La Forme redevient un rectangle normal : le texte est maintenant un
    # insert de zone, pas la silhouette globale du panneau.
    assert scene.shape.shape_type is ShapeType.RECTANGLE
    assert main_window.shape_type_combo.currentData() is ShapeType.RECTANGLE


class _FakeCadrageDialog:
    """Simule CadrageDialog : accepte immediatement avec le transform initial
    recu, sans jamais afficher de vraie fenetre (tests headless)."""

    def __init__(self, source_array, shape_mask, initial_transform, parent=None):
        self.transform = initial_transform

    def setWindowTitle(self, _title):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


class _FakeCadrageDialogRejected(_FakeCadrageDialog):
    def exec(self):
        return QDialog.DialogCode.Rejected


def test_lithogift_preset_sets_locked_aspect_and_shows_crop_button(main_window):
    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    assert main_window._locked_aspect_mm == (140.0, 104.0)
    assert not main_window.crop_to_locked_aspect_button.isHidden()


def test_quality_preset_clears_locked_aspect(main_window):
    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    main_window._apply_preset("Fin")

    assert main_window._locked_aspect_mm is None
    assert main_window.crop_to_locked_aspect_button.isHidden()


def test_lithogift_preset_with_square_photo_triggers_real_crop_to_140x104(
    main_window, tmp_path, monkeypatch
):
    from lithoshape3d.core.geometry.heightmap import height_mm_from_aspect_ratio

    # Photo carree : ratio tres eloigne de 140:104 (~1.346:1), declenche a
    # coup sur le recadrage (pas de zone grise pres de la tolerance 1%).
    _load(main_window, tmp_path, width=200, height=200)
    monkeypatch.setattr("lithoshape3d.ui.cadrage_dialog.CadrageDialog", _FakeCadrageDialog)

    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    new_path = Path(main_window._image_path)
    assert new_path.name.endswith("-140x104.png")
    assert new_path.exists()
    height_mm = height_mm_from_aspect_ratio(
        140.0, main_window._image_width_px, main_window._image_height_px
    )
    assert height_mm == pytest.approx(104.0, abs=0.5)


def test_lithogift_crop_cancelled_leaves_image_untouched(main_window, tmp_path, monkeypatch):
    original_path = _load(main_window, tmp_path, width=200, height=200)
    monkeypatch.setattr("lithoshape3d.ui.cadrage_dialog.CadrageDialog", _FakeCadrageDialogRejected)

    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    assert main_window._image_path == str(original_path)


def test_loading_a_different_photo_after_preset_retriggers_crop(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.cadrage_dialog.CadrageDialog", _FakeCadrageDialog)
    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")  # sans image chargee
    assert main_window._locked_aspect_mm == (140.0, 104.0)

    _load(main_window, tmp_path, width=200, height=200)  # ordre inverse

    new_path = Path(main_window._image_path)
    assert new_path.name.endswith("-140x104.png")


def test_crop_to_locked_aspect_updates_the_zone_geometry_height_not_just_the_display(
    main_window, tmp_path, monkeypatch
):
    """Reproduit le bug terrain : apres le recadrage, le panneau Geometrie
    affichait bien 140x104mm (recalcule en direct depuis les spinboxes +
    `_image_width_px/_image_height_px`), mais `Zone.geometry_params.height_mm`
    -- la valeur reellement utilisee par la composition/generation -- restait
    figee sur l'ancienne hauteur (celle de la photo carree d'avant recadrage),
    puisque recharger une nouvelle image ne declenche aucun `valueChanged` sur
    `width_spin` (valeur deja a 140) et donc jamais `_on_param_changed`."""
    _load(main_window, tmp_path, width=200, height=200)
    monkeypatch.setattr("lithoshape3d.ui.cadrage_dialog.CadrageDialog", _FakeCadrageDialog)

    main_window._apply_preset("LithoGift Bambu Mono (140x104mm)")

    zone = main_window._active_zone()
    assert zone.geometry_params.width_mm == pytest.approx(140.0)
    assert zone.geometry_params.height_mm == pytest.approx(104.0, abs=0.5)


def test_loading_an_image_resyncs_height_on_every_zone_not_just_the_active_one(
    main_window, tmp_path
):
    """Meme invariant ("hauteur toujours verrouillee au ratio de la photo")
    mais isole du flux preset/crop : une zone non-active (ex. cree pendant
    qu'une autre zone etait selectionnee, comme 'Envoyer vers une zone
    Backlight...') ne doit pas non plus garder une `height_mm` perimee des
    qu'une nouvelle photo est chargee -- `_on_param_changed` n'ecrit que sur
    la zone active, donc seul `_load_image` peut garantir cet invariant pour
    toutes les zones."""
    from lithoshape3d.core.scene.models import Zone

    _load(main_window, tmp_path, width=100, height=100)
    base_zone = main_window._active_zone()

    other_zone = Zone(name="Texte LOVE", geometry_params=main_window._current_geometry_parameters())
    main_window._project.scene.zones.append(other_zone)
    main_window._project.scene.active_zone_id = other_zone.id

    landscape_path = make_gradient_image(tmp_path / "landscape.png", width=700, height=520)
    main_window._load_image(str(landscape_path))

    from lithoshape3d.core.geometry.heightmap import height_mm_from_aspect_ratio

    assert base_zone.geometry_params.height_mm == pytest.approx(
        height_mm_from_aspect_ratio(base_zone.geometry_params.width_mm, 700, 520), abs=1e-6
    )
    assert other_zone.geometry_params.height_mm == pytest.approx(
        height_mm_from_aspect_ratio(other_zone.geometry_params.width_mm, 700, 520), abs=1e-6
    )


def _generate_ready_mesh(main_window):
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    params = main_window._current_geometry_parameters()
    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)


def test_export_blocked_without_a_valid_license(main_window, tmp_path, monkeypatch):
    """Reproduit le blocage reel : sans licence, `_on_export_clicked` doit
    ouvrir la boite de dialogue de licence et ne jamais atteindre le
    QFileDialog d'export -- voir `_ensure_licensed_for_export`."""
    monkeypatch.setattr("lithoshape3d.ui.license_dialog.is_licensed", lambda: False)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)
    opened = []
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.MainWindow._open_license_dialog",
        lambda self: opened.append(True),
    )
    save_dialog_called = []
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: save_dialog_called.append(True) or ("", ""),
    )
    _load(main_window, tmp_path)
    _generate_ready_mesh(main_window)

    main_window._on_export_clicked()

    assert opened == [True]
    assert not save_dialog_called


def test_export_proceeds_once_licensed(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.license_dialog.is_licensed", lambda: True)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)
    _load(main_window, tmp_path)
    _generate_ready_mesh(main_window)

    output_path = tmp_path / "export_licensed.stl"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(output_path), "STL (*.stl)"),
    )

    main_window._on_export_clicked()

    assert output_path.exists()
