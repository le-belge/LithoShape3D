"""Logique d'edition de masque : pinceau/gomme/fill/clear/invert + undo/redo.

Pur Python/NumPy, aucune dependance Qt : testable sans interface, comme
`worker.py`/`state.py`. Le widget (`mask_editor_dialog.py`) ne fait que
traduire les evenements souris en appels ici et redessiner `self.mask`.

Regle undo/redo : une action souris complete (un trait de pinceau/gomme) est
une seule entree d'historique, qui ne stocke que le rectangle englobant
reellement modifie (pas le masque entier). Fill/Clear/Invert sont des
operations globales rares : une copie complete y est acceptable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

MAX_HISTORY = 50


@dataclass
class _Edit:
    bounds: tuple[int, int, int, int]  # y0, y1, x0, x1 (fin exclusive)
    before: np.ndarray
    after: np.ndarray


class MaskEditController:
    def __init__(self, mask: np.ndarray) -> None:
        self.mask = np.ascontiguousarray(mask, dtype=np.float32).copy()
        self._undo_stack: deque[_Edit] = deque(maxlen=MAX_HISTORY)
        self._redo_stack: deque[_Edit] = deque(maxlen=MAX_HISTORY)
        self._stroke_active = False
        self._stroke_before: np.ndarray | None = None
        self._stroke_bounds: tuple[int, int, int, int] | None = None

    # ------------------------------------------------------------------ #
    # Pinceau / gomme (trait = une seule entree undo)
    # ------------------------------------------------------------------ #
    def begin_stroke(self) -> None:
        self._stroke_active = True
        self._stroke_before = self.mask.copy()
        self._stroke_bounds = None

    def paint(self, x: int, y: int, radius: int, value: float) -> None:
        if not self._stroke_active:
            raise RuntimeError("begin_stroke() doit etre appele avant paint()")

        rows, cols = self.mask.shape
        y0, y1 = max(0, y - radius), min(rows, y + radius + 1)
        x0, x1 = max(0, x - radius), min(cols, x + radius + 1)
        if y0 >= y1 or x0 >= x1:
            return

        yy, xx = np.ogrid[y0:y1, x0:x1]
        circle = (yy - y) ** 2 + (xx - x) ** 2 <= radius**2
        region = self.mask[y0:y1, x0:x1]
        region[circle] = value

        self._accumulate_stroke_bounds(y0, y1, x0, x1)

    def _accumulate_stroke_bounds(self, y0: int, y1: int, x0: int, x1: int) -> None:
        if self._stroke_bounds is None:
            self._stroke_bounds = (y0, y1, x0, x1)
            return
        by0, by1, bx0, bx1 = self._stroke_bounds
        self._stroke_bounds = (min(by0, y0), max(by1, y1), min(bx0, x0), max(bx1, x1))

    def end_stroke(self) -> None:
        if not self._stroke_active:
            return
        self._stroke_active = False

        if self._stroke_bounds is not None and self._stroke_before is not None:
            y0, y1, x0, x1 = self._stroke_bounds
            before_region = self._stroke_before[y0:y1, x0:x1].copy()
            after_region = self.mask[y0:y1, x0:x1].copy()
            if not np.array_equal(before_region, after_region):
                self._push_undo(_Edit((y0, y1, x0, x1), before_region, after_region))

        self._stroke_before = None
        self._stroke_bounds = None

    # ------------------------------------------------------------------ #
    # Operations globales (copie complete acceptable, actions rares)
    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        self._apply_whole_mask(np.zeros_like(self.mask))

    def fill(self) -> None:
        self._apply_whole_mask(np.ones_like(self.mask))

    def invert(self) -> None:
        self._apply_whole_mask(1.0 - self.mask)

    def apply_external_mask(self, mask: np.ndarray) -> None:
        """Applique un masque externe (ex. proposition de selection
        intelligente) comme UNE seule entree undo -- pinceau/gomme restent
        utilisables normalement ensuite pour corriger le resultat."""
        if mask.shape != self.mask.shape:
            raise ValueError("le masque externe doit avoir la meme forme que le masque courant")
        self._apply_whole_mask(mask)

    def _apply_whole_mask(self, new_mask: np.ndarray) -> None:
        before = self.mask.copy()
        self.mask = new_mask.astype(np.float32)
        rows, cols = self.mask.shape
        self._push_undo(_Edit((0, rows, 0, cols), before, self.mask.copy()))

    # ------------------------------------------------------------------ #
    # Undo / Redo
    # ------------------------------------------------------------------ #
    def _push_undo(self, edit: _Edit) -> None:
        self._undo_stack.append(edit)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        edit = self._undo_stack.pop()
        y0, y1, x0, x1 = edit.bounds
        self.mask[y0:y1, x0:x1] = edit.before
        self._redo_stack.append(edit)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        edit = self._redo_stack.pop()
        y0, y1, x0, x1 = edit.bounds
        self.mask[y0:y1, x0:x1] = edit.after
        self._undo_stack.append(edit)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def history_size(self) -> int:
        return len(self._undo_stack)
