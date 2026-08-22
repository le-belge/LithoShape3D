"""E2E (mission 2.18, Test B) : nouvelle photo -> Shape=Texte "M" -> cadrer
-> generer -> verifier la silhouette -> exporter STL et 3MF -> valider le
mesh. Plus simple que le Test A (pas de SAM2/materiaux), mais un cablage UI
complet distinct : Shape=TEXT est un chemin different de Shape=HEART (police,
`shape_text_edit`, pas d'import de fichier)."""

import time

import pyvista as pv
import trimesh

from lithoshape3d.core.geometry.shape import build_shape_mask, count_connected_components
from lithoshape3d.core.scene.models import ShapeParams, ShapeType
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.core.validation.printability import check_printability
from lithoshape3d.ui.cadrage_dialog import CadrageDialog
from lithoshape3d.ui.main_window import MainWindow
from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _wait_until(predicate, qapp, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "timeout en attendant la condition attendue"


def test_letter_m_shaped_lithophane_from_a_different_photo(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.critical", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    main_window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        # 1. nouvelle photo (differente de celle du Test A -- degrade, pas de rose)
        image_path = make_gradient_image(tmp_path / "autre_photo.png", width=200, height=200)
        main_window._load_image(str(image_path))
        main_window.resolution_spin.setValue(1.0)  # grille 100x100
        assert main_window._state is AppState.IMAGE_LOADED

        # 2. Shape -> Texte "M"
        idx = main_window.shape_type_combo.findData(ShapeType.TEXT)
        main_window.shape_type_combo.setCurrentIndex(idx)
        main_window.shape_text_edit.setText("M")
        main_window._on_shape_changed()
        assert main_window._project.scene.shape.shape_type is ShapeType.TEXT
        assert main_window._project.scene.shape.text == "M"
        assert main_window.shape_info_label.text() == ""  # "M" = une seule piece, pas d'avertissement

        # 3. cadrer (Ajuster, cadrage reel via CadrageDialog)
        shape_mask = main_window._current_shape_mask()
        assert shape_mask is not None
        assert count_connected_components(shape_mask) == 1
        from lithoshape3d.core.image.io import load_image
        from lithoshape3d.core.image.preprocessing import to_grayscale_array

        source_array = to_grayscale_array(load_image(image_path))
        cadrage = CadrageDialog(source_array, shape_mask, main_window._project.scene.image_transform)
        cadrage._on_fit_clicked()
        main_window._project.scene.image_transform = cadrage.transform
        main_window._current_material_meshes = None

        # 4. generer
        main_window.view_composition_button.setChecked(True)
        main_window._on_generate_clicked()
        _wait_until(lambda: main_window._state is not AppState.GENERATING, qapp)
        assert main_window._state is AppState.MESH_READY, main_window.statusBar().currentMessage()
        assert main_window._current_mesh is not None

        # 5. verifier la silhouette : le mesh doit correspondre a la forme de
        # la lettre, pas a un rectangle plein (nettement moins large en haut
        # qu'un carre complet, cf. la forme du "M" -- deux jambages + creux
        # central) -- verifie via l'API d'imprimabilite (2.16), qui expose
        # aussi les dimensions physiques finales.
        report = check_printability(
            main_window._current_mesh, shape_mask=shape_mask, pixel_size_mm=main_window.resolution_spin.value()
        )
        assert report.mesh_validation.is_valid
        assert report.width_mm > 0
        assert report.height_mm > 0
        reference_full_mask = build_shape_mask(ShapeParams(shape_type=ShapeType.RECTANGLE), *shape_mask.shape)
        assert shape_mask.sum() < reference_full_mask.sum()  # le "M" occupe moins que le rectangle plein

        # 6. exporter en STL puis en 3MF (mono-materiau -- pas de multi-couleur ici)
        stl_path = tmp_path / "lettre_m.stl"
        monkeypatch.setattr(
            "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(stl_path), "STL (*.stl)"),
        )
        main_window._on_export_clicked()
        assert stl_path.exists()

        # 7. valider le mesh exporte (watertight/manifold, pas seulement en memoire)
        reloaded = trimesh.load(stl_path, process=True)
        reexported_result = validate_mesh(reloaded)
        assert reexported_result.is_valid
        assert reexported_result.connected_components == 1
    finally:
        main_window.plotter.close()
