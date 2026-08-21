"""E2E (2.16) : une Shape Texte disjointe genere un mesh valide, ET le
diagnostic d'imprimabilite (composantes disjointes) doit remonter jusqu'a
l'utilisateur via la barre de statut -- sans jamais bloquer l'export."""

import time

from lithoshape3d.core.scene.models import ShapeType
from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=60, height=45):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def _wait_for_mesh_ready(main_window, qapp, timeout=10):
    deadline = time.monotonic() + timeout
    while main_window._state is AppState.GENERATING and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def test_disjoint_text_shape_reports_warning_in_status_bar(qapp, main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)

    idx = main_window.shape_type_combo.findData(ShapeType.TEXT)
    main_window.shape_type_combo.setCurrentIndex(idx)
    main_window.shape_text_edit.setText("LOVE")
    main_window._on_shape_changed()

    assert "4 elements separes" in main_window.shape_info_label.text()

    main_window.view_composition_button.setChecked(True)
    main_window._on_generate_clicked()
    _wait_for_mesh_ready(main_window, qapp)

    assert main_window._state is AppState.MESH_READY
    assert main_window._current_mesh is not None
    assert "composantes disjointes" in main_window.statusBar().currentMessage()
    # le diagnostic est informatif uniquement -- l'export reste possible
    assert main_window.export_button.isEnabled()


def test_single_component_shape_does_not_warn(qapp, main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)

    idx = main_window.shape_type_combo.findData(ShapeType.HEART)
    main_window.shape_type_combo.setCurrentIndex(idx)

    main_window.view_composition_button.setChecked(True)
    main_window._on_generate_clicked()
    _wait_for_mesh_ready(main_window, qapp)

    assert main_window._state is AppState.MESH_READY
    assert "composantes disjointes" not in main_window.statusBar().currentMessage()
