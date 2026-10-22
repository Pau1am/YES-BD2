import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.utils import scheduled_start as ss
from src.utils.scheduled_start import KIND_RESET, KIND_TIME, Settings, Slot

TAIPEI = timezone(timedelta(hours=8))
NEW_YORK = timezone(timedelta(hours=-4))


def _done(code=0, out=""):
    return subprocess.CompletedProcess([], code, out, "")


class SettingsTest(unittest.TestCase):
    """Leo 2026-10-22: several time slots, each with its own time and days."""

    def test_round_trip(self):
        settings = Settings(True, False, [Slot(KIND_RESET), Slot(KIND_TIME, 7, 5, [5, 6], False)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "configs" / "scheduled_start.json"
            ss.save(settings, path)
            again = ss.load(path)
        self.assertEqual(again.to_json(), settings.to_json())

    def test_missing_or_broken_file_is_off(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.json"
            self.assertFalse(ss.load(path).enabled)
            path.write_text("{oops", encoding="utf-8")
            self.assertFalse(ss.load(path).enabled)

    def test_bad_slots_are_dropped(self):
        settings = Settings.from_json(
            {"enabled": True, "slots": [{"time": "25:00"}, {"time": "9:30", "days": [0, 9]}, 3]}
        )
        self.assertEqual([s.to_json() for s in settings.slots],
                         [{"kind": "time", "time": "09:30", "days": [0], "on": True}])

    def test_off_means_no_active_slot(self):
        settings = Settings(False, True, [Slot(KIND_RESET)])
        self.assertEqual(settings.active_slots(), [])
        settings.enabled = True
        settings.slots.append(Slot(KIND_TIME, days=[]))
        settings.slots.append(Slot(KIND_TIME, on=False))
        self.assertEqual(len(settings.active_slots()), 1)


class TimesTest(unittest.TestCase):
    def test_reset_follows_game_time_in_any_zone(self):
        self.assertEqual(ss.reset_clock(datetime(2026, 10, 22, 12, tzinfo=TAIPEI)), (8, 5))
        # 08:05 UTC+8 is 20:05 the day before in New York (UTC-4).
        self.assertEqual(ss.reset_clock(datetime(2026, 10, 22, 12, tzinfo=NEW_YORK)), (20, 5))

    def test_next_run_picks_the_nearest_day(self):
        settings = Settings(True, True, [Slot(KIND_TIME, 21, 0, [5])])  # Saturday
        now = datetime(2026, 10, 22, 22, 0, tzinfo=TAIPEI)  # Thursday
        self.assertEqual(ss.next_run(settings, now), datetime(2026, 10, 24, 21, 0, tzinfo=TAIPEI))

    def test_next_run_reset_slot(self):
        settings = Settings(True, True, [Slot(KIND_RESET)])
        before = datetime(2026, 10, 22, 7, 0, tzinfo=TAIPEI)
        after = datetime(2026, 10, 22, 9, 0, tzinfo=TAIPEI)
        self.assertEqual(ss.next_run(settings, before), datetime(2026, 10, 22, 8, 5, tzinfo=TAIPEI))
        self.assertEqual(ss.next_run(settings, after), datetime(2026, 10, 23, 8, 5, tzinfo=TAIPEI))

    def test_nothing_when_off(self):
        self.assertIsNone(ss.next_run(Settings(False), datetime.now(TAIPEI)))

    def test_due_only_once_and_not_too_late(self):
        settings = Settings(True, True, [Slot(KIND_TIME, 21, 0)])
        slot = datetime(2026, 10, 22, 21, 0, tzinfo=TAIPEI)
        self.assertEqual(
            ss.due_between(settings, slot - timedelta(seconds=20), slot + timedelta(seconds=1)), slot
        )
        # The next tick does not start it again.
        self.assertIsNone(
            ss.due_between(settings, slot + timedelta(seconds=1), slot + timedelta(seconds=21))
        )
        # The PC slept through it and woke an hour later: no start then.
        self.assertIsNone(
            ss.due_between(settings, slot - timedelta(minutes=1), slot + timedelta(hours=1))
        )


class TaskXmlTest(unittest.TestCase):
    def xml(self, settings):
        return ss.task_xml(
            settings,
            ("C:\\yes\\pythonw.exe", '"C:\\yes\\main.py" --scheduled-start', "C:\\yes"),
            "PC\\leo",
            datetime(2026, 10, 22, 9, 0, tzinfo=TAIPEI),
        )

    def test_one_trigger_per_slot(self):
        xml = self.xml(Settings(True, True, [Slot(KIND_RESET), Slot(KIND_TIME, 12, 30, [5, 6])]))
        self.assertEqual(xml.count("<CalendarTrigger>"), 2)
        self.assertIn("<StartBoundary>2026-10-22T08:05:00+08:00</StartBoundary>", xml)
        self.assertIn("<StartBoundary>2026-10-22T12:30:00</StartBoundary>", xml)
        self.assertIn("<Saturday /><Sunday />", xml)

    def test_wakes_runs_elevated_and_never_stops_the_tool(self):
        xml = self.xml(Settings(True, True, [Slot(KIND_RESET)]))
        self.assertIn("<WakeToRun>true</WakeToRun>", xml)
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", xml)
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", xml)
        self.assertIn("<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>", xml)
        self.assertIn("&quot;C:\\yes\\main.py&quot; --scheduled-start", xml.replace('"', "&quot;"))
        self.assertIn("<WakeToRun>false</WakeToRun>", self.xml(Settings(True, False, [Slot(KIND_RESET)])))

    def test_task_name_per_folder(self):
        self.assertNotEqual(ss.task_name("C:\\a"), ss.task_name("C:\\b"))
        self.assertTrue(ss.task_name("C:\\a").startswith("\\YES-BD2\\"))


class ApplyTest(unittest.TestCase):
    def test_on_creates_the_task(self):
        calls = []
        ss.apply(Settings(True, True, [Slot(KIND_RESET)]),
                 run=lambda args, **kw: calls.append(args) or _done())
        self.assertEqual(calls[0][:2], ["schtasks", "/Create"])
        self.assertIn("/F", calls[0])

    def test_off_deletes_the_task(self):
        calls = []
        ss.apply(Settings(False, True, [Slot(KIND_RESET)]),
                 run=lambda args, **kw: calls.append(args) or _done())
        self.assertEqual([c[1] for c in calls], ["/Query", "/Delete"])

    def test_off_without_a_task_is_fine(self):
        calls = []
        ss.apply(Settings(False), run=lambda args, **kw: calls.append(args) or _done(1))
        self.assertEqual([c[1] for c in calls], ["/Query"])

    def test_refused_says_why(self):
        def run(args, **kw):
            return subprocess.CompletedProcess(args, 1, "", "ERROR: Access is denied.")

        with self.assertRaises(ss.TaskError) as caught:
            ss.apply(Settings(True, True, [Slot(KIND_RESET)]), run=run)
        self.assertIn("Access is denied", str(caught.exception))

    def test_missing_schtasks(self):
        def run(args, **kw):
            raise FileNotFoundError("schtasks")

        with self.assertRaises(ss.TaskError):
            ss.apply(Settings(True, True, [Slot(KIND_RESET)]), run=run)


class WakeTimerTest(unittest.TestCase):
    QUERY = (
        "    电源设置 GUID: bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d  (允许使用唤醒定时器)\n"
        "      可能的设置索引: 000\n      可能的设置索引: 001\n      可能的设置索引: 002\n"
        "    当前交流电源设置索引: 0x{ac:08x}\n    当前直流电源设置索引: 0x00000001\n"
    )

    def test_reads_the_plugged_in_value(self):
        self.assertEqual(ss.wake_timer_index(self.QUERY.format(ac=2)), 2)
        self.assertIsNone(ss.wake_timer_index("nothing"))

    def test_on_already(self):
        calls = []
        result = ss.ensure_wake_timers(
            run=lambda args, **kw: calls.append(args) or _done(0, self.QUERY.format(ac=1))
        )
        self.assertTrue(result)
        self.assertEqual(len(calls), 1)

    def test_turned_on_when_off(self):
        calls = []
        result = ss.ensure_wake_timers(
            run=lambda args, **kw: calls.append(args) or _done(0, self.QUERY.format(ac=0))
        )
        self.assertTrue(result)
        self.assertEqual([c[1] for c in calls],
                         ["/query", "/setacvalueindex", "/setdcvalueindex", "/setactive"])

    def test_refused(self):
        def run(args, **kw):
            return _done(0, self.QUERY.format(ac=0)) if args[1] == "/query" else _done(1)

        self.assertFalse(ss.ensure_wake_timers(run=run))


class FlagTest(unittest.TestCase):
    def test_flag_taken_off(self):
        argv = ["main.py", ss.FLAG]
        self.assertTrue(ss.take_flag(argv))
        self.assertEqual(argv, ["main.py"])
        self.assertFalse(ss.take_flag(argv))


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from src.tasks.DailyBatchTask import CLOSE_GAME_KEY
        from src.ui.shell import data, schedule_ui

        self.ui = schedule_ui
        self.config = {CLOSE_GAME_KEY: False}
        batch = SimpleNamespace(
            name=data.DAILY_BATCH, child_tasks=[], config=self.config, info={},
            batch_label="一键完成日常",
        )
        patches = [
            mock.patch.object(data, "task_by_name", lambda name: batch),
            mock.patch.object(schedule_ui, "_settings", Settings(True, True, [Slot(KIND_RESET)])),
            mock.patch.object(schedule_ui, "problem", ""),
            mock.patch.object(ss, "save"),
            mock.patch.object(ss, "ensure_wake_timers", return_value=True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_master_switch_off_removes_everything(self):
        with mock.patch.object(ss, "apply") as apply:
            self.assertEqual(self.ui.set_enabled(False), "")
        self.assertFalse(apply.call_args[0][0].enabled)
        self.assertFalse(self.ui.settings().enabled)

    def test_refused_keeps_the_old_settings(self):
        with mock.patch.object(ss, "apply", side_effect=ss.TaskError("denied")):
            why = self.ui.set_enabled(False)
        self.assertIn("denied", why)
        self.assertTrue(self.ui.settings().enabled)
        ss.save.assert_not_called()

    def test_dialog_adds_and_deletes_slots(self):
        dialog = self.ui.ScheduleDialog(None)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.add_reset.isHidden())
        dialog._add_time()
        self.assertEqual(len(dialog._rows), 2)
        dialog._delete(dialog._rows[0])
        self.assertEqual([s.kind for s in dialog.working.slots], [KIND_TIME])
        self.assertFalse(dialog.add_reset.isHidden())
        for _ in range(10):
            dialog._add_time()
        self.assertEqual(len(dialog.working.slots), ss.MAX_SLOTS)
        # Nothing is kept before 保存.
        self.assertEqual(len(self.ui.settings().slots), 1)

    def test_dialog_save_writes_task_and_options(self):
        from src.tasks.DailyBatchTask import CLOSE_GAME_KEY

        dialog = self.ui.ScheduleDialog(None)
        self.addCleanup(dialog.close)
        # Leo 2026-10-22: a scheduled run closes the game by default.
        self.assertTrue(dialog.close_game.isChecked())
        dialog._add_time()
        dialog._rows[1].days[6].setChecked(False)
        dialog.shutdown.setChecked(True)
        with mock.patch.object(ss, "apply") as apply:
            dialog._save()
        saved = apply.call_args[0][0]
        self.assertEqual(saved.slots[1].days, [0, 1, 2, 3, 4, 5])
        self.assertTrue(saved.close_game and saved.shutdown)
        # 一键日常's own setting (manual runs) is left as it was.
        self.assertFalse(self.config[CLOSE_GAME_KEY])
        self.assertEqual(len(self.ui.settings().slots), 2)

    def test_master_off_in_dialog_greys_the_slots(self):
        dialog = self.ui.ScheduleDialog(None)
        self.addCleanup(dialog.close)
        dialog.master.setChecked(False)
        self.assertFalse(dialog.body.isEnabled())

    def test_next_text(self):
        now = datetime(2026, 10, 22, 7, 0, tzinfo=TAIPEI)
        self.assertEqual(self.ui.next_text(now), ("08:05", "下次 · 今天"))
        self.ui._settings.enabled = False
        self.assertEqual(self.ui.next_text(now), ("", ""))


class FailureReportTest(UiTest):
    """A scheduled start that never became a run still ends in a report
    (Leo 2026-10-22: 「有問題也要說」; the 跑完通知 sends on run_report.finish)."""

    def setUp(self):
        super().setUp()
        from src.tasks import run_report

        self.run_report = run_report
        folder = tempfile.mkdtemp()
        run_report.set_report_file(os.path.join(folder, "reports.json"))
        self.addCleanup(run_report.set_report_file, None)
        self.finished = []
        real_finish = run_report.finish
        patch = mock.patch.object(
            run_report, "finish", lambda ended: self.finished.append(real_finish(ended))
        )
        patch.start()
        self.addCleanup(patch.stop)
        ss.mark_run_pending(False)

    def test_lock_screen(self):
        with mock.patch.object(ss, "screen_locked", return_value=True):
            self.assertFalse(self.ui.before_start())
        report = self.finished[-1]
        self.assertEqual(report["ended"], self.run_report.ENDED_ERROR)
        self.assertEqual(report["label"], "一键完成日常")
        self.assertEqual(report["rows"], [])
        self.assertTrue(report["scheduled"])
        self.assertIn("锁屏", report["notice"])
        self.assertFalse(ss.take_run_pending())

    def test_unlocked_marks_the_run(self):
        with mock.patch.object(ss, "screen_locked", return_value=False):
            self.assertTrue(self.ui.before_start())
        self.assertTrue(ss.take_run_pending())
        self.assertFalse(ss.take_run_pending())
        self.assertEqual(self.finished, [])

    def test_not_started(self):
        ss.mark_run_pending()
        self.ui.after_start(False)
        self.assertIn("没能开始", self.finished[-1]["notice"])
        self.assertFalse(ss.take_run_pending())

    def test_game_never_logged_in(self):
        from src.ui.shell import data

        with mock.patch.object(self.ui.QTimer, "singleShot"):
            self.ui.after_start(True)
        with mock.patch.object(data, "busy", return_value=False):
            self.ui._check_begun()
        self.assertIn("没登录进去", self.finished[-1]["notice"])

    def test_run_began_no_report(self):
        from src.ui.shell import data

        with mock.patch.object(self.ui.QTimer, "singleShot"):
            self.ui.after_start(True)
        self.run_report.begin("一键完成日常", "x", [("a", "a")])
        self.run_report.finish(self.run_report.ENDED_DONE)
        count = len(self.finished)
        with mock.patch.object(data, "busy", return_value=False):
            self.ui._check_begun()
        self.assertEqual(len(self.finished), count)

    def test_still_busy_checks_again(self):
        from src.ui.shell import data

        with mock.patch.object(self.ui.QTimer, "singleShot"):
            self.ui.after_start(True)
        with mock.patch.object(data, "busy", return_value=True), \
                mock.patch.object(self.ui.QTimer, "singleShot") as later:
            self.ui._check_begun()
        later.assert_called_once()
        self.assertEqual(self.finished, [])

    def test_no_report_over_a_running_one(self):
        self.run_report.begin("一键完成日常", "x", [("a", "a")])
        self.addCleanup(self.run_report.finish, self.run_report.ENDED_DONE)
        self.ui.report_failure("x")
        self.assertEqual(self.finished, [])


class ScheduledOptionTest(unittest.TestCase):
    def test_only_for_the_scheduled_run(self):
        from src.tasks.DailyBatchTask import DailyBatchTask

        task = SimpleNamespace(_scheduled_run=False)
        settings = Settings(True, True, [Slot(KIND_RESET)], close_game=True, shutdown=False)
        with mock.patch.object(ss, "load", return_value=settings):
            self.assertFalse(DailyBatchTask._scheduled_option(task, "close_game"))
            task._scheduled_run = True
            self.assertTrue(DailyBatchTask._scheduled_option(task, "close_game"))
            self.assertFalse(DailyBatchTask._scheduled_option(task, "shutdown"))


class AutorunTest(unittest.TestCase):
    def test_scheduled_start_ignores_the_home_box(self):
        from src.ui.shell import autorun

        with mock.patch.object(autorun, "enabled", return_value=False), \
                mock.patch.object(autorun.data, "executor", return_value=object()), \
                mock.patch.object(autorun.data, "busy", return_value=False), \
                mock.patch.object(autorun, "remaining", return_value=[1]):
            self.assertEqual(autorun.should_start(False), "off")
            self.assertIsNone(autorun.should_start(False, scheduled=True))
            self.assertEqual(autorun.should_start(True, scheduled=True), "in the clone")


if __name__ == "__main__":
    unittest.main()
