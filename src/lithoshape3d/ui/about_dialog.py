"""Fenetre "A propos de LithoShape3D" (menu Aide) : identite minimale --
logo, nom, version reelle du package, courte description, copyright, et un
seul bouton de fermeture. Pas de lien externe obligatoire (cf. mission
branding/packaging, tache 3) : reste un simple ecran d'information, pas une
page marketing."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from lithoshape3d.ui.branding import BRAND_NAME, application_icon

_TAGLINE = "Creation de lithophanies et reliefs 3D a partir d'images."
_COPYRIGHT = "© 2026 LithoShape3D"


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        from lithoshape3d import __version__

        self.setWindowTitle(f"A propos de {BRAND_NAME}")
        self.setFixedSize(360, 220)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 26, 28, 20)

        header = QHBoxLayout()
        header.setSpacing(14)

        mark = QLabel()
        mark.setPixmap(application_icon().pixmap(56, 56))
        mark.setFixedSize(56, 56)
        mark.setScaledContents(True)
        header.addWidget(mark)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        name_label = QLabel(BRAND_NAME)
        name_label.setObjectName("aboutName")
        title_col.addWidget(name_label)
        self.version_label = QLabel(f"Version {__version__}")
        self.version_label.setObjectName("aboutVersion")
        title_col.addWidget(self.version_label)
        header.addLayout(title_col)
        header.addStretch(1)
        layout.addLayout(header)

        tagline = QLabel(_TAGLINE)
        tagline.setWordWrap(True)
        layout.addWidget(tagline)

        layout.addStretch(1)

        copyright_label = QLabel(_COPYRIGHT)
        copyright_label.setObjectName("aboutCopyright")
        layout.addWidget(copyright_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
