"""定时启动 shown once after the update (Leo 2026-10-22: new features get the
same one-time walk-through as before)."""

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ok import BaseTask

from src.tasks import DailyBatchTask as batch_module
from src.tasks.DailyBatchTask import SCHEDULE_NOTICE_KEY, DailyBatchTask, WeeklyBatchTask
from src.ui.shell import new_setting_notice


def _load(saved: dict | None) -> DailyBatchTask:
    task = DailyBatchTask(executor=SimpleNamespace(scene=None), app=SimpleNamespace())

    def load(_self):
        _self.config = {**_self.default_config, **(saved or {})}

    def read(path):
        return dict(saved or {}) if "DailyBatchTask" in str(path) else {}

    with (
        mock.patch.object(batch_module, "_read_json", side_effect=read),
        mock.patch.object(BaseTask, "load_config", load),
    ):
        task.load_config()
    return task


class ScheduleNoticeTest(unittest.TestCase):
    def test_new_install_is_not_asked(self):
        self.assertFalse(_load(None).config[SCHEDULE_NOTICE_KEY])

    def test_player_from_before_is_asked(self):
        self.assertTrue(_load({"启用": True}).config[SCHEDULE_NOTICE_KEY])

    def test_not_asked_again_once_saved(self):
        saved = {"启用": True, SCHEDULE_NOTICE_KEY: False}
        self.assertFalse(_load(saved).config[SCHEDULE_NOTICE_KEY])

    def test_weekly_batch_has_no_such_key(self):
        weekly = WeeklyBatchTask(executor=SimpleNamespace(scene=None), app=SimpleNamespace())
        self.assertNotIn(SCHEDULE_NOTICE_KEY, weekly.default_config)

    def test_walk_through_shows_once(self):
        batch = SimpleNamespace(config={SCHEDULE_NOTICE_KEY: True})
        with (
            mock.patch.object(
                new_setting_notice.data,
                "task_by_class_name",
                side_effect={"DailyBatchTask": batch}.get,
            ),
            mock.patch.object(new_setting_notice, "CoachMarks") as tour,
        ):
            self.assertTrue(new_setting_notice.show_pending(mock.Mock()))
            self.assertFalse(new_setting_notice.show_pending(mock.Mock()))
        self.assertEqual(1, tour.return_value.start.call_count)
        self.assertFalse(batch.config[SCHEDULE_NOTICE_KEY])

    def test_points_at_the_card_on_home(self):
        card = object()
        shell = mock.Mock()
        shell.pages = {"home": SimpleNamespace(schedule_card=card)}
        (step,) = new_setting_notice.schedule_steps(shell)
        step.before()
        shell.navigate.assert_called_once_with("home")
        self.assertIs(card, step.target())

    def test_texts_are_translated(self):
        folder = Path(__file__).resolve().parents[1] / "tools" / "i18n"
        keys = set(json.loads((folder / "ui_keys.json").read_text(encoding="utf-8")))
        for step in new_setting_notice.schedule_steps(mock.Mock()):
            self.assertIn(step.title, keys)
            self.assertIn(step.body, keys)


if __name__ == "__main__":
    unittest.main()
