from __future__ import annotations

import pyvista as pv
import pytest

from lithoshape3d.ui.i18n import (
    DEFAULT_LANGUAGE,
    install_translator,
    set_stored_language,
    stored_language,
)
from lithoshape3d.ui.main_window import MainWindow


def test_default_language_is_french(qapp):
    assert stored_language() == DEFAULT_LANGUAGE == "fr"


def test_set_stored_language_persists_and_rejects_unknown_codes(qapp):
    set_stored_language("en")
    try:
        assert stored_language() == "en"
    finally:
        set_stored_language("fr")  # ne pas polluer les tests suivants

    with pytest.raises(ValueError):
        set_stored_language("de")


def test_install_translator_is_a_noop_for_french(qapp):
    assert install_translator(qapp, "fr") is True


def test_install_translator_loads_the_english_qm(qapp):
    assert install_translator(qapp, "en") is True
    qapp.removeTranslator(qapp._lithoshape3d_translator)


def test_generate_button_translates_once_english_is_installed(qapp):
    assert install_translator(qapp, "en") is True
    try:
        window = MainWindow(plotter=pv.Plotter(off_screen=True))
        try:
            assert window.generate_button.text() == "Generate"
        finally:
            window.plotter.close()
    finally:
        qapp.removeTranslator(qapp._lithoshape3d_translator)


def test_language_menu_lists_french_and_english(main_window):
    actions = {a.text(): a for a in main_window.menuBar().actions()}
    assert "Langue" in actions
    language_menu = actions["Langue"].menu()
    labels = {a.text() for a in language_menu.actions()}
    assert labels == {"Francais", "English"}
