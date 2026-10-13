"""One shared way to close popups; the way home steps back with Esc.

Leo 2026-10-12: 「共用彈窗處理」, 「建議還是逐步回主頁 連按也可以 但這遊戲按沒幾下
就會變成問你要不要關閉遊戲 所以根本不用連按」.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.tasks import recovery
from src.utils import known_popups


def _box(name, x=100, y=100):
    return SimpleNamespace(name=name, x=x, y=y, width=40, height=20)


def _boxes(*names):
    return [_box(name, x=100 + 60 * i) for i, name in enumerate(names)]


class PickTest(unittest.TestCase):
    def test_mid_task_never_cancels(self):
        self.assertIsNone(known_popups.pick(_boxes("是否使用", "取消", "确认")))

    def test_way_home_may_cancel(self):
        press = known_popups.pick(_boxes("是否使用", "取消", "确认"), allow_cancel=True)
        self.assertEqual(press.label, "取消")

    def test_purchase_confirm_is_never_picked(self):
        self.assertIsNone(known_popups.pick(_boxes("是否购买", "消耗 100 钻石", "确认")))

    def test_reward_overlays_and_info_confirms(self):
        self.assertEqual(known_popups.pick(_boxes("赛季奖励", "点击画面即可返回")).label, "点击画面即可返回")
        self.assertEqual(known_popups.pick(_boxes("获得道具", "确认")).label, "确认")
        self.assertEqual(known_popups.pick(_boxes("公告", "关闭")).label, "关闭")

    def test_quit_dialog_is_cancelled_even_mid_task_never_confirmed(self):
        boxes = _boxes("是否退出游戏？", "取消", "确认")
        self.assertTrue(known_popups.is_quit_dialog(boxes))
        press = known_popups.pick(boxes)
        self.assertEqual(press.label, "取消")
        self.assertIs(press.box, boxes[1])

    def test_quit_words_without_cancel_or_without_game_are_not_quit(self):
        self.assertFalse(known_popups.is_quit_dialog(_boxes("是否退出游戏？", "确认")))
        self.assertFalse(known_popups.is_quit_dialog(_boxes("退出公会", "取消")))


class QuitDialogOnTheWayHomeTest(unittest.TestCase):
    def test_quit_dialog_is_cancelled_and_reported(self):
        clicks = []
        task = SimpleNamespace(
            capture_frame=lambda: np.zeros((1080, 1920, 3), np.uint8),
            log_info=lambda *a, **k: None,
            operate_click=lambda x, y, after_sleep=0: clicks.append((x, y)),
            _ocr_box_center=lambda box: (box.x + 20, box.y + 10),
        )
        vision = SimpleNamespace(ocr_boxes=lambda frame, name: _boxes("要关闭游戏吗", "取消", "确认"))
        self.assertEqual("quit", recovery._handle_dialog(task, vision))
        self.assertEqual(clicks, [((160 + 20) / 1920, 110 / 1080)])


class EscapeStepTest(unittest.TestCase):
    """Back arrow does nothing → H → one Esc at a time, never after the quit dialog."""

    def _run(self, dialogs, home_after_presses=None):
        events = []
        frame = np.full((1080, 1920, 3), 120, np.uint8)
        home = {"now": False}
        navigator = SimpleNamespace(
            _home_confirmation_signals=lambda f: (home["now"], 0, 0, ""),
            vision=SimpleNamespace(capture=lambda: frame),
            classify=lambda frame=None: recovery.ScreenState.UNKNOWN,
            clear_home_announcement=lambda f: False,
        )
        outcomes = list(dialogs)

        def press(name):
            events.append(name)
            if home_after_presses is not None and len(events) >= home_after_presses:
                home["now"] = True
            return True

        task = SimpleNamespace(
            info_set=lambda *a: None,
            log_info=lambda *a, **k: None,
            sleep=lambda s: None,
            operate_click=lambda x, y, after_sleep=0: press("back"),
            tap_key=lambda key, after_sleep=0: press(key),
            tap_escape=lambda after_sleep=0: press("esc"),
        )
        with mock.patch.object(recovery, "Vision", lambda t: navigator.vision), mock.patch.object(
            recovery, "Navigator", lambda t, v: navigator
        ), mock.patch.object(
            recovery, "_handle_dialog", lambda t, v: outcomes.pop(0) if outcomes else "none"
        ), mock.patch.object(recovery, "_note_leaving_step", lambda *a: None), mock.patch.object(
            recovery, "_keep_failure_picture", lambda *a: None
        ), mock.patch.object(recovery, "BACK_HOME_WAIT_SECONDS", 0.0), mock.patch.object(
            recovery, "UNKNOWN_SETTLE_SECONDS", 0.0
        ):
            result = recovery.recover_to_home(task)
        return result, events

    def test_esc_follows_a_back_arrow_that_changed_nothing(self):
        result, events = self._run([], home_after_presses=3)
        self.assertTrue(result)
        self.assertEqual(events, ["back", "H", "esc"])

    def test_esc_is_pressed_one_at_a_time_and_at_most_three_times(self):
        result, events = self._run([])
        self.assertFalse(result)
        self.assertEqual(events.count("esc"), recovery.ESCAPE_STEPS_MAX)
        # Never two Esc in a row: the back arrow is tried between them.
        self.assertNotIn(["esc", "esc"], [events[i : i + 2] for i in range(len(events) - 1)])

    def test_no_more_esc_after_the_quit_dialog(self):
        # The first Esc brings the quit dialog; it is cancelled, Esc stops.
        result, events = self._run(["none", "none", "none", "quit"])
        self.assertFalse(result)
        self.assertEqual(events.count("esc"), 1)


if __name__ == "__main__":
    unittest.main()
