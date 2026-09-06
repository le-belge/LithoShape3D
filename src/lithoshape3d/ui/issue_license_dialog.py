"""Bouton vendeur : genere une cle de licence directement depuis l'app.

N'apparait que si `core.licensing.seller_private_key_hex()` trouve la cle
privee locale du vendeur -- absente de l'app packagee livree a un client,
ce menu n'existe donc que sur la machine du vendeur. Voir
`main_window.py::_maybe_add_seller_menu`."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from lithoshape3d.core.licensing import issue_license_key, seller_private_key_hex


class IssueLicenseDialog(QDialog):
    """Saisie de l'email client -> cle de licence prete a copier."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generer une licence (vendeur)")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Email du client :"))

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("client@example.com")
        layout.addWidget(self.email_edit)

        self.generate_button = QPushButton("Generer")
        self.generate_button.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_button)

        layout.addWidget(QLabel("Cle de licence (a copier dans l'email de confirmation) :"))
        self.result_edit = QLineEdit()
        self.result_edit.setReadOnly(True)
        layout.addWidget(self.result_edit)

        self.copy_button = QPushButton("Copier")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._on_copy)
        layout.addWidget(self.copy_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _on_generate(self) -> None:
        email = self.email_edit.text().strip()
        if not email:
            QMessageBox.warning(self, "LithoShape3D", "Entrez l'email du client.")
            return
        private_key_hex = seller_private_key_hex()
        if not private_key_hex:
            QMessageBox.critical(self, "LithoShape3D", "Cle privee vendeur introuvable.")
            return
        key = issue_license_key(email, private_key_hex)
        self.result_edit.setText(key)
        self.copy_button.setEnabled(True)

    def _on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.result_edit.text())
        self.copy_button.setText("Copie !")
