"""活动每日战斗: 只刷普通难度 back off once, then the one-time walk-through
(Leo 2026-10-14 「把它改成不打勾 然後和之前更新快速狩獵時一樣 第一次開工具會提示」)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.tasks.BaseBD2Task import BaseBD2Task
from src.tasks.EventBattleTask import (
    CHALLENGE_CAP_KEY,
    EVENT_NOTICE_KEY,
    NORMAL_ONLY_KEY,
    EventBattleTask,
)
from src.ui.shell import new_setting_notice


def _load(saved: dict | None) -> EventBattleTask:
    task = EventBattleTask(executor=SimpleNamespace(scene=None), app=SimpleNamespace())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "EventBattleTask.json"
        if saved is not None:
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

        def load(_self):
            _self.config = {**_self.default_config, **(saved or {})}

        with mock.patch(
            "src.tasks.EventBattleTask.get_relative_path", return_value=str(path)
        ), mock.patch.object(BaseBD2Task, "load_config", load):
            task.load_config()
    return task


class NormalOnlyResetTest(unittest.TestCase):
    def test_default_is_unticked_and_stage_15(self):
        config = _load(None).config
        self.assertIs(False, config[NORMAL_ONLY_KEY])
        self.assertEqual("15", config[CHALLENGE_CAP_KEY])

    def test_saved_tick_from_before_goes_off_and_asks_once(self):
        task = _load({NORMAL_ONLY_KEY: True, CHALLENGE_CAP_KEY: "10"})
        self.assertIs(False, task.config[NORMAL_ONLY_KEY])
        self.assertTrue(task.config[EVENT_NOTICE_KEY])
        self.assertEqual("15", task.config[CHALLENGE_CAP_KEY])

    def test_new_install_does_not_ask(self):
        self.assertFalse(_load(None).config[EVENT_NOTICE_KEY])

    def test_a_tick_made_after_the_update_stays(self):
        task = _load({NORMAL_ONLY_KEY: True, CHALLENGE_CAP_KEY: "10", EVENT_NOTICE_KEY: False})
        self.assertIs(True, task.config[NORMAL_ONLY_KEY])
        self.assertEqual("10", task.config[CHALLENGE_CAP_KEY])
        self.assertFalse(task.config[EVENT_NOTICE_KEY])


class WalkThroughTest(unittest.TestCase):
    def _tasks(self, quick: bool, event: bool):
        from src.tasks.QuickHuntTask import QUICK_HUNT_NOTICE_KEY

        return {
            "QuickHuntTask": SimpleNamespace(config={QUICK_HUNT_NOTICE_KEY: quick}),
            "EventBattleTask": SimpleNamespace(config={EVENT_NOTICE_KEY: event}),
        }

    def test_shows_once_then_clears(self):
        tasks = self._tasks(False, True)
        with mock.patch.object(
            new_setting_notice.data, "task_by_class_name", side_effect=tasks.get
        ), mock.patch.object(new_setting_notice, "CoachMarks") as tour:
            self.assertTrue(new_setting_notice.show_pending(mock.Mock()))
            self.assertFalse(new_setting_notice.show_pending(mock.Mock()))
        self.assertEqual(1, tour.return_value.start.call_count)
        self.assertFalse(tasks["EventBattleTask"].config[EVENT_NOTICE_KEY])

    def test_after_the_quick_hunt_one_when_both_are_pending(self):
        tasks = self._tasks(True, True)
        with mock.patch.object(
            new_setting_notice.data, "task_by_class_name", side_effect=tasks.get
        ), mock.patch.object(new_setting_notice, "CoachMarks") as tour:
            self.assertTrue(new_setting_notice.show_pending(mock.Mock()))
            self.assertEqual(1, tour.call_count)
            self.assertTrue(tasks["EventBattleTask"].config[EVENT_NOTICE_KEY])
            on_done = tour.call_args.args[2]
            on_done()  # the quick hunt walk-through closed
            self.assertEqual(2, tour.call_count)
        self.assertFalse(tasks["EventBattleTask"].config[EVENT_NOTICE_KEY])

    def test_tour_points_at_the_sidebar_then_opens_the_settings(self):
        shell = mock.Mock()
        first, second = new_setting_notice.event_battle_steps(shell)
        self.assertIs(shell.sidebar.items.get.return_value, first.target())
        second.before()
        shell.open_task.assert_called_once_with("daily", "活动每日战斗")
        self.assertIs(shell.pages.get.return_value.form, second.target())


if __name__ == "__main__":
    unittest.main()
