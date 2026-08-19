"""Demo Phase 1B : Image -> moteur Phase 1A -> affichage 3D interactif.

CE N'EST PAS L'INTERFACE FINALE DE LITHOSHAPE3D. Pas de theme, pas de
panneau complexe, pas d'edition multi-zones : le seul but est de prouver
que le viewer consomme correctement le moteur existant.

Usage :
    python scripts/demo_viewer.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from lithoshape3d.core.geometry.heightmap import (
    height_mm_from_aspect_ratio,
    heightmap_from_image_path,
)
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.image.pipeline import image_size
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.viewer.scene_viewer import DisplayMode, SceneViewer


class DemoWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LithoShape3D - Demo Phase 1B (viewer)")
        self.resize(1100, 700)

        self._image_path: str | None = None
        self._current_mesh = None

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)

        root_layout.addWidget(self._build_controls(), 0)

        self.plotter = QtInteractor(central)
        root_layout.addWidget(self.plotter.interactor, 1)
        self.scene_viewer = SceneViewer(self.plotter)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)

        self.choose_button = QPushButton("Choisir une image...")
        self.choose_button.clicked.connect(self._choose_image)
        layout.addWidget(self.choose_button)

        self.image_label = QLabel("Aucune image selectionnee")
        self.image_label.setWordWrap(True)
        layout.addWidget(self.image_label)

        layout.addWidget(QLabel("Largeur (mm)"))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 500.0)
        self.width_spin.setValue(100.0)
        layout.addWidget(self.width_spin)

        layout.addWidget(QLabel("Epaisseur min (mm)"))
        self.min_thickness_spin = QDoubleSpinBox()
        self.min_thickness_spin.setRange(0.1, 10.0)
        self.min_thickness_spin.setSingleStep(0.1)
        self.min_thickness_spin.setValue(0.8)
        layout.addWidget(self.min_thickness_spin)

        layout.addWidget(QLabel("Epaisseur max (mm)"))
        self.max_thickness_spin = QDoubleSpinBox()
        self.max_thickness_spin.setRange(0.2, 15.0)
        self.max_thickness_spin.setSingleStep(0.1)
        self.max_thickness_spin.setValue(3.0)
        layout.addWidget(self.max_thickness_spin)

        layout.addWidget(QLabel("Resolution (mm/px)"))
        self.resolution_spin = QDoubleSpinBox()
        self.resolution_spin.setRange(0.05, 2.0)
        self.resolution_spin.setSingleStep(0.05)
        self.resolution_spin.setValue(0.3)
        layout.addWidget(self.resolution_spin)

        self.invert_checkbox = QCheckBox("Inverser (clair = epais)")
        layout.addWidget(self.invert_checkbox)

        self.generate_button = QPushButton("Generer")
        self.generate_button.clicked.connect(self._generate)
        layout.addWidget(self.generate_button)

        layout.addWidget(QLabel("Mode d'affichage"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("Surface", DisplayMode.SURFACE)
        self.display_mode_combo.addItem("Fil de fer", DisplayMode.WIREFRAME)
        self.display_mode_combo.addItem("Surface + aretes", DisplayMode.SURFACE_WITH_EDGES)
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        layout.addWidget(self.display_mode_combo)

        layout.addWidget(QLabel("Vues"))
        for label, method_name in [
            ("Face", "view_front"),
            ("Arriere", "view_back"),
            ("Gauche", "view_left"),
            ("Droite", "view_right"),
            ("Dessus", "view_top"),
            ("Isometrique", "view_isometric"),
            ("Reinitialiser", "reset_camera"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, m=method_name: getattr(self.scene_viewer, m)())
            layout.addWidget(button)

        layout.addStretch(1)
        return panel

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une image", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self._image_path = path
            self.image_label.setText(path)

    def _generate(self) -> None:
        if not self._image_path:
            QMessageBox.warning(self, "LithoShape3D", "Choisissez d'abord une image.")
            return

        width_mm = self.width_spin.value()
        image_width_px, image_height_px = image_size(self._image_path)
        height_mm = height_mm_from_aspect_ratio(width_mm, image_width_px, image_height_px)

        params = GeometryParameters(
            width_mm=width_mm,
            height_mm=height_mm,
            min_thickness_mm=self.min_thickness_spin.value(),
            max_thickness_mm=self.max_thickness_spin.value(),
            invert=self.invert_checkbox.isChecked(),
            resolution=self.resolution_spin.value(),
        )

        heightmap = heightmap_from_image_path(self._image_path, params)
        mesh = build_slab_mesh(heightmap, mask=None, params=params)
        result = validate_mesh(mesh)

        if not result.is_valid:
            QMessageBox.critical(self, "LithoShape3D", "Mesh invalide : " + ", ".join(result.issues()))
            return

        self._current_mesh = mesh
        self.scene_viewer.show_mesh(mesh, display_mode=self.display_mode_combo.currentData())
        self.scene_viewer.view_isometric()

    def _on_display_mode_changed(self) -> None:
        if self._current_mesh is not None:
            self.scene_viewer.show_mesh(self._current_mesh, display_mode=self.display_mode_combo.currentData())


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
