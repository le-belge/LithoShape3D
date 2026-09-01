"""Fenetre "A propos de LithoShape3D" (menu Aide, mission branding tache 3) :
s'ouvre, affiche la version REELLE du package, puis se ferme proprement."""

from lithoshape3d import __version__
from lithoshape3d.ui.about_dialog import AboutDialog
from lithoshape3d.ui.branding import BRAND_NAME


def test_about_dialog_shows_real_package_version(qapp):
    dialog = AboutDialog()

    assert __version__ in dialog.version_label.text()
    assert BRAND_NAME in dialog.windowTitle()

    dialog.close()
    assert not dialog.isVisible()


def test_about_dialog_close_button_closes_without_error(qapp):
    dialog = AboutDialog()
    dialog.show()
    assert dialog.isVisible()

    from PySide6.QtWidgets import QDialogButtonBox

    box = dialog.findChild(QDialogButtonBox)
    box.button(QDialogButtonBox.StandardButton.Close).click()

    assert not dialog.isVisible()


def test_main_window_help_menu_opens_about_dialog(main_window, monkeypatch):
    """Accessible depuis le menu Aide -- verifie que l'action declenche bien
    l'ouverture d'une AboutDialog (sans bloquer sur exec(), on intercepte)."""
    opened = {}

    def fake_exec(self):
        opened["called"] = True
        opened["version_text"] = self.version_label.text()
        return 0

    monkeypatch.setattr(AboutDialog, "exec", fake_exec)

    main_window._show_about()

    assert opened.get("called") is True
    assert __version__ in opened["version_text"]
