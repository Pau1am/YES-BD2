"""Live 4K 2026-10-14: after login the 镜中之战 rank-up page (蓝宝石Ⅲ
恭喜晋级。 确认) only closes with its 确认; the clear spot was clicked 29 times
until Leo closed it by hand."""

import unittest
from types import SimpleNamespace

import numpy as np

from src.tasks.trigger.AutoLoginTask import AutoLoginTask


def _box(name, x, y):
    return SimpleNamespace(name=name, x=x, y=y, width=60, height=20)


class RankUpPopupTest(unittest.TestCase):
    def _task(self, boxes):
        task = object.__new__(AutoLoginTask)
        task.config = {"公告清理点击 X 百分比": 8.8, "公告清理点击 Y 百分比": 56.9}
        task.info_set = lambda *_a, **_k: None
        task.log_info = lambda *_a, **_k: None
        task.sleep = lambda *_a, **_k: None
        task._sleep_after_recognition = lambda: None
        task._last_clear_click_at = 0.0
        task._login_clicked_at = 1.0
        task._home_bright_since = None
        task.capture_frame = lambda: np.zeros((720, 1280, 3), np.uint8)
        task.ocr = lambda *_a, **_k: boxes
        task.clicks = []
        task.operate_click = lambda x, y, **_k: task.clicks.append((round(x, 3), round(y, 3)))
        return task

    def test_the_rank_up_page_is_closed_with_its_confirm(self):
        task = self._task(
            [_box("蓝宝石Ⅲ", 600, 170), _box("恭喜晋级。", 600, 500), _box("确认", 610, 660)]
        )
        task._clear_home_popup(0.08)
        self.assertEqual([(round(640 / 1280, 3), round(670 / 720, 3))], task.clicks)

    def test_without_a_known_popup_the_clear_spot_is_clicked(self):
        task = self._task([])
        task._clear_home_popup(0.08)
        self.assertEqual([(0.088, 0.569)], task.clicks)


if __name__ == "__main__":
    unittest.main()
