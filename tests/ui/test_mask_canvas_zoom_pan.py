"""Hotfix 0.3.1 : zoom/pan de l'editeur de masque. Le point critique (1.5 du
brief) est que le mapping souris -> coordonnees image reste EXACT a tout
niveau de zoom/pan -- sinon le pinceau/la gomme/SAM2 touchent le mauvais
pixel des que l'utilisateur zoome. Ces tests verifient le mapping
directement (pas seulement "ca ne plante pas")."""

import numpy as np
import pytest
from PySide6.QtCore import QPointF

from lithoshape3d.ui.mask_edit_controller import MaskEditController
from lithoshape3d.ui.mask_editor_dialog import _MaskCanvas


@pytest.fixture
def canvas(qapp):
    image = np.zeros((100, 160), dtype=np.float32)
    controller = MaskEditController(np.zeros((100, 160), dtype=np.float32))
    c = _MaskCanvas(controller, image, (255, 0, 0))
    c.resize(400, 300)
    return c


def test_zoom_to_fit_matches_expected_scale_formula(canvas):
    canvas.zoom_to_fit()

    expected_scale = min(400 / 160, 300 / 100)
    assert canvas._scale == pytest.approx(expected_scale)


def test_zoom_to_fit_centers_the_image(canvas):
    canvas.zoom_to_fit()

    rows, cols = canvas.base_image.shape[:2]
    expected_x = (canvas.width() - cols * canvas._scale) / 2.0
    expected_y = (canvas.height() - rows * canvas._scale) / 2.0
    assert canvas._origin.x() == pytest.approx(expected_x)
    assert canvas._origin.y() == pytest.approx(expected_y)


def test_zoom_to_actual_size_sets_scale_to_one(canvas):
    canvas.zoom_to_fit()
    canvas.zoom_to_actual_size()

    assert canvas._scale == pytest.approx(1.0)


def test_widget_to_image_round_trip_at_fit_scale(canvas):
    canvas.zoom_to_fit()

    image_point = (42.0, 17.0)
    widget_x = canvas._origin.x() + image_point[0] * canvas._scale
    widget_y = canvas._origin.y() + image_point[1] * canvas._scale

    recovered = canvas._widget_to_image_xy(QPointF(widget_x, widget_y))

    assert recovered[0] == pytest.approx(image_point[0])
    assert recovered[1] == pytest.approx(image_point[1])


@pytest.mark.parametrize("zoom_factor", [2.0, 4.0, 8.0])
def test_widget_to_image_round_trip_stays_exact_when_zoomed(canvas, zoom_factor):
    canvas.zoom_to_fit()
    canvas.zoom_by_factor(zoom_factor)

    image_point = (30.0, 60.0)
    widget_x = canvas._origin.x() + image_point[0] * canvas._scale
    widget_y = canvas._origin.y() + image_point[1] * canvas._scale

    recovered = canvas._widget_to_image_xy(QPointF(widget_x, widget_y))

    assert recovered[0] == pytest.approx(image_point[0], abs=1e-6)
    assert recovered[1] == pytest.approx(image_point[1], abs=1e-6)


def test_wheel_zoom_keeps_image_point_under_cursor_fixed(canvas):
    """Zoom "vers le curseur" : le point image sous le curseur doit rester
    exactement sous le curseur apres le zoom, sinon le pinceau derape a
    chaque coup de molette."""
    canvas.zoom_to_fit()
    cursor_widget_pos = QPointF(150.0, 120.0)
    image_point_before = canvas._widget_to_image_xy(cursor_widget_pos)

    canvas._zoom_around(cursor_widget_pos, 3.0)

    image_point_after = canvas._widget_to_image_xy(cursor_widget_pos)
    assert image_point_after[0] == pytest.approx(image_point_before[0], abs=1e-6)
    assert image_point_after[1] == pytest.approx(image_point_before[1], abs=1e-6)


def test_panning_shifts_origin_by_the_drag_delta(canvas):
    canvas.zoom_to_fit()
    origin_before = QPointF(canvas._origin)

    canvas._origin += QPointF(25.0, -10.0)  # equivalent d'un drag de pan

    assert canvas._origin.x() == pytest.approx(origin_before.x() + 25.0)
    assert canvas._origin.y() == pytest.approx(origin_before.y() - 10.0)


def test_paint_at_zoomed_state_touches_the_correct_pixel(canvas):
    """Bout en bout : peindre a une position widget donnee, a un niveau de
    zoom eleve, doit modifier le masque exactement au pixel image attendu
    (pas un pixel voisin a cause d'une erreur d'arrondi/mapping)."""
    canvas.zoom_to_fit()
    canvas.zoom_by_factor(5.0)
    canvas.brush_radius = 1  # pinceau tres fin : un seul pixel modifie

    target_image_point = (80.0, 45.0)
    widget_x = canvas._origin.x() + target_image_point[0] * canvas._scale
    widget_y = canvas._origin.y() + target_image_point[1] * canvas._scale

    canvas.controller.begin_stroke()
    canvas._paint_at(QPointF(widget_x, widget_y))
    canvas.controller.end_stroke()

    painted = np.argwhere(canvas.controller.mask > 0.5)
    assert len(painted) > 0
    center = painted.mean(axis=0)  # (row, col) moyen du trait peint
    assert center[0] == pytest.approx(target_image_point[1], abs=1.0)
    assert center[1] == pytest.approx(target_image_point[0], abs=1.0)


def test_ai_point_added_maps_correctly_when_zoomed(canvas, qapp):
    canvas.tool = "ai"
    canvas.zoom_to_fit()
    canvas.zoom_by_factor(4.0)

    target_image_point = (55.0, 22.0)
    widget_x = canvas._origin.x() + target_image_point[0] * canvas._scale
    widget_y = canvas._origin.y() + target_image_point[1] * canvas._scale

    received = []
    canvas.ai_point_added.connect(lambda x, y, positive: received.append((x, y, positive)))

    from PySide6.QtCore import QEvent
    from PySide6.QtCore import Qt as QtNS
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(widget_x, widget_y),
        QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.LeftButton,
        QtNS.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(event)

    assert len(received) == 1
    x, y, positive = received[0]
    assert x == pytest.approx(target_image_point[0], abs=1e-3)
    assert y == pytest.approx(target_image_point[1], abs=1e-3)
    assert positive is True


def test_resize_while_not_fit_mode_keeps_widget_center_image_point(canvas):
    """`resize()` seul ne garantit pas la livraison synchrone de
    resizeEvent sur un widget headless sans parent -- on construit et
    livre l'evenement explicitement pour un test deterministe."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    canvas.zoom_to_fit()
    canvas.zoom_by_factor(3.0)  # sort du mode "Ajuster"
    assert canvas._fit_mode is False

    old_size = QSize(canvas.width(), canvas.height())
    old_center = QPointF(old_size.width() / 2.0, old_size.height() / 2.0)
    image_at_center_before = canvas._widget_to_image_xy(old_center)

    new_size = QSize(600, 500)
    canvas.resize(new_size)
    canvas.resizeEvent(QResizeEvent(new_size, old_size))

    new_center = QPointF(new_size.width() / 2.0, new_size.height() / 2.0)
    image_at_center_after = canvas._widget_to_image_xy(new_center)
    assert image_at_center_after[0] == pytest.approx(image_at_center_before[0], abs=1.0)
    assert image_at_center_after[1] == pytest.approx(image_at_center_before[1], abs=1.0)
