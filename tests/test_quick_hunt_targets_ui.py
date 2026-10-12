"""快速狩猎 per-double-case switches and the one-time notice (Leo 2026-10-12)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.tasks.quick_hunt import QUICK_HUNT_TARGET_DEFAULTS
from src.tasks.QuickHuntTask import QUICK_HUNT_NOTICE_KEY, QuickHuntTask
from src.ui.shell import new_setting_notice
from src.ui.shell.config_form import ConfigForm
from src.ui.shell.widgets import Toggle

app = QApplication.instance() or QApplication([])


def _task() -> QuickHuntTask:
    task = object.__new__(QuickHuntTask)
    task.default_config = {}
    task.config_description = {}
    task.config_type = {}
    with mock.patch("src.tasks.DailyTask.BaseBD2Task.__init__", return_value=None):
        QuickHuntTask.__init__(task)
    task.config = dict(task.default_config)
    return task


class ToggleChoiceTest(unittest.TestCase):
    def _toggles(self, form: ConfigForm, key: str) -> list[Toggle]:
        _label, control, _sync = form._rows[key]
        return control.findChildren(Toggle)

    def test_always_exactly_one_switch_on_per_row(self):
        # Leo 2026-10-12: 「沒有那種整行都關掉都不打的狀況 一定要選一個」.
        task = _task()
        form = ConfigForm(task, keys=list(QUICK_HUNT_TARGET_DEFAULTS))
        gold, slime, ground = self._toggles(form, "都双倍时")
        self.assertEqual([True, False, False], [t.isChecked() for t in (gold, slime, ground)])

        ground.click()
        self.assertEqual("狩猎场", task.config["都双倍时"])
        self.assertEqual([False, False, True], [t.isChecked() for t in (gold, slime, ground)])

        ground.click()  # the one that is on stays on
        self.assertEqual("狩猎场", task.config["都双倍时"])
        self.assertEqual([False, False, True], [t.isChecked() for t in (gold, slime, ground)])
        # Other rows untouched.
        self.assertEqual("史莱姆", task.config["史莱姆双倍时"])


class NoticeTest(unittest.TestCase):
    def _load(self, saved: dict | None) -> QuickHuntTask:
        task = _task()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "QuickHuntTask.json"
            if saved is not None:
                path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

            def load(_self):
                _self.config = dict(_self.default_config)

            with mock.patch(
                "src.tasks.QuickHuntTask.get_relative_path", return_value=str(path)
            ), mock.patch("src.tasks.QuickHuntTask.BaseBD2Task.load_config", load):
                task.load_config()
        return task

    def test_update_from_old_settings_moves_them_and_asks_once(self):
        task = self._load({"快速狩猎双倍策略": "忽视双倍", "快速狩猎资源倾向": "金币"})
        self.assertTrue(task.config[QUICK_HUNT_NOTICE_KEY])
        self.assertEqual({"金币"}, {task.config[key] for key in QUICK_HUNT_TARGET_DEFAULTS})

    def test_new_install_and_later_starts_do_not_ask(self):
        self.assertFalse(self._load(None).config[QUICK_HUNT_NOTICE_KEY])
        self.assertFalse(self._load({"都双倍时": "狩猎场"}).config[QUICK_HUNT_NOTICE_KEY])

    def test_notice_shows_once_then_clears(self):
        task = _task()
        task.config[QUICK_HUNT_NOTICE_KEY] = True
        shown = []
        shell = mock.Mock()
        with mock.patch.object(
            new_setting_notice.data, "task_by_class_name", return_value=task
        ), mock.patch.object(new_setting_notice, "CoachMarks") as tour:
            tour.return_value.start.side_effect = lambda: shown.append(1)
            self.assertTrue(new_setting_notice.show_quick_hunt_notice(shell))
            self.assertFalse(new_setting_notice.show_quick_hunt_notice(shell))
        self.assertEqual(1, len(shown))
        self.assertFalse(task.config[QUICK_HUNT_NOTICE_KEY])

    def test_tour_points_at_the_sidebar_then_opens_the_rows(self):
        shell = mock.Mock()
        first, second = new_setting_notice.quick_hunt_steps(shell)
        self.assertIs(shell.sidebar.items.get.return_value, first.target())
        second.before()
        shell.open_task.assert_called_once_with("daily", "快速狩猎")
        self.assertIs(shell.pages.get.return_value.form, second.target())

    def test_notice_waits_while_a_run_or_auto_run_is_pending(self):
        from src.ui.shell import autorun

        with mock.patch.object(new_setting_notice.data, "busy", return_value=True):
            self.assertFalse(new_setting_notice._ready())
        with mock.patch.object(new_setting_notice.data, "busy", return_value=False), mock.patch.object(
            autorun, "seconds_left", return_value=5
        ):
            self.assertFalse(new_setting_notice._ready())
        with mock.patch.object(new_setting_notice.data, "busy", return_value=False), mock.patch.object(
            autorun, "seconds_left", return_value=None
        ):
            self.assertTrue(new_setting_notice._ready())


class CoachMarksTest(unittest.TestCase):
    def test_lit_part_is_clickable_and_steps_walk_to_the_end(self):
        from PySide6.QtWidgets import QPushButton, QWidget

        window = QWidget()
        window.resize(900, 600)
        target = QPushButton("x", window)
        target.setGeometry(100, 100, 120, 40)
        window.show()
        done = []
        steps = [
            new_setting_notice.Step(lambda: target, "a", "b"),
            new_setting_notice.Step(lambda: target, "c", "d"),
        ]
        tour = new_setting_notice.CoachMarks(window, steps, lambda: done.append(1))
        tour.start()
        app.processEvents()
        self.assertFalse(tour.mask().contains(target.geometry().center()))
        self.assertTrue(tour.mask().contains(window.rect().bottomRight() - target.pos()))
        tour.go(1)
        self.assertEqual("知道了", tour.next.text())
        self.assertTrue(tour.back.isVisibleTo(tour))
        tour.go(1)
        self.assertEqual([1], done)


if __name__ == "__main__":
    unittest.main()
