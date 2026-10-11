"""爛装强化分解 without the "!" gate (Leo 2026-10-11 「把！這個去掉」).

B站 渐崩渐晰: R gear from 抽抽乐 was never dismantled, two days running.
The front cells of the newest-first bag are now judged whether they carry
the "!" or not; those without it must show the not-worn slot icon and no
enhance badge.  Frames: Leo's 4K bag at 1080 reference, grid crop placed
back at its offset (700, 140).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.GearTasks import GRID_COLUMNS, GRID_ROWS
from src.utils.junk_gear import (
    GearItem,
    front_cells,
    load_exclusive_stars,
    slot_icon_scores,
    slot_icon_shown,
)

FIXTURES = Path(__file__).parent / "fixtures" / "junk_gear"


def _frame(name: str) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / name))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[140 : 140 + crop.shape[0], 700 : 700 + crop.shape[1]] = crop
    return frame


def _shown(frame, row, column) -> bool:
    return slot_icon_shown(frame, (GRID_COLUMNS[column], GRID_ROWS[row]))


class SlotIconTest(unittest.TestCase):
    def test_r_filter_worn_and_not_worn(self):
        frame = _frame("bag_r_leo_4k_at_1080.jpg")
        # c1 helmet and c3 necklace not worn; c2 armour and c4 glove worn.
        self.assertEqual(
            [True, False, True, False, False, False, False, False],
            [_shown(frame, 0, column) for column in range(8)],
        )

    def test_sr_filter(self):
        frame = _frame("bag_sr_leo_4k_at_1080.jpg")
        # Row 1: only c2 (armour, 15) not worn.  Row 2: c1 (locked mask)
        # and c3 (staff) not worn, c2 (bow) worn, the rest empty.
        self.assertEqual(
            [False, True, False, False, False, False, False, False],
            [_shown(frame, 0, column) for column in range(8)],
        )
        self.assertEqual(
            [True, False, True, False, False, False, False, False],
            [_shown(frame, 1, column) for column in range(8)],
        )

    def test_worn_ur_portraits_are_never_a_slot_icon(self):
        frame = _frame("bag_ur_leo_4k_at_1080.jpg")
        for row in range(4):
            for column in range(8):
                slate, ring = slot_icon_scores(frame, (GRID_COLUMNS[column], GRID_ROWS[row]))
                if ring >= 0.2:
                    with self.subTest(row=row, column=column):
                        self.assertFalse(_shown(frame, row, column))


class FrontCellsTest(unittest.TestCase):
    def test_first_cells_row_by_row(self):
        self.assertEqual(
            [(0, column) for column in range(8)] + [(1, 0), (1, 1)],
            front_cells(GRID_COLUMNS, GRID_ROWS, 10),
        )


class OlderCellsTest(unittest.TestCase):
    """Front cells of the filtered bag are judged only when not worn and not
    enhanced."""

    def _task(self, badged):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.config = {}
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        task.log_warning = lambda *a, **k: None
        task._badged_cells = lambda: badged
        task._grid_rarity = lambda frame, cell: "SR"
        task.sleep = lambda *a: None
        task._wait_detail = lambda *a, **k: True
        task.press_and_confirm = lambda label, do, confirmed, **k: do() or True
        task._click_reference = lambda *a, **k: None
        # Leo's real r2c3: 猎人之弓 SR, 莉兹内's (3★) exclusive (4K 2026-10-11).
        task._read_detail = lambda: (
            GearItem("猎人之弓", "SR", False, False, False, owner_line="莉兹内"), "专用装备"
        )
        return task

    def test_sr_filter_picks_only_the_unworn_unenhanced_unlocked(self):
        from unittest import mock

        frame = _frame("bag_sr_leo_4k_at_1080.jpg")
        cells = front_cells(GRID_COLUMNS, GRID_ROWS, 11)
        task = self._task({(0, 1), (0, 6)})
        with mock.patch(
            "src.tasks.JunkGearTask.grid_cell_locked", side_effect=lambda f, c, *a: c == (1, 0)
        ):
            junk = task._classify_cells(cells, load_exclusive_stars(), frame, grade="SR")
        # The RC thread's reading of Leo's SR bag: only r2c3 (staff) fits.
        self.assertEqual([(1, 2)], junk)

    def test_unread_grid_keeps_every_older_cell(self):
        frame = _frame("bag_r_leo_4k_at_1080.jpg")
        cells = front_cells(GRID_COLUMNS, GRID_ROWS, 4)
        task = self._task(None)
        self.assertEqual([], task._classify_cells(cells, {}, frame, grade="R"))

    def test_older_cell_with_unread_rarity_is_not_opened(self):
        frame = _frame("bag_r_leo_4k_at_1080.jpg")
        task = self._task(set())
        task._grid_rarity = lambda frame, cell: None
        task._wait_detail = lambda *a, **k: self.fail("detail opened")
        self.assertEqual([], task._classify_cells([(0, 0)], {}, frame, grade="R"))

    def test_badge_text_cells_reads_numbers_and_plus(self):
        from src.tasks.JunkGearTask import badge_text_cells

        def box(text, cx, cy):
            return SimpleNamespace(name=text, x=cx + 25, y=cy + 5, width=20, height=20)

        boxes = [
            box("15", GRID_COLUMNS[1], GRID_ROWS[0]),
            box("+7", GRID_COLUMNS[6], GRID_ROWS[0]),
            box("SR", GRID_COLUMNS[2], GRID_ROWS[0] - 70),
        ]
        self.assertEqual({(0, 1), (0, 6)}, badge_text_cells(boxes))


if __name__ == "__main__":
    unittest.main()
