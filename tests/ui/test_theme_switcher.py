from __future__ import annotations

import pyvista as pv

from lithoshape3d.ui.main_window import MainWindow
from lithoshape3d.ui.theme import ACCENT_TURQUOISE, build_stylesheet, set_theme_dark, stored_theme_is_dark


def test_dark_is_the_default_theme(qapp):
    assert stored_theme_is_dark()


def test_set_theme_dark_persists_the_choice(qapp):
    set_theme_dark(qapp, False)
    try:
        assert not stored_theme_is_dark()
        assert qapp.styleSheet() == build_stylesheet(dark=False)
    finally:
        set_theme_dark(qapp, True)  # ne pas polluer les tests suivants


def test_both_stylesheets_use_the_same_signature_accent():
    assert ACCENT_TURQUOISE in build_stylesheet(dark=True)
    assert ACCENT_TURQUOISE in build_stylesheet(dark=False)


def test_theme_menu_reflects_current_choice_and_toggling_persists(qapp):
    set_theme_dark(qapp, True)
    window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        actions = {a.text(): a for a in window.menuBar().actions()}
        assert "Theme" in actions

        dark_action, light_action = _theme_actions(window)
        assert dark_action.isChecked()
        assert not light_action.isChecked()

        light_action.trigger()
        assert not stored_theme_is_dark()
    finally:
        window.plotter.close()
        set_theme_dark(qapp, True)


def _theme_actions(window):
    theme_menu = next(
        window.menuBar().actions()[i].menu()
        for i in range(len(window.menuBar().actions()))
        if window.menuBar().actions()[i].text() == "Theme"
    )
    dark_action, light_action = theme_menu.actions()
    return dark_action, light_action
