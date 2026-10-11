"""爛装强化分解: a fully enhanced item is never picked (Leo 2026-10-11, real run
on his 4K PC: 「我那件SR右下有標誌 你怎麼去點他」「那件裝備都強化滿了」).

His 顶级英雄盔甲 SR shows its refine level 「15」 in a diamond on the grid and
in the popup.  The grid OCR read nothing there and the popup name has no
「+N」, so the item was taken as +0, opened and picked.  The older tests fed
OCR boxes only and had no frame with a diamond the OCR misses.  Frames: the
real bag and popups of that run, 2026-10-11.
"""

import unittest
from pathlib import Path

import cv2
import numpy as np

from src.tasks.GearTasks import GRID_COLUMNS, GRID_ROWS
from src.tasks.JunkGearTask import JunkGearTask, popup_level_shown
from src.utils.junk_gear import badge_shown

FIXTURES = Path(__file__).parent / "fixtures" / "junk_gear"
GRID_AT = (700, 150)
POPUP_AT = (1300, 580)


def _frame(name, at):
    crop = cv2.imread(str(FIXTURES / name))
    frame = np.zeros((1080, 1920, 3), np.uint8)
    x, y = at
    frame[y : y + crop.shape[0], x : x + crop.shape[1]] = crop
    return frame


def _centre(cell):
    row, column = cell
    return GRID_COLUMNS[column], GRID_ROWS[row]


class GridBadgeTest(unittest.TestCase):
    def test_every_number_on_the_sr_grid_is_seen(self):
        frame = _frame("grid_sr_badges_leo_4k_at_1080.jpg", GRID_AT)
        # Row 1: 14 15 14 18 10 13 +7, then a sword with no number.
        shown = [badge_shown(frame, _centre((0, column))) for column in range(8)]
        self.assertEqual([True] * 7 + [False], shown)
        # Row 2: locked 翼角头盔, 劲弩, 猎人之弓, none with a number.
        self.assertEqual(
            [False, False, False], [badge_shown(frame, _centre((1, c))) for c in range(3)]
        )

    def test_plain_r_items_show_no_number(self):
        frame = _frame("grid_r_no_badges_leo_4k_at_1080.jpg", GRID_AT)
        self.assertFalse(any(badge_shown(frame, _centre((0, c))) for c in range(8)))

    def test_the_15_armour_is_kept_even_when_the_ocr_read_nothing(self):
        frame = _frame("grid_sr_badges_leo_4k_at_1080.jpg", GRID_AT)
        self.assertEqual("已强化", JunkGearTask._older_cell_kept(frame, (0, 1), set()))


class PopupLevelTest(unittest.TestCase):
    def test_the_refine_level_in_the_popup_diamond(self):
        self.assertTrue(popup_level_shown(_frame("popup_level_15_leo_4k_at_1080.png", POPUP_AT)))

    def test_an_empty_diamond_is_plus_0(self):
        self.assertFalse(
            popup_level_shown(_frame("popup_level_empty_leo_4k_at_1080.png", POPUP_AT))
        )


if __name__ == "__main__":
    unittest.main()
