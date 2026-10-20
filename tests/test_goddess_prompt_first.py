"""广场女神像: wish when the prompt is already up though the daily row is unread.

A player's 问题摘要 (v0.1.21, 1920×1080 windowed, 2026-10-11): 「未确认每日导航」
while the character stood at the goddess with 「向女神像许愿」 shown; the daily
row sat over the pink food truck and OCR did not read it.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.tasks import SquareGoddessTask as goddess_module
from src.tasks.SquareGoddessTask import SquareGoddessTask


def make_task(prompts, *, navigation=None, wished=False):
    """``prompts``: the prayer prompt's point per frame (None = not shown)."""
    task = object.__new__(SquareGoddessTask)
    task.config = {}
    task.info_set = lambda *_a, **_k: None
    task.logs = []
    task.log_info = lambda message, **_k: task.logs.append(message)
    task.sleep = lambda *_a: None
    task.stages = []
    task._click_square_notice_if_present = lambda **_k: False
    task._click_goddess_daily_navigation_until = lambda **_k: navigation
    task._wished_today = lambda: wished
    task._wait_for_goddess_prayer_completion = (
        lambda **_k: task.stages.append("pray") or True
    )
    frames = list(prompts)
    task.capture_frame = lambda: SimpleNamespace(
        point=frames.pop(0) if len(frames) > 1 else frames[0]
    )
    task._ocr_pattern_click_point = lambda frame, *_a, **_k: (frame.point, "")
    task._press_row_where_it_usually_is = lambda: False
    task._walk_by_key = lambda: False
    return task


class PromptFirstTest(unittest.TestCase):
    def test_the_players_case_wishes_from_the_prompt(self):
        task = make_task([(830, 630), (832, 631)])
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual(["pray"], task.stages)
        self.assertTrue(any("直接许愿" in line for line in task.logs))

    def test_one_frame_with_the_prompt_is_not_enough(self):
        task = make_task([(830, 630), None])
        self.assertFalse(task._pray_at_goddess())
        self.assertEqual([], task.stages)

    def test_a_prompt_that_jumps_is_not_steady(self):
        task = make_task([(830, 630), (1300, 200)])
        self.assertFalse(task._pray_at_goddess())

    def test_no_prompt_and_no_row_still_stops(self):
        task = make_task([None])
        self.assertFalse(task._pray_at_goddess())
        self.assertEqual([], task.stages)

    def test_wished_today_without_a_prompt_is_still_done(self):
        task = make_task([None], wished=True)
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual([], task.stages)

    def test_a_clicked_row_does_not_look_for_the_prompt_first(self):
        from src.tasks.SquareGoddessTask import GODDESS_NAVIGATION_CLICKED

        task = make_task([None], navigation=GODDESS_NAVIGATION_CLICKED)
        task._prayer_prompt_steady = lambda: self.fail("row clicked: no extra look")
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual(["pray"], task.stages)


class BlindRowPressTest(unittest.TestCase):
    """Leo: 「讀不到 不是應該還是嘗試用滑鼠點一下嗎 點到就有 沒點到不會損失甚麼」."""

    def _task(self, after_press):
        task = make_task([None])
        del task._press_row_where_it_usually_is
        task.clicks = []
        screens = list(after_press)
        task.capture_frame = lambda: SimpleNamespace(shape=(1080, 1920, 3))

        def read(_frame, *_a, **_k):
            if not task.clicks:
                return None, ""
            return screens.pop(0) if len(screens) > 1 else screens[0]

        task._ocr_pattern_click_point = read
        task._click_client = lambda x, y, w, h, after_sleep=0: task.clicks.append((x, y))
        return task

    def test_a_walk_after_the_press_goes_on_to_pray(self):
        task = self._task([(None, "自动移动中：艾力克史温女神像")])
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual([(1678, 228)], task.clicks)
        self.assertEqual(["pray"], task.stages)

    def test_the_prompt_after_the_press_goes_on_to_pray(self):
        task = self._task([(None, ""), ((830, 630), "向女神像许愿")])
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual(["pray"], task.stages)

    def test_nothing_after_the_press_stops_after_one_press(self):
        task = self._task([(None, "")])
        with mock.patch.object(goddess_module, "GODDESS_ROW_PRESS_CONFIRM_SECONDS", 0.0):
            self.assertFalse(task._pray_at_goddess())
        self.assertEqual(1, len(task.clicks))
        self.assertEqual([], task.stages)

    def test_wished_today_does_not_press(self):
        task = self._task([(None, "")])
        task._wished_today = lambda: True
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual([], task.clicks)


class RowKeyTest(unittest.TestCase):
    """Leo 2026-10-20: 「點 E 會走到女神像」 when the daily row is unread."""

    def _task(self, after_key, key_sent=True):
        task = make_task([None])
        del task._walk_by_key
        task.keys = []
        screens = list(after_key)
        task.capture_frame = lambda: SimpleNamespace(shape=(1080, 1920, 3))

        def read(_frame, *_a, **_k):
            if not task.keys:
                return None, ""
            return screens.pop(0) if len(screens) > 1 else screens[0]

        task._ocr_pattern_click_point = read
        task.tap_key = lambda key, after_sleep=0: task.keys.append(key) or key_sent
        task._press_row_where_it_usually_is = lambda: task.stages.append("blind") or False
        return task

    def test_e_starts_the_walk_before_the_blind_press(self):
        task = self._task([(None, "自动移动中：艾力克史温女神像")])
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual(["E"], task.keys)
        self.assertEqual(["pray"], task.stages)

    def test_e_without_a_walk_goes_on_to_the_blind_press(self):
        task = self._task([(None, "")])
        with mock.patch.object(goddess_module, "GODDESS_ROW_PRESS_CONFIRM_SECONDS", 0.0):
            self.assertFalse(task._pray_at_goddess())
        self.assertEqual(["E"], task.keys)
        self.assertEqual(["blind"], task.stages)

    def test_a_clicked_row_never_sends_e(self):
        from src.tasks.SquareGoddessTask import GODDESS_NAVIGATION_CLICKED

        task = self._task([(None, "")])
        task._click_goddess_daily_navigation_until = lambda **_k: GODDESS_NAVIGATION_CLICKED
        self.assertTrue(task._pray_at_goddess())
        self.assertEqual([], task.keys)


if __name__ == "__main__":
    unittest.main()
