"""Ecran minimal "LightBox Letters" : declenche visuellement la meme
generation que la commande CLI `lithoshape3d lightbox-letters`, sans taper
de commande. Reutilise directement `generate_lightbox_letters`
(core/geometry/lightbox_letters_export.py), la meme fonction que le CLI --
aucune logique de generation dupliquee ici, seulement de la construction de
formulaire et un worker Qt pour ne pas geler l'UI pendant l'export.

Flux image/lettre (retour utilisateur : trop de clics, pas assez visuel) :
un seul bouton "Image..." par lettre enchaine selection de fichier ->
cadrage visuel (glisser/molette, `CadrageDialog` reutilise tel quel) ->
retour a la liste, sans dialogue intermediaire separe."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
    compute_word_layout_and_grid,
    generate_lightbox_letters,
    letter_wall_thickness_ok,
    rasterize_letter_shape_mask_for_index,
)
from lithoshape3d.core.scene.models import ImageTransform
from lithoshape3d.ui.fonts import discover_bold_fonts

logger = logging.getLogger("lithoshape3d.ui.lightbox_letters")

_CUSTOM_FONT_LABEL = "Parcourir un fichier .ttf/.otf..."


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
        self.setMinimumWidth(560)

        self._font_path: str = ""
        self._output_dir: str = ""
        self._image_by_index: dict[int, str] = {}
        self._transform_by_index: dict[int, ImageTransform] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._bold_fonts = discover_bold_fonts()

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Mot a generer (ex. LOVE)")
        self.text_edit.textChanged.connect(self._on_text_changed)
        form.addRow("Mot", self.text_edit)

        self.font_combo = QComboBox()
        for display_name, path in self._bold_fonts:
            self.font_combo.addItem(display_name, path)
        self.font_combo.addItem(_CUSTOM_FONT_LABEL, "")
        self.font_combo.currentIndexChanged.connect(self._on_font_combo_changed)
        form.addRow("Police (grasse recommandee)", self.font_combo)

        self.font_path_label = QLabel("(aucune police selectionnee)")
        self.font_path_label.setWordWrap(True)
        form.addRow("", self.font_path_label)

        self.thickness_warning_label = QLabel("")
        self.thickness_warning_label.setWordWrap(True)
        self.thickness_warning_label.setStyleSheet("color: #b45309;")
        form.addRow("", self.thickness_warning_label)

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
        self.font_size_spin.valueChanged.connect(self._on_thickness_relevant_changed)
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
        self.wall_spin.valueChanged.connect(self._on_thickness_relevant_changed)
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
        if self._bold_fonts:
            self.font_combo.setCurrentIndex(0)
            self._on_font_combo_changed(0)

    # ------------------------------------------------------------------ #
    # Selection police / dossier / images
    # ------------------------------------------------------------------ #
    def _on_font_combo_changed(self, combo_index: int) -> None:
        path = self.font_combo.itemData(combo_index)
        if not path:
            # "Parcourir..." : ouvre le selecteur de fichier custom, en
            # conservant l'option existante intacte.
            chosen, _ = QFileDialog.getOpenFileName(
                self, "Choisir une police", "", "Polices (*.ttf *.otf)"
            )
            if chosen:
                self._font_path = chosen
                self.font_path_label.setText(chosen)
            elif not self._font_path:
                self.font_path_label.setText("(aucune police selectionnee)")
            self._on_thickness_relevant_changed()
            return
        self._font_path = path
        self.font_path_label.setText(path)
        self._on_thickness_relevant_changed()

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if directory:
            self._output_dir = directory
            self.output_label.setText(directory)

    def _on_text_changed(self, _text: str) -> None:
        self._refresh_letters_list()
        self._on_thickness_relevant_changed()

    def _on_thickness_relevant_changed(self, *_args) -> None:
        """Reutilise le meme garde-fou d'epaisseur de paroi que la
        generation reelle (`letter_wall_thickness_ok`), applique a un test
        rapide sur les lettres du mot courant (ou un echantillon par defaut
        si le mot est vide) -- avertissement indicatif AVANT de lancer une
        generation complete, aucune logique dupliquee."""
        text = self.text_edit.text().strip() or "Il1"
        if not self._font_path:
            self.thickness_warning_label.setText("")
            return
        try:
            layout, _face_params, _rows, _cols = compute_word_layout_and_grid(
                text, self._font_path, self.font_size_spin.value()
            )
        except Exception:
            self.thickness_warning_label.setText("")
            return

        wall_thickness_mm = self.wall_spin.value()
        thin_letters = [
            letter.character
            for letter in layout.letters
            if not letter_wall_thickness_ok(letter, wall_thickness_mm)
        ]
        if thin_letters:
            self.thickness_warning_label.setText(
                "Police trop fine pour l'epaisseur de paroi demandee (ex. "
                f"'{thin_letters[0]}') -- choisissez une police plus grasse/epaisse, "
                "augmentez la taille de corps, ou reduisez l'epaisseur des parois."
            )
        else:
            self.thickness_warning_label.setText("")

    def _refresh_letters_list(self) -> None:
        text = self.text_edit.text()
        # On garde les images/transforms deja assignes dont l'index reste
        # valide pour ce nouveau texte (evite de perdre une selection sur
        # une simple correction de frappe).
        self._image_by_index = {
            index: path for index, path in self._image_by_index.items() if index < len(text)
        }
        self._transform_by_index = {
            index: transform
            for index, transform in self._transform_by_index.items()
            if index < len(text)
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

        image_path = self._image_by_index.get(index)
        status = Path(image_path).name if image_path else "(aucune image)"
        image_label = QLabel(status)
        row_layout.addWidget(image_label, 1)

        image_button = QPushButton("Image...")
        image_button.setToolTip(
            "Choisir une image puis regler son cadrage sur la lettre "
            "(glisser = deplacer, molette = zoomer)."
        )
        image_button.clicked.connect(lambda: self._assign_letter_image(index))
        row_layout.addWidget(image_button)

        return row

    def _assign_letter_image(self, index: int) -> None:
        text = self.text_edit.text()
        if index >= len(text):
            return
        if not self._font_path:
            QMessageBox.warning(
                self, "LightBox Letters", "Choisissez d'abord une police pour pouvoir cadrer l'image."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Image de lithophanie", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return

        try:
            shape_mask = rasterize_letter_shape_mask_for_index(
                text, self._font_path, self.font_size_spin.value(), index
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "LightBox Letters", f"Impossible de calculer le contour de la lettre : {exc}"
            )
            return

        try:
            from lithoshape3d.core.image.io import load_image
            from lithoshape3d.core.image.preprocessing import to_grayscale_array

            source_array = to_grayscale_array(load_image(path))
        except Exception as exc:
            QMessageBox.warning(self, "LightBox Letters", f"Image illisible : {exc}")
            return

        # Enchaine directement sur le cadrage visuel -- pas de dialogue
        # intermediaire "Assigner une image..." separe du reglage.
        from lithoshape3d.ui.cadrage_dialog import CadrageDialog

        initial_transform = self._transform_by_index.get(index, ImageTransform())
        cadrage = CadrageDialog(source_array, shape_mask, initial_transform, self)
        cadrage.setWindowTitle(f"Cadrer la photo -- lettre '{text[index]}'")
        if cadrage.exec() != QDialog.DialogCode.Accepted:
            return

        self._image_by_index[index] = path
        self._transform_by_index[index] = cadrage.transform
        self._refresh_letters_list()

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
            transforms_by_index=dict(self._transform_by_index),
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
