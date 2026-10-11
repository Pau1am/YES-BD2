"""每日精炼: the refine page's single 精炼 pill is found by its lightning icon.

Leo 2026-10-11 「第二張圖也可以認雷電圖案」 on his 4K 精炼装备分数 page: the
single-refine pill starts with a yellow lightning, 连续精炼 with a white gear.
Only used when the text is not read; the press keeps all its checks.

The fixture is the page's button bar only (x 1150-1810, y 960-1050 at 1080).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.GearTasks import DailyRefineTask, refine_lightning_point

BAR = Path(__file__).parent / "fixtures" / "refine" / "refine_page_buttons_4k_at_1080.png"
# The lightning icon's centre on that page (1080 coordinates).
LIGHTNING = (1435, 1006)


def page(height=1080, keep_right=True):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    bar = cv2.imread(str(BAR))
    if not keep_right:
        bar = bar.copy()
        bar[:, 260:] = 0  # 连续精炼 only
    frame[960 : 960 + bar.shape[0], 1150 : 1150 + bar.shape[1]] = bar
    if height != 1080:
        frame = cv2.resize(frame, (height * 16 // 9, height), interpolation=cv2.INTER_CUBIC)
    return frame


class LightningTest(unittest.TestCase):
    def test_found_at_every_size(self):
        for height in (1080, 1440, 2160):
            with self.subTest(height=height):
                x, y = refine_lightning_point(page(height))
                scale = height / 1080
                self.assertAlmostEqual(LIGHTNING[0], x / scale, delta=4)
                self.assertAlmostEqual(LIGHTNING[1], y / scale, delta=4)

    def test_darker_or_lighter(self):
        for alpha, beta in ((0.75, 0), (1.0, 30)):
            with self.subTest(alpha=alpha, beta=beta):
                frame = cv2.convertScaleAbs(page(), alpha=alpha, beta=beta)
                self.assertIsNotNone(refine_lightning_point(frame))

    def test_the_gear_of_continuous_refine_is_not_taken(self):
        self.assertIsNone(refine_lightning_point(page(keep_right=False)))
        self.assertIsNone(refine_lightning_point(np.zeros((1080, 1920, 3), np.uint8)))

    def test_unread_text_presses_the_lightning_through_the_usual_checks(self):
        task = object.__new__(DailyRefineTask)
        task.info = {}
        task.info_set = lambda key, value: task.info.__setitem__(key, value)
        task.logs = []
        task.log_info = task.logs.append
        task.capture_frame = lambda: page(2160)
        unread = [SimpleNamespace(name="连续精炼", x=0, y=0, width=1, height=1)]
        task._wait_boxes = lambda *_a, **_k: unread
        pressed = []
        task._press_refine_once = lambda box: pressed.append(box) or "refined"
        task._back_to_bag = lambda outcome: outcome
        self.assertEqual("refined", task._refine_on_page())
        (box,) = pressed
        self.assertAlmostEqual(LIGHTNING[0] * 2, box.x + box.width / 2, delta=8)
        self.assertTrue(any("雷电图示" in line for line in task.logs))


if __name__ == "__main__":
    unittest.main()
