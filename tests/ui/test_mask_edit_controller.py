import numpy as np
import pytest

from lithoshape3d.ui.mask_edit_controller import MAX_HISTORY, MaskEditController


def _empty_controller(shape=(20, 20)) -> MaskEditController:
    return MaskEditController(np.zeros(shape, dtype=np.float32))


def _paint_stroke(controller: MaskEditController, points, radius=2, value=1.0) -> None:
    controller.begin_stroke()
    for x, y in points:
        controller.paint(x, y, radius, value)
    controller.end_stroke()


def test_paint_sets_values_within_radius():
    controller = _empty_controller()
    _paint_stroke(controller, [(10, 10)], radius=3, value=1.0)

    assert controller.mask[10, 10] == 1.0
    assert controller.mask[10, 13] == 1.0  # bord du cercle
    assert controller.mask[0, 0] == 0.0  # hors du trait


def test_eraser_sets_zero():
    controller = MaskEditController(np.ones((20, 20), dtype=np.float32))
    _paint_stroke(controller, [(5, 5)], radius=2, value=0.0)

    assert controller.mask[5, 5] == 0.0
    assert controller.mask[19, 19] == 1.0


def test_paint_requires_begin_stroke():
    controller = _empty_controller()
    with pytest.raises(RuntimeError):
        controller.paint(1, 1, 1, 1.0)


def test_one_stroke_is_one_undo_entry():
    controller = _empty_controller()
    _paint_stroke(controller, [(5, 5), (6, 6), (7, 7)], radius=1, value=1.0)

    assert controller.history_size == 1


def test_undo_reverts_stroke():
    controller = _empty_controller()
    _paint_stroke(controller, [(10, 10)], radius=2, value=1.0)
    assert controller.mask[10, 10] == 1.0

    controller.undo()

    assert controller.mask[10, 10] == 0.0
    assert not controller.can_undo


def test_redo_reapplies_stroke():
    controller = _empty_controller()
    _paint_stroke(controller, [(10, 10)], radius=2, value=1.0)
    controller.undo()

    controller.redo()

    assert controller.mask[10, 10] == 1.0
    assert not controller.can_redo


def test_new_action_after_undo_clears_redo_stack():
    controller = _empty_controller()
    _paint_stroke(controller, [(2, 2)], radius=1, value=1.0)
    controller.undo()
    assert controller.can_redo

    _paint_stroke(controller, [(15, 15)], radius=1, value=1.0)

    assert not controller.can_redo


def test_undo_without_history_is_a_no_op():
    controller = _empty_controller()
    controller.undo()  # ne doit pas lever
    assert np.all(controller.mask == 0.0)


def test_redo_without_history_is_a_no_op():
    controller = _empty_controller()
    controller.redo()  # ne doit pas lever
    assert np.all(controller.mask == 0.0)


def test_clear_fill_invert_are_undoable():
    controller = MaskEditController(np.zeros((10, 10), dtype=np.float32))

    controller.fill()
    assert np.all(controller.mask == 1.0)

    controller.clear()
    assert np.all(controller.mask == 0.0)

    controller.undo()  # annule clear -> retour a fill (tout 1.0)
    assert np.all(controller.mask == 1.0)

    controller.invert()
    assert np.all(controller.mask == 0.0)


def test_history_is_bounded_to_max_entries():
    controller = _empty_controller(shape=(5, 5))

    for i in range(MAX_HISTORY + 10):
        controller.begin_stroke()
        controller.paint(i % 5, (i * 2) % 5, radius=0, value=float(i % 2))
        controller.end_stroke()

    assert controller.history_size <= MAX_HISTORY


def test_apply_external_mask_is_one_undo_entry():
    controller = _empty_controller(shape=(10, 10))
    external = np.zeros((10, 10), dtype=np.float32)
    external[2:5, 2:5] = 1.0

    controller.apply_external_mask(external)

    assert controller.history_size == 1
    assert np.array_equal(controller.mask, external)


def test_apply_external_mask_can_be_corrected_with_brush_afterward():
    controller = _empty_controller(shape=(10, 10))
    external = np.zeros((10, 10), dtype=np.float32)
    external[2:5, 2:5] = 1.0
    controller.apply_external_mask(external)

    _paint_stroke(controller, [(8, 8)], radius=1, value=1.0)

    assert controller.mask[8, 8] == 1.0
    assert controller.history_size == 2


def test_apply_external_mask_rejects_mismatched_shape():
    controller = _empty_controller(shape=(10, 10))
    with pytest.raises(ValueError):
        controller.apply_external_mask(np.zeros((5, 5), dtype=np.float32))


def test_stroke_with_no_actual_change_does_not_push_history():
    controller = MaskEditController(np.ones((10, 10), dtype=np.float32))
    _paint_stroke(controller, [(3, 3)], radius=1, value=1.0)  # deja a 1.0 partout

    assert controller.history_size == 0
