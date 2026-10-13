"""The stuck-screen watch (Leo 2026-10-13 「點擊沒反應 或者辨識不到卡住 那就回主頁
可以的話就重試沒辦法就下一步」「不要整個卡死」)."""

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.tasks import BaseBD2Task as base_module
from src.utils.frozen_screen import (
    FROZEN_GAP_SECONDS,
    FROZEN_SCREEN_SECONDS,
    FrozenScreen,
    FrozenWatch,
)


def _screen(value=90):
    frame = np.full((1080, 1920, 3), value, np.uint8)
    frame[500:560, 900:1000] = 200
    return frame


class FrozenWatchTest(unittest.TestCase):
    def _look_every(self, watch, frames, step=1.0):
        now = 0.0
        for frame in frames:
            watch.look(frame, now)
            now += step
        return now

    def test_a_still_screen_raises_after_the_limit(self):
        watch = FrozenWatch()
        frame = _screen()
        looks = int(FROZEN_SCREEN_SECONDS)
        self._look_every(watch, [frame] * looks)  # up to just under the limit
        with self.assertRaises(FrozenScreen):
            watch.look(frame, FROZEN_SCREEN_SECONDS)
        with self.assertRaises(FrozenScreen):  # stays raised until the run ends
            watch.look(_screen(30), FROZEN_SCREEN_SECONDS + 1)

    def test_a_moving_screen_never_raises(self):
        watch = FrozenWatch()
        frames = []
        for i in range(60):
            frame = _screen()
            frame[100:104, 100 + 10 * i : 140 + 10 * i] = 255  # a spinner-sized change
            frames.append(frame)
        self._look_every(watch, frames)

    def test_a_press_starts_the_count_over(self):
        watch = FrozenWatch()
        frame = _screen()
        for second in range(int(FROZEN_SCREEN_SECONDS) - 1):
            watch.look(frame, float(second))
        watch.pressed()
        for second in range(int(FROZEN_SCREEN_SECONDS) - 1, 2 * int(FROZEN_SCREEN_SECONDS) - 2):
            watch.look(frame, float(second))

    def test_a_pause_between_looks_starts_the_count_over(self):
        # 暂停 holds the run in a sleep: no looks meanwhile.
        watch = FrozenWatch()
        frame = _screen()
        watch.look(frame, 0.0)
        watch.look(frame, FROZEN_SCREEN_SECONDS - 1)
        later = FROZEN_SCREEN_SECONDS - 1 + FROZEN_GAP_SECONDS + 1
        watch.look(frame, later)
        watch.look(frame, later + FROZEN_SCREEN_SECONDS - 1)

    def test_paused_while_going_home(self):
        watch = FrozenWatch()
        watch.paused = 1
        for second in range(3 * int(FROZEN_SCREEN_SECONDS)):
            watch.look(_screen(), float(second))


class RunWatchedTest(unittest.TestCase):
    def _task(self, retry):
        task_type = type("Task", (), {"frozen_retry": retry})
        task = task_type()
        task.name = "测试"
        task.log_warning = mock.Mock()
        task.log_info = mock.Mock()
        return task

    def test_a_frozen_run_goes_home_and_runs_once_more(self):
        task = self._task(retry=True)
        results = iter([FrozenScreen(), True])
        seen_watches = []

        def run(t):
            seen_watches.append(t._frozen_watch)
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch("src.tasks.recovery.recover_to_home", return_value=True) as home:
            self.assertTrue(base_module._run_watched(task, run, (), {}, watched=True))
        home.assert_called_once_with(task)
        self.assertEqual(2, len(seen_watches))
        self.assertIsNot(seen_watches[0], seen_watches[1])  # a fresh watch
        self.assertIsNone(task._frozen_watch)
        self.assertIn("回主页再试一次", task.log_warning.call_args.args[0])

    def test_frozen_twice_ends_as_failed_with_the_reason(self):
        task = self._task(retry=True)

        def run(_t):
            raise FrozenScreen()

        with mock.patch("src.tasks.recovery.recover_to_home", return_value=True) as home:
            self.assertFalse(base_module._run_watched(task, run, (), {}, watched=True))
        self.assertEqual(1, home.call_count)  # the second time 失败后继续 goes home
        self.assertIn("秒没有变化", task._why)

    def test_a_task_that_may_spend_is_not_run_again(self):
        task = self._task(retry=False)
        calls = []

        def run(_t):
            calls.append(1)
            raise FrozenScreen()

        with mock.patch("src.tasks.recovery.recover_to_home", return_value=True) as home:
            self.assertFalse(base_module._run_watched(task, run, (), {}, watched=True))
        self.assertEqual(1, len(calls))
        home.assert_not_called()

    def test_a_task_own_stuck_reason_is_kept(self):
        task = self._task(retry=False)

        def run(_t):
            raise FrozenScreen("在活动页 20 秒没走到下一步")

        self.assertFalse(base_module._run_watched(task, run, (), {}, watched=True))
        self.assertEqual("在活动页 20 秒没走到下一步", task._why)

    def test_not_watched_runs_as_before(self):
        task = self._task(retry=True)
        self.assertEqual("ok", base_module._run_watched(task, lambda t: "ok", (), {}))
        self.assertFalse(hasattr(task, "_frozen_watch"))

    def test_safe_tasks_run_again_and_spending_ones_do_not(self):
        from src.tasks.CraftGearTask import CraftGearTask
        from src.tasks.EventBattleTask import EventBattleTask
        from src.tasks.GearTasks import DailyRefineTask
        from src.tasks.JunkGearTask import JunkGearTask
        from src.tasks.MapTradeTask import MapTradeTask
        from src.tasks.PVPTask import PVPTask

        for cls in (EventBattleTask, PVPTask):
            self.assertTrue(cls.frozen_retry, cls.__name__)
        for cls in (DailyRefineTask, JunkGearTask, CraftGearTask, MapTradeTask):
            self.assertFalse(cls.frozen_retry, cls.__name__)


class RecoveryRestsTheWatchTest(unittest.TestCase):
    def test_going_home_does_not_count_as_stuck(self):
        from src.tasks import recovery

        watch = FrozenWatch()
        task = SimpleNamespace(_frozen_watch=watch)
        seen = []

        def inner(t, attempts):
            seen.append(t._frozen_watch.paused)
            return True

        with mock.patch.object(recovery, "_recover_to_home", inner):
            self.assertTrue(recovery.recover_to_home(task))
        self.assertEqual([1], seen)
        self.assertEqual(0, watch.paused)


if __name__ == "__main__":
    unittest.main()
