"""活动每日战斗: the mode buttons are found by their crossed-swords icons.

Leo 2026-10-11, on his 4K hub frame (Loyal Maid event): 「沒辨識到也可以認圖片
左邊都是普通戰鬥 右邊是挑戰戰鬥」「那個兩把劍的圖片」「白色部分」.  When the names
are not read the swords tell the two modes apart; when neither shows the label's
usual spot is pressed once and the stage page must follow.

The fixture is the hub's button band only (no names or ids), cut from Leo's
3840x2160 frame and scaled to 1080 (x 280-1640, y 740-1060).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.EventBattleTask import (
    CHALLENGE_MODE,
    MODE_USUAL_POINTS,
    NORMAL_MODE,
    EventBattleTask,
    mode_name_in,
    sword_icon_points,
)

BAND = Path(__file__).parent / "fixtures" / "event_battle" / "hub_buttons_loyal_maid_4k_at_1080.jpg"
BAND_AT = (280, 740)
# Label centres read off the same frame by OCR (普通战斗, 挑战战斗).
LABELS = {NORMAL_MODE: (678, 997), CHALLENGE_MODE: (865, 997)}


def hub_frame(height=1080, background=0):
    band = cv2.imread(str(BAND))
    frame = np.full((1080, 1920, 3), background, np.uint8)
    x, y = BAND_AT
    frame[y : y + band.shape[0], x : x + band.shape[1]] = band
    if height != 1080:
        frame = cv2.resize(frame, (height * 16 // 9, height), interpolation=cv2.INTER_CUBIC)
    return frame


def make_task(frame, boxes):
    task = object.__new__(EventBattleTask)
    task.config = {}
    task.info = {}
    task.info_set = lambda key, value: task.info.__setitem__(key, value)
    task.logs = []
    task.log_info = lambda text, *a, **k: task.logs.append(text)
    task.sleep = lambda *_a: None
    task._sleep_after_recognition = lambda: None
    task._enter_hub = lambda: "ok"
    task.capture_frame = lambda: frame
    task._roi_boxes = lambda _frame, _roi, _name: boxes
    task.clicks = []
    task._click_box = lambda button, after_sleep=0: task.clicks.append(button)
    task.opens = True
    task._wait_for_stage_page = (
        lambda mode, timeout=0, quiet=False: task.opens and bool(task.clicks)
    )
    task._wait_for_hub = lambda timeout=0: True
    return task


def centre(button):
    return (button.x + button.width / 2, button.y + button.height / 2)


class SwordIconTest(unittest.TestCase):
    def test_the_two_swords_are_found_left_normal_right_challenge(self):
        for height in (1080, 1440, 2160):
            with self.subTest(height=height):
                points = sword_icon_points(hub_frame(height))
                self.assertEqual(2, len(points))
                scale = height / 1080
                (nx, _), (cx, _) = points
                self.assertAlmostEqual(LABELS[NORMAL_MODE][0], nx / scale, delta=8)
                self.assertAlmostEqual(LABELS[CHALLENGE_MODE][0], cx / scale, delta=8)

    def test_darker_or_washed_out_screens_still_show_both(self):
        # HDR / filters: the white parts stay the brightest in the band.
        for alpha, beta in ((0.85, 0), (0.6, 0), (1.0, 25), (0.8, 40)):
            with self.subTest(alpha=alpha, beta=beta):
                frame = cv2.convertScaleAbs(hub_frame(), alpha=alpha, beta=beta)
                self.assertEqual(2, len(sword_icon_points(frame)))

    def test_no_swords_on_a_screen_without_them(self):
        self.assertEqual([], sword_icon_points(np.zeros((1080, 1920, 3), np.uint8)))
        white = np.full((1080, 1920, 3), 255, np.uint8)
        self.assertEqual([], sword_icon_points(white))

    def test_unread_names_press_the_label_under_the_right_swords(self):
        # OCR read none of the two names: the swords place 挑战战斗's label.
        story = SimpleNamespace(name="剧情", x=0, y=0, width=1, height=1)
        task = make_task(hub_frame(2160), [story])
        self.assertEqual("ok", task._open_mode(CHALLENGE_MODE))
        (pressed,) = task.clicks
        x, y = centre(pressed)
        self.assertAlmostEqual(LABELS[CHALLENGE_MODE][0] * 2, x, delta=16)
        self.assertAlmostEqual(LABELS[CHALLENGE_MODE][1] * 2, y, delta=24)
        self.assertTrue(any("双剑图示" in line for line in task.logs))

    def test_hub_counts_one_name_with_both_swords(self):
        self.assertTrue(EventBattleTask._hub_shown(hub_frame(), "剧情普通战斗魔兽追踪者"))
        blank = np.zeros((1080, 1920, 3), np.uint8)
        self.assertFalse(EventBattleTask._hub_shown(blank, "剧情普通战斗魔兽追踪者"))
        self.assertFalse(EventBattleTask._hub_shown(hub_frame(), "剧情魔兽追踪者"))


class UsualSpotTest(unittest.TestCase):
    def test_nothing_read_presses_the_usual_spot_once(self):
        blank = np.zeros((2160, 3840, 3), np.uint8)
        task = make_task(blank, [])
        self.assertEqual("ok", task._open_mode(CHALLENGE_MODE))
        (pressed,) = task.clicks
        x, y = MODE_USUAL_POINTS[CHALLENGE_MODE]
        self.assertEqual((x * 2, y * 2), centre(pressed))
        self.assertTrue(any("平常的位置" in line for line in task.logs))

    def test_the_usual_spot_that_opens_nothing_stops_with_why(self):
        task = make_task(np.zeros((1080, 1920, 3), np.uint8), [])
        task.opens = False
        self.assertEqual("failed", task._open_mode(CHALLENGE_MODE))
        self.assertEqual(1, len(task.clicks))
        self.assertIn("活动页里没找到「挑战战斗」", task._why)
        self.assertIn("照平常位置点了一下也没进关卡页", task._why)


class ModeNameTest(unittest.TestCase):
    def test_one_character_off_still_names_the_mode(self):
        for text in ("挑战战斗", "挑战战", "挑战战头", "剧情挑战战魔兽"):
            with self.subTest(text=text):
                self.assertTrue(mode_name_in(text, CHALLENGE_MODE))

    def test_the_other_mode_or_half_a_name_does_not(self):
        for text in ("普通战斗", "挑战", "战斗", "挑战任务"):
            with self.subTest(text=text):
                self.assertFalse(mode_name_in(text, CHALLENGE_MODE))
        self.assertFalse(mode_name_in("挑战战斗", NORMAL_MODE))


if __name__ == "__main__":
    unittest.main()
