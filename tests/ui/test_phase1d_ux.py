from PySide6.QtGui import QKeySequence

from lithoshape3d.ui.state import AppState
from lithoshape3d.ui.theme import STYLESHEET, apply_theme
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=64, height=48):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_preview_rescales_on_resize_without_recomputation(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    assert main_window.preview_label.pixmap() is not None
    assert not main_window.preview_label.pixmap().isNull()

    calls = []
    import lithoshape3d.ui.main_window as main_window_module

    original = main_window_module.to_grayscale_array
    monkeypatch.setattr(
        main_window_module,
        "to_grayscale_array",
        lambda *a, **k: calls.append(1) or original(*a, **k),
    )

    main_window.preview_label.resize(400, 300)

    assert not calls  # aucun recalcul image declenche par le resize
    assert not main_window.preview_label.pixmap().isNull()


def test_preview_keeps_aspect_ratio_after_resize(main_window, tmp_path):
    _load(main_window, tmp_path, width=200, height=100)  # ratio 2:1

    main_window.preview_label.resize(300, 300)  # carre : le pixmap doit rester 2:1

    pixmap = main_window.preview_label.pixmap()
    assert pixmap is not None
    ratio = pixmap.width() / pixmap.height()
    assert 1.9 < ratio < 2.1


def test_stale_banner_visible_only_when_params_dirty(main_window, tmp_path):
    # La fenetre n'est jamais montree en test (pas de vraie fenetre Qt/VTK) :
    # isHidden() reflete l'appel explicite a setVisible(), contrairement a
    # isVisible() qui depend de la visibilite reelle a l'ecran.
    _load(main_window, tmp_path)
    assert main_window.stale_banner.isHidden()

    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)
    assert main_window.stale_banner.isHidden()

    main_window.max_thickness_spin.setValue(6.0)
    assert main_window._state is AppState.PARAMS_DIRTY
    assert not main_window.stale_banner.isHidden()


def test_generating_message_has_no_fake_percentage(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._set_state(AppState.GENERATING)

    message = main_window.statusBar().currentMessage()
    assert "%" not in message
    assert main_window.progress_bar.minimum() == 0
    assert main_window.progress_bar.maximum() == 0  # indetermine, jamais un faux pourcentage


def test_menu_shortcuts_follow_macos_conventions(main_window):
    assert main_window.open_action.shortcut() == QKeySequence.StandardKey.Open
    assert main_window.export_action.shortcut() == QKeySequence("Ctrl+E")
    assert main_window.generate_action.shortcut() == QKeySequence("Ctrl+R")


def test_theme_stylesheet_targets_key_widgets():
    assert "#generateButton" in STYLESHEET
    assert "#staleBanner" in STYLESHEET


def test_apply_theme_sets_stylesheet_on_app(qapp):
    apply_theme(qapp)
    assert qapp.styleSheet() == STYLESHEET
