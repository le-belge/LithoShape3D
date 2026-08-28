"""Ecran minimal "LightBox Letters" : declenche visuellement la meme
generation que la commande CLI `lithoshape3d lightbox-letters`, sans taper
de commande. Reutilise directement `generate_lightbox_letters`
(core/geometry/lightbox_letters_export.py), la meme fonction que le CLI --
aucune logique de generation dupliquee ici, seulement de la construction de
formulaire et un worker Qt pour ne pas geler l'UI pendant l'export."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.core.geometry.lightbox_letters_export import (
    LightboxLettersResult,
    generate_lightbox_letters,
)

logger = logging.getLogger("lithoshape3d.ui.lightbox_letters")


class _LightboxLettersSignals(QObject):
    succeeded = Signal(object)  # LightboxLettersResult
    failed = Signal(str)
    finished = Signal()


class _LightboxLettersWorker(QRunnable):
    """Genere le mot en arriere-plan -- meme discipline que les autres
    workers du projet (worker.py) : aucun widget touche depuis `run()`,
    resultat uniquement via signaux Qt (mis en file d'attente cross-thread
    automatiquement)."""

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self._kwargs = kwargs
        self.signals = _LightboxLettersSignals()

    def run(self) -> None:
        try:
            result = generate_lightbox_letters(**self._kwargs)
        except (ValueError, OSError, RuntimeError) as exc:
            logger.exception("Echec de la generation LightBox Letters")
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return
        self.signals.succeeded.emit(result)
        self.signals.finished.emit()


class LightboxLettersDialog(QDialog):
    """Dialogue modal minimal pour generer un caisson lumineux par lettre."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LightBox Letters")
        self.setMinimumWidth(520)

        self._font_path: str = ""
        self._output_dir: str = ""
        self._image_by_index: dict[int, str] = {}
        self._thread_pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Mot a generer (ex. LOVE)")
        self.text_edit.textChanged.connect(self._on_text_changed)
        form.addRow("Mot", self.text_edit)

        font_row = QHBoxLayout()
        self.font_label = QLabel("(aucune police selectionnee)")
        font_button = QPushButton("Choisir une police...")
        font_button.clicked.connect(self._choose_font)
        font_row.addWidget(self.font_label, 1)
        font_row.addWidget(font_button)
        form.addRow("Police (.ttf/.otf)", font_row)

        output_row = QHBoxLayout()
        self.output_label = QLabel("(aucun dossier selectionne)")
        output_button = QPushButton("Choisir un dossier...")
        output_button.clicked.connect(self._choose_output_dir)
        output_row.addWidget(self.output_label, 1)
        output_row.addWidget(output_button)
        form.addRow("Dossier de sortie", output_row)

        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(5.0, 500.0)
        self.font_size_spin.setValue(40.0)
        self.font_size_spin.setSuffix(" mm")
        form.addRow("Taille de corps", self.font_size_spin)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1.0, 200.0)
        self.depth_spin.setValue(25.0)
        self.depth_spin.setSuffix(" mm")
        form.addRow("Profondeur du caisson", self.depth_spin)

        self.wall_spin = QDoubleSpinBox()
        self.wall_spin.setRange(0.4, 20.0)
        self.wall_spin.setSingleStep(0.1)
        self.wall_spin.setValue(1.6)
        self.wall_spin.setSuffix(" mm")
        form.addRow("Epaisseur des parois", self.wall_spin)

        layout.addLayout(form)

        layout.addWidget(QLabel("Lettres du mot (image de lithophanie optionnelle par lettre) :"))
        self.letters_list = QListWidget()
        layout.addWidget(self.letters_list)

        self.generate_button = QPushButton("Generer")
        self.generate_button.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("Le resultat de la generation s'affichera ici.")
        self.result_view.setMinimumHeight(140)
        layout.addWidget(self.result_view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_letters_list()

    # ------------------------------------------------------------------ #
    # Selection police / dossier / images
    # ------------------------------------------------------------------ #
    def _choose_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une police", "", "Polices (*.ttf *.otf)"
        )
        if path:
            self._font_path = path
            self.font_label.setText(path)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if directory:
            self._output_dir = directory
            self.output_label.setText(directory)

    def _on_text_changed(self, _text: str) -> None:
        self._refresh_letters_list()

    def _refresh_letters_list(self) -> None:
        text = self.text_edit.text()
        # On garde les images deja assignees dont l'index reste valide pour
        # ce nouveau texte (evite de perdre une selection sur une simple
        # correction de frappe).
        self._image_by_index = {
            index: path for index, path in self._image_by_index.items() if index < len(text)
        }
        self.letters_list.clear()
        for index, character in enumerate(text):
            item = QListWidgetItem()
            row_widget = self._build_letter_row(index, character)
            item.setSizeHint(row_widget.sizeHint())
            self.letters_list.addItem(item)
            self.letters_list.setItemWidget(item, row_widget)

    def _build_letter_row(self, index: int, character: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)

        label = QLabel(f"#{index} '{character}'")
        label.setMinimumWidth(80)
        row_layout.addWidget(label)

        image_label = QLabel(self._image_by_index.get(index, "(aucune image)"))
        row_layout.addWidget(image_label, 1)

        assign_button = QPushButton("Assigner une image...")
        assign_button.clicked.connect(lambda: self._assign_letter_image(index, image_label))
        row_layout.addWidget(assign_button)

        return row

    def _assign_letter_image(self, index: int, image_label: QLabel) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image de lithophanie", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._image_by_index[index] = path
            image_label.setText(path)

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def _on_generate_clicked(self) -> None:
        text = self.text_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "LightBox Letters", "Saisissez un mot a generer.")
            return
        if not self._font_path:
            QMessageBox.warning(self, "LightBox Letters", "Choisissez une police (.ttf/.otf).")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "LightBox Letters", "Choisissez un dossier de sortie.")
            return

        self.generate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.result_view.setPlainText("Generation en cours...")

        worker = _LightboxLettersWorker(
            text=text,
            font_path=self._font_path,
            output_dir=self._output_dir,
            font_size_mm=self.font_size_spin.value(),
            depth_mm=self.depth_spin.value(),
            wall_thickness_mm=self.wall_spin.value(),
            images_by_index=dict(self._image_by_index),
        )
        worker.signals.succeeded.connect(self._on_generation_succeeded)
        worker.signals.failed.connect(self._on_generation_failed)
        worker.signals.finished.connect(self._on_generation_finished)
        self._thread_pool.start(worker)

    def _on_generation_succeeded(self, result: LightboxLettersResult) -> None:
        lines: list[str] = []
        for level, text in result.messages:
            prefix = "ECHEC" if level == "error" else "AVERTISSEMENT"
            lines.append(f"{prefix}: {text}")

        if not result.ok:
            lines.append("ECHEC: aucune lettre n'a pu etre generee.")
        else:
            lines.append("")
            lines.append(f"OK -- {len(result.written)} fichier(s) genere(s) :")
            lines.extend(str(path) for path in result.written)

        self.result_view.setPlainText("\n".join(lines))

    def _on_generation_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"ECHEC: {message}")

    def _on_generation_finished(self) -> None:
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
