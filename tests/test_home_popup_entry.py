"""A home entrance click lost under a login popup (4K clone 2026-10-21).

The pass promo and the Bilibili banner lay over 主页 while the home check
still passed, and three 游戏卡珍藏集 clicks went nowhere.  Leo 「彈窗不是點掉
就好了嗎」: before clicking again, close the popup.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.tasks.DoomBookTask import DoomBookTask
from src.utils.home_confirmation import HOME_ANNOUNCEMENT_CLEAR_REFERENCE_POINT

ENTRY = (1693, 975)


class HomePopupEntryTest(unittest.TestCase):
    def task(self, titles, popup_closed=False):
        task = DoomBookTask(SimpleNamespace(scene=None), SimpleNamespace(debug=False))
        task._wait_for_home_confirmation = lambda *a, **k: True
        task._sleep_after_recognition = lambda: None
        titles = iter(titles)
        task._wait_for_title = lambda *a, **k: next(titles)
        task.close_known_popup = mock.Mock(return_value=popup_closed)
        task._click_reference = mock.Mock()
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        return task

    def clicks(self, task):
        return [call.args[:2] for call in task._click_reference.call_args_list]

    def test_lost_click_taps_the_blank_spot_then_clicks_again(self):
        task = self.task([False, True])
        self.assertTrue(task._open_page_from_home("游戏卡珍藏集", ENTRY, ("游戏卡珍藏集",)))
        self.assertEqual([ENTRY, HOME_ANNOUNCEMENT_CLEAR_REFERENCE_POINT, ENTRY], self.clicks(task))

    def test_a_popup_with_its_own_close_is_closed_by_it(self):
        task = self.task([False, True], popup_closed=True)
        self.assertTrue(task._open_page_from_home("游戏卡珍藏集", ENTRY, ("游戏卡珍藏集",)))
        self.assertEqual([ENTRY, ENTRY], self.clicks(task))

    def test_first_click_that_works_touches_nothing_else(self):
        task = self.task([True])
        self.assertTrue(task._open_page_from_home("游戏卡珍藏集", ENTRY, ("游戏卡珍藏集",)))
        self.assertEqual([ENTRY], self.clicks(task))
        task.close_known_popup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
