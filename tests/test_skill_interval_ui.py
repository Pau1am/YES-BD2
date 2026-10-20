"""跑图 技能间隔: a small 「1.2s」 by the skill counts opens a small window,
and players who had the tool before are shown the new place once (Leo
2026-10-20)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.tasks.BaseBD2Task import BaseBD2Task
from src.tasks.MapCollectionTask import MAP_NOTICE_KEY, MapCollectionTask
from src.ui.shell import new_setting_notice
from src.ui.shell.skill_interval_dialog import SkillIntervalDialog, seconds_text


def _load(saved: dict | None) -> MapCollectionTask:
    task = MapCollectionTask(executor=SimpleNamespace(scene=None), app=SimpleNamespace())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "MapCollectionTask.json"
        if saved is not None:
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

        def load(_self):
            _self.config = {**_self.default_config, **(saved or {})}

        with mock.patch(
            "src.tasks.MapCollectionTask.get_relative_path", return_value=str(path)
        ), mock.patch.object(BaseBD2Task, "load_config", load):
            task.load_config()
    return task


class NoticeTest(unittest.TestCase):
    def test_saved_settings_from_before_ask_once(self):
        self.assertTrue(_load({"技能间隔秒数": 1.5}).config[MAP_NOTICE_KEY])

    def test_new_install_does_not_ask(self):
        self.assertFalse(_load(None).config[MAP_NOTICE_KEY])

    def test_after_it_was_shown_it_stays_off(self):
        self.assertFalse(_load({"技能间隔秒数": 1.5, MAP_NOTICE_KEY: False}).config[MAP_NOTICE_KEY])

    def test_shown_once_after_the_others(self):
        from src.tasks.EventBattleTask import EVENT_NOTICE_KEY
        from src.tasks.QuickHuntTask import QUICK_HUNT_NOTICE_KEY

        tasks = {
            "QuickHuntTask": SimpleNamespace(config={QUICK_HUNT_NOTICE_KEY: False}),
            "EventBattleTask": SimpleNamespace(config={EVENT_NOTICE_KEY: True}),
            "MapCollectionTask": SimpleNamespace(config={MAP_NOTICE_KEY: True}),
        }
        with mock.patch.object(
            new_setting_notice.data, "task_by_class_name", side_effect=tasks.get
        ), mock.patch.object(new_setting_notice, "CoachMarks") as tour:
            self.assertTrue(new_setting_notice.show_pending(mock.Mock()))
            self.assertEqual(1, tour.call_count)
            self.assertTrue(tasks["MapCollectionTask"].config[MAP_NOTICE_KEY])
            tour.call_args.args[2]()  # the 活动战斗 walk-through closed
            self.assertEqual(2, tour.call_count)
            self.assertFalse(new_setting_notice.show_pending(mock.Mock()))
        self.assertFalse(tasks["MapCollectionTask"].config[MAP_NOTICE_KEY])

    def test_tour_points_at_the_sidebar_then_the_small_button(self):
        shell = mock.Mock()
        first, second = new_setting_notice.skill_interval_steps(shell)
        self.assertIs(shell.sidebar.items.get.return_value, first.target())
        second.before()
        shell.navigate.assert_called_once_with("map")


class DialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_value_moves_in_tenths_and_resets_to_the_default(self):
        dialog = SkillIntervalDialog(1.5, (0.5, 2.0), 1.2)
        self.assertEqual(1.5, dialog.value())
        self.assertEqual("1.5s", dialog.value_text.text())
        dialog.slider.setValue(dialog.slider.maximum())
        self.assertEqual(2.0, dialog.value())
        dialog._reset()
        self.assertEqual(1.2, dialog.value())
        self.assertEqual("0.5s", seconds_text(0.5))


if __name__ == "__main__":
    unittest.main()
