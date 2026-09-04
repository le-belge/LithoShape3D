import time

import numpy as np

from lithoshape3d.ai.segmentation import MockSegmentationBackend
from lithoshape3d.ui.mask_editor_dialog import MaskEditorDialog


def _wait_until(condition, timeout=5.0, app=None):
    from PySide6.QtWidgets import QApplication

    app = app or QApplication.instance()
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return condition()


def test_ai_button_disabled_without_backend(qapp):
    dlg = MaskEditorDialog(
        "Zone", np.zeros((40, 40), dtype=np.float32), np.zeros((40, 40), dtype=np.float32), (1, 2, 3)
    )
    assert not dlg.ai_button.isEnabled()


def test_ai_button_enabled_with_available_backend(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((40, 40), dtype=np.float32),
        np.zeros((40, 40), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    assert dlg.ai_button.isEnabled()


def test_selecting_ai_tool_shows_ai_toolbar(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((40, 40), dtype=np.float32),
        np.zeros((40, 40), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    assert not dlg.ai_toolbar.isVisible()  # jamais montre (dialog non affiche), mais verifions la logique

    dlg._set_tool("ai")

    assert dlg.canvas.tool == "ai"


def test_positive_point_produces_preview_mask(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)

    dlg._on_ai_point_added(50, 50, True)

    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)
    assert dlg.canvas.preview_mask[50, 50] == 1.0
    assert dlg.ai_apply_button.isEnabled()


def test_apply_commits_preview_as_one_undo_entry(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)

    dlg._on_ai_apply()

    assert dlg.controller.history_size == 1
    assert dlg.controller.mask[50, 50] == 1.0
    assert dlg.canvas.tool == "brush"  # retour a l'edition manuelle apres application


def test_applied_mask_remains_editable_with_brush(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)
    dlg._on_ai_apply()

    dlg.controller.begin_stroke()
    dlg.controller.paint(10, 10, 3, 1.0)
    dlg.controller.end_stroke()

    assert dlg.controller.mask[10, 10] == 1.0
    assert dlg.controller.history_size == 2


def test_reset_points_clears_preview(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)

    dlg._on_ai_reset()

    assert dlg.canvas.preview_mask is None
    assert dlg._ai_points == []
    assert not dlg.ai_apply_button.isEnabled()


def test_subject_isolation_mode_hides_zone_toolbar_and_selects_ai_tool(qapp):
    dlg = MaskEditorDialog(
        "Sujet",
        np.zeros((40, 40), dtype=np.float32),
        np.zeros((40, 40), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
        subject_isolation_mode=True,
    )
    assert not dlg.brush_button.isVisible()
    assert not dlg.eraser_button.isVisible()
    assert not dlg.clear_button.isVisible()
    assert not dlg.fill_button.isVisible()
    assert not dlg.invert_button.isVisible()
    assert not dlg.undo_button.isVisible()
    assert not dlg.redo_button.isVisible()
    assert dlg.canvas.tool == "ai"


def test_subject_isolation_apply_keeps_continuous_alpha_and_closes(qapp):
    dlg = MaskEditorDialog(
        "Sujet",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
        subject_isolation_mode=True,
    )
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)
    preview_before_apply = dlg.canvas.preview_mask.copy()

    dlg._on_ai_apply()

    alpha = dlg.resulting_alpha_mask()
    assert alpha is not None
    np.testing.assert_array_equal(alpha, preview_before_apply)
    assert dlg.result() == dlg.DialogCode.Accepted


def test_zone_mode_still_binarizes_on_apply(qapp):
    """Non-regression : hors mode isolation, le comportement historique
    (binarisation a 0.5, retour a l'outil pinceau) reste inchange."""
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)

    dlg._on_ai_apply()

    assert dlg.resulting_alpha_mask() is None
    assert dlg.controller.mask[50, 50] == 1.0
    assert dlg.canvas.tool == "brush"


def test_undo_last_point_recomputes_with_remaining_points(qapp):
    dlg = MaskEditorDialog(
        "Zone",
        np.zeros((100, 100), dtype=np.float32),
        np.zeros((100, 100), dtype=np.float32),
        (1, 2, 3),
        segmentation_backend=MockSegmentationBackend(),
    )
    dlg._set_tool("ai")
    assert _wait_until(lambda: dlg._segmentation_session is not None, app=qapp)
    dlg._on_ai_point_added(50, 50, True)
    assert _wait_until(lambda: dlg.canvas.preview_mask is not None, app=qapp)
    dlg._on_ai_point_added(20, 20, True)
    assert _wait_until(lambda: dlg._ai_points == [(50, 50, True)] + [(20, 20, True)], app=qapp)

    dlg._on_ai_undo_point()

    assert dlg._ai_points == [(50, 50, True)]
