"""每日精炼: 18-20 are tried first, the purple star backing the number.

Leo 2026-10-11 on his 4K bag: 「右下有數字就是強化滿的」「可以請程式先優先抓 18 19
20這三個」「18 19 20 底都是紫色」「以數字為主 有辨識到 18 19 20 就可以點開了 沒有的話
就點24(不包含24)以下的數字」.

The fixture is the item grid only (GRID_ROI), cut from his 3840x2160 frame and
scaled to 1080.
"""

import unittest
from pathlib import Path

import cv2
import numpy as np

from src.tasks.GearTasks import GRID_ROI, purple_badges, refine_candidate

GRID = Path(__file__).parent / "fixtures" / "refine" / "bag_grid_badges_4k_at_1080.jpg"
# The badge numbers on that screen, row by row.
VALUES = (
    (24, 24, 24, 24, 24, 18, 20, 22),
    (20, 20, 20, 19, 22, 20, 20, 24),
    (18, 18, 20, 19, 20, 18, 20, 20),
    (19, 18, 20, 12, 19, 18, 21, 18),
    (20, 18, 21, 21, 18, 18, 22, 18),
    (19, 9, 9, 20, 19, 19, 19, 18),
)
PURPLE = {(r, c) for r, row in enumerate(VALUES) for c, v in enumerate(row) if 18 <= v <= 20}


def bag_frame(height=1080):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    x, y, _w, _h = GRID_ROI
    grid = cv2.imread(str(GRID))
    frame[y : y + grid.shape[0], x : x + grid.shape[1]] = grid
    if height != 1080:
        frame = cv2.resize(frame, (height * 16 // 9, height), interpolation=cv2.INTER_CUBIC)
    return frame


class PurpleBadgeTest(unittest.TestCase):
    def test_exactly_the_18_to_20_badges_are_purple(self):
        for height in (1080, 1440, 2160):
            with self.subTest(height=height):
                self.assertEqual(PURPLE, purple_badges(bag_frame(height)))

    def test_darker_or_lighter_screens_still_match(self):
        # A miss only loses the preference (numbers still decide).
        for alpha, beta in ((0.8, 0), (1.0, 20)):
            with self.subTest(alpha=alpha, beta=beta):
                frame = cv2.convertScaleAbs(bag_frame(), alpha=alpha, beta=beta)
                self.assertEqual(PURPLE, purple_badges(frame))

    def test_nothing_purple_on_a_blank_screen(self):
        self.assertEqual(set(), purple_badges(np.zeros((1080, 1920, 3), np.uint8)))
        self.assertEqual(set(), purple_badges(None))


class CandidateOrderTest(unittest.TestCase):
    def test_18_to_20_with_purple_first(self):
        cells = [(0, 0, 22), (0, 5, 18), (1, 0, 20)]
        self.assertEqual((0, 5, 18), refine_candidate(cells, {(0, 5), (1, 0)}))

    def test_a_purple_cut_off_read_before_other_numbers(self):
        # 「8」 read off a purple 18 counts before a 22.
        self.assertEqual((2, 0, 8), refine_candidate([(0, 7, 22), (2, 0, 8)], {(2, 0)}))

    def test_without_18_to_20_any_number_below_24(self):
        self.assertEqual((0, 7, 22), refine_candidate([(0, 0, 24), (0, 7, 22)], set()))
        self.assertIsNone(refine_candidate([(0, 0, 24)], {(0, 0)}))

    def test_the_real_screen_picks_a_purple_18(self):
        cells = [(r, c, v) for r, row in enumerate(VALUES) for c, v in enumerate(row)]
        self.assertEqual((0, 5, 18), refine_candidate(cells, purple_badges(bag_frame(2160))))


if __name__ == "__main__":
    unittest.main()
