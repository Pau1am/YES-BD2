"""A tool 定时启动 opened goes straight to 一键日常 (Leo 2026-10-22).

「使用排程開啟的 有沒有確保 打開程式就是直接開始日常」 and 「如果遇到更新
要點掉框框甚麼的 也要處理」: a tool that is not free yet is waited for, and
nothing that waits for a click shows on a scheduled open.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer

from src.ui.shell import autorun, data, schedule_ui
from src.utils import scheduled_start


class _Clock:
    def __init__(self):
        self.now = 1000.0
        self.later = []

    def single_shot(self, ms, call):
        self.later.append((ms, call))

    def run_next(self):
        ms, call = self.later.pop(0)
        self.now += ms / 1000
        call()


class WaitTest(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.busy = True
        self.current = None
        self.started = []
        self.failures = []
        batch = SimpleNamespace(name=data.DAILY_BATCH)
        self.batch = batch
        patches = [
            mock.patch.object(QTimer, "singleShot", self.clock.single_shot),
            mock.patch.object(autorun.time, "time", lambda: self.clock.now),
            mock.patch.object(data, "executor", lambda: object()),
            mock.patch.object(data, "busy", lambda: self.busy),
            mock.patch.object(data, "current_task", lambda: self.current),
            mock.patch.object(data, "task_by_name", lambda name: batch),
            mock.patch.object(autorun, "remaining", lambda: [1]),
            mock.patch("src.utils.clone_desktop.in_clone", lambda: False),
            mock.patch("src.ui.shell.clone_flow.busy_in_clone", lambda: False),
            mock.patch.object(autorun, "maybe_start", self.started.append),
            mock.patch.object(schedule_ui, "report_failure", self.failures.append),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(autorun.cancel)
        autorun.cancel()

    def test_a_busy_tool_is_waited_for_then_it_starts(self):
        self.assertTrue(autorun.schedule(scheduled=True))
        self.assertIsNone(autorun.seconds_left())  # waiting, not counting down
        for _ in range(5):
            self.clock.run_next()
        self.assertEqual([], self.started)
        self.busy = False
        self.clock.run_next()  # free now: the count down begins
        self.assertIsNotNone(autorun.seconds_left())
        self.clock.run_next()
        self.assertEqual([True], self.started)
        self.assertEqual([], self.failures)

    def test_never_free_says_why(self):
        autorun.schedule(scheduled=True)
        while self.clock.later:
            self.clock.run_next()
        self.assertEqual([], self.started)
        self.assertEqual(1, len(self.failures))
        self.assertIn(f"{autorun.WAIT_MINUTES} 分钟", self.failures[0])
        self.assertLessEqual(self.clock.now - 1000.0, autorun.WAIT_MINUTES * 60 + 11)

    def test_busy_again_during_the_count_down_waits_again(self):
        self.busy = False
        autorun.schedule(scheduled=True)
        self.busy = True
        self.clock.run_next()  # the count down ends while a task runs
        self.assertEqual([], self.started)
        self.busy = False
        self.clock.run_next()
        self.clock.run_next()
        self.assertEqual([True], self.started)

    def test_daily_already_running_is_left_alone(self):
        self.current = self.batch
        self.assertFalse(autorun.schedule(scheduled=True))
        self.assertEqual([], self.clock.later)
        self.assertEqual([], self.failures)

    def test_the_players_own_box_does_not_wait(self):
        with mock.patch.object(autorun, "enabled", return_value=True):
            self.assertFalse(autorun.schedule())
        self.assertEqual([], self.clock.later)

    def test_cancel_stops_the_wait(self):
        autorun.schedule(scheduled=True)
        autorun.cancel()
        self.clock.run_next()
        self.assertEqual([], self.clock.later)
        self.assertEqual([], self.failures)


class QuietOpenTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(scheduled_start, "launched_by_schedule", True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_ok_notices_are_left_out(self):
        from ok.ui.qt.MainWindow import MainWindow

        from src.compat import quiet_scheduled_open

        quiet_scheduled_open.install()
        window = SimpleNamespace(switchTo=mock.Mock())
        MainWindow.show_startup_version_change_notice(window)
        MainWindow.show_update_copyright(window)
        window.switchTo.assert_not_called()

    def test_launcher_notices_are_left_out(self):
        from src.compat import launcher_update_notice

        with mock.patch.object(QTimer, "singleShot") as later:
            launcher_update_notice.schedule_notices(SimpleNamespace(config={}))
        later.assert_not_called()
        with mock.patch.object(scheduled_start, "launched_by_schedule", False), \
                mock.patch.object(QTimer, "singleShot") as later:
            launcher_update_notice.schedule_notices(SimpleNamespace(config={}))
        self.assertEqual(2, later.call_count)

    def test_walk_throughs_wait_for_the_next_open(self):
        from src.ui.shell import new_setting_notice

        with mock.patch.object(QTimer, "singleShot") as later:
            new_setting_notice.schedule(SimpleNamespace())
        later.assert_not_called()


if __name__ == "__main__":
    unittest.main()
