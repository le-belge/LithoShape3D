"""Dialogue de saisie de la cle de licence (verification hors-ligne, voir
`core/licensing.py`)."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from lithoshape3d.core.licensing import InvalidLicenseError, verify_license_key

SETTINGS_KEY_LICENSE = "license/key"


def stored_license_key() -> str | None:
    settings = QSettings()
    value = settings.value(SETTINGS_KEY_LICENSE, "")
    return value or None


def is_licensed() -> bool:
    key = stored_license_key()
    if not key:
        return False
    try:
        verify_license_key(key)
        return True
    except InvalidLicenseError:
        return False


class LicenseDialog(QDialog):
    """Saisie/collage de la cle de licence recue a l'achat."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Licence LithoShape3D")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Collez la cle de licence recue par email a l'achat.\n"
                "L'export STL/3MF necessite une licence valide -- le reste du "
                "logiciel (import, cadrage, apercu 3D) reste utilisable sans."
            )
        )

        self.key_edit = QLineEdit(stored_license_key() or "")
        self.key_edit.setPlaceholderText("payload.signature")
        layout.addWidget(self.key_edit)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self._refresh_status(self.key_edit.text())
        self.key_edit.textChanged.connect(self._refresh_status)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_status(self, key_str: str) -> None:
        key_str = key_str.strip()
        if not key_str:
            self.status_label.setText("Aucune cle saisie.")
            return
        try:
            info = verify_license_key(key_str)
        except InvalidLicenseError:
            self.status_label.setText("Cle invalide.")
            self.status_label.setObjectName("licenseStatusInvalid")
            self.status_label.setStyleSheet("color: #b5790f; font-weight: 600;")
            return
        self.status_label.setText(f"Licence valide -- {info.email}")
        self.status_label.setStyleSheet("color: #157C89; font-weight: 600;")

    def _on_save(self) -> None:
        key_str = self.key_edit.text().strip()
        if key_str:
            try:
                verify_license_key(key_str)
            except InvalidLicenseError:
                QMessageBox.warning(self, "LithoShape3D", "Cette cle de licence n'est pas valide.")
                return
        settings = QSettings()
        settings.setValue(SETTINGS_KEY_LICENSE, key_str)
        self.accept()
