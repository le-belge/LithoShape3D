"""Mode "Cadrer la photo" (Shape Composer, v0.4) : glisser/molette/boutons
Remplir-Ajuster-Centrer-Reinitialiser -- vue seulement, ne recalcule jamais
de mesh (voir docstring de module de cadrage_dialog.py)."""

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF
from PySide6.QtCore import Qt as QtNS
from PySide6.QtGui import QMouseEvent, QWheelEvent

from lithoshape3d.core.scene.models import ImageTransform
from lithoshape3d.ui.cadrage_dialog import CadrageDialog


@pytest.fixture
def dialog(qapp):
    source = np.full((200, 300), 0.5, dtype=np.float32)
    shape_mask = np.ones((150, 150), dtype=bool)
    d = CadrageDialog(source, shape_mask, ImageTransform())
    d.resize(700, 700)
    d.preview.resize(400, 400)
    return d


def _press(pos):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.LeftButton, QtNS.KeyboardModifier.NoModifier,
    )


def _move(pos):
    return QMouseEvent(
        QEvent.Type.MouseMove, pos, QtNS.MouseButton.NoButton,
        QtNS.MouseButton.LeftButton, QtNS.KeyboardModifier.NoModifier,
    )


def _release(pos):
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease, pos, QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.NoButton, QtNS.KeyboardModifier.NoModifier,
    )


def test_dialog_starts_with_identity_transform(dialog):
    assert dialog.transform == ImageTransform()


def test_drag_before_any_paint_event_produces_small_fractional_offset(dialog):
    """Regression : `_draw_rect` ne doit pas dependre d'un paintEvent
    prealable, sinon un glissement demarre avant le tout premier rendu
    (frequent dans un dialogue qui vient de s'ouvrir) donne un decalage
    enorme (pixels bruts au lieu d'une fraction) au lieu d'un pan normal."""
    dialog.preview.mousePressEvent(_press(QPointF(200, 200)))
    dialog.preview.mouseMoveEvent(_move(QPointF(250, 220)))

    assert abs(dialog.transform.offset_x) < 1.0
    assert abs(dialog.transform.offset_y) < 1.0
    assert dialog.transform.offset_x > 0  # glisse vers la droite -> offset positif


def test_drag_release_stops_dragging(dialog):
    dialog.preview.mousePressEvent(_press(QPointF(200, 200)))
    dialog.preview.mouseMoveEvent(_move(QPointF(220, 200)))
    dialog.preview.mouseReleaseEvent(_release(QPointF(220, 200)))

    assert dialog.preview._dragging is False


def test_wheel_zooms_in_and_out(dialog):
    wheel_in = QWheelEvent(
        QPointF(200, 200), QPointF(200, 200), QPoint(0, 0), QPoint(0, 120),
        QtNS.MouseButton.NoButton, QtNS.KeyboardModifier.NoModifier,
        QtNS.ScrollPhase.NoScrollPhase, False,
    )
    dialog.preview.wheelEvent(wheel_in)
    assert dialog.transform.scale > 1.0

    scale_after_in = dialog.transform.scale
    wheel_out = QWheelEvent(
        QPointF(200, 200), QPointF(200, 200), QPoint(0, 0), QPoint(0, -120),
        QtNS.MouseButton.NoButton, QtNS.KeyboardModifier.NoModifier,
        QtNS.ScrollPhase.NoScrollPhase, False,
    )
    dialog.preview.wheelEvent(wheel_out)
    assert dialog.transform.scale < scale_after_in


def test_fit_button_resets_offset_and_scale_to_identity(dialog):
    dialog.preview.mousePressEvent(_press(QPointF(200, 200)))
    dialog.preview.mouseMoveEvent(_move(QPointF(250, 250)))

    dialog._on_fit_clicked()

    assert dialog.transform.offset_x == 0.0
    assert dialog.transform.offset_y == 0.0
    assert dialog.transform.scale == 1.0


def test_fill_button_scales_up_for_mismatched_aspect_ratio(dialog):
    dialog._on_fill_clicked()

    assert dialog.transform.scale > 1.0  # source 300x200, shape carree -> Remplir agrandit


def test_center_button_resets_only_offset(dialog):
    dialog.preview.mousePressEvent(_press(QPointF(200, 200)))
    dialog.preview.mouseMoveEvent(_move(QPointF(250, 250)))
    dialog._on_fill_clicked()  # change le scale
    scale_before_center = dialog.transform.scale

    dialog._on_center_clicked()

    assert dialog.transform.offset_x == 0.0
    assert dialog.transform.offset_y == 0.0
    assert dialog.transform.scale == scale_before_center  # inchange


def test_reset_button_restores_full_identity(dialog):
    dialog.rotation_spin.setValue(45.0)
    dialog._on_fill_clicked()

    dialog._on_reset_clicked()

    assert dialog.transform == ImageTransform()
    assert dialog.rotation_spin.value() == 0.0


def test_rotation_spin_updates_transform(dialog):
    dialog.rotation_spin.setValue(30.0)

    assert dialog.transform.rotation_deg == 30.0
