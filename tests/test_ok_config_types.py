"""ok-script builds a settings card for every task when the tool opens and
stops with 「Unknown config type」 on a type it doesn't know, so the tool
never opens (v0.1.27, player log 2026-10-12).  Our own widgets go under
"widget"; "type" must stay one ok-script knows."""

import importlib
import unittest
from types import SimpleNamespace

from ok.ui.qt.tasks.ConfigItemFactory import _resolve_type

from src.config import config

OK_SCRIPT_TYPES = {
    "drop_down",
    "multi_selection",
    "global",
    "text_edit",
    "line_edit",
    "file_selector",
    "button",
}


class OkScriptConfigTypesTest(unittest.TestCase):
    def test_every_task_setting_has_a_type_ok_script_can_draw(self):
        for module, name in config["onetime_tasks"] + config["trigger_tasks"]:
            task = getattr(importlib.import_module(module), name)(
                executor=SimpleNamespace(scene=None), app=SimpleNamespace()
            )
            for key, value in task.default_config.items():
                resolved = _resolve_type(task.config_type.get(key), value)
                with self.subTest(task=name, key=key):
                    self.assertIn(resolved, OK_SCRIPT_TYPES | {None})


if __name__ == "__main__":
    unittest.main()
