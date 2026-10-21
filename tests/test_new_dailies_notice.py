"""救赎之塔 and 亲密度谈心 shown once after the update (Leo 2026-10-21
「這次新增兩個功能 更新上去和以前一樣 要跳窗告訴用戶」)."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ok import BaseTask

from src.tasks import DailyBatchTask as batch_module
from src.tasks.DailyBatchTask import NEW_DAILIES, NEW_DAILIES_NOTICE_KEY, DailyBatchTask
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


class NewDailiesNoticeTest(unittest.TestCase):
    def test_both_are_daily_batch_children(self):
        keys = {child.config_key for child in batch_module.DAILY_BATCH_CHILDREN}
        self.assertTrue(set(NEW_DAILIES) <= keys)

    def test_new_install_is_not_asked(self):
        self.assertFalse(_load(None).config[NEW_DAILIES_NOTICE_KEY])

    def test_player_from_before_is_asked(self):
        config = _load({"启用": True, "广场女神像": True}).config
        self.assertTrue(config[NEW_DAILIES_NOTICE_KEY])
        for key in NEW_DAILIES:
            self.assertIs(True, config[key])

    def test_not_asked_once_both_are_saved(self):
        saved = {"启用": True, **{key: True for key in NEW_DAILIES}}
        self.assertFalse(_load(saved).config[NEW_DAILIES_NOTICE_KEY])

    def test_walk_through_shows_once(self):
        batch = SimpleNamespace(config={NEW_DAILIES_NOTICE_KEY: True})
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
        self.assertFalse(batch.config[NEW_DAILIES_NOTICE_KEY])

    def test_steps_point_at_each_new_row(self):
        rows = {key: object() for key in NEW_DAILIES}
        sidebar_item = object()
        shell = mock.Mock()
        shell.sidebar.items = {"daily": sidebar_item}
        shell.pages = {"daily": SimpleNamespace(_rows=rows, list_card=None)}
        first, *rest = new_setting_notice.new_dailies_steps(shell)
        self.assertIs(sidebar_item, first.target())
        self.assertEqual(len(NEW_DAILIES), len(rest))
        for key, step in zip(NEW_DAILIES, rest, strict=True):
            step.before()
            shell.open_task.assert_called_with("daily", key)
            self.assertIs(rows[key], step.target())

    def test_texts_are_translated(self):
        import json
        from pathlib import Path

        folder = Path(__file__).resolve().parents[1] / "tools" / "i18n"
        keys = set(json.loads((folder / "ui_keys.json").read_text(encoding="utf-8")))
        shell = mock.Mock()
        shell.pages = {}
        for step in new_setting_notice.new_dailies_steps(shell):
            self.assertIn(step.body, keys)
            self.assertIn(step.title, keys | set(NEW_DAILIES))


if __name__ == "__main__":
    unittest.main()
