"""料理: 返回 on a detail page is pressed again once when the page stays.

YES-BD2 #13 (v0.1.21, 1920×1080 fullscreen, 2026-10-11): after 香草牛排 was
cooked the log read 「结果已确认，但未恢复料理列表」 and the frames show the
detail page through the whole wait.  The same 返回 pressed on the way out
worked, so later dishes were skipped for a press the game dropped.
"""

import unittest

import numpy as np

from src.tasks.map_trade.trader import Trader
from src.tasks.map_trade.trader_cooking import (
    COOKING_PAGE_TIMEOUT,
    COOKING_RECLICK_AFTER,
    CookingDetailSnapshot,
)


class _Screen:
    """The cooking detail page; each 返回 lands or is dropped in turn."""

    def __init__(self, lands=(True,), detail_after_drop=True):
        self.lands = list(lands)
        self.detail_after_drop = detail_after_drop
        self.page = "detail"
        self.presses = []
        self.list_waits = []

    def back(self, context):
        self.presses.append(context)
        landed = self.lands.pop(0) if self.lands else False
        if landed:
            self.page = "list"
        elif not self.detail_after_drop:
            self.page = "other"


def _trader(screen):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    logs = []
    trader = object.__new__(Trader)
    trader.task = type(
        "Task",
        (),
        {
            "sleep": lambda self, _s: None,
            "log_info": lambda self, message: logs.append(message),
            "log_warning": lambda self, message, **_k: logs.append(message),
            "info_set": lambda self, *_a: None,
        },
    )()
    trader.logs = logs
    detail = CookingDetailSnapshot(frame, None, False, 0.0)
    trader._wait_for_cooking_detail = lambda _recipe, _timeout: (
        detail if screen.page == "detail" else None
    )
    trader._generic_cooking_detail_snapshot = lambda frame=None: (
        detail if screen.page == "detail" else None
    )

    def wait_list(timeout):
        screen.list_waits.append(timeout)
        return object() if screen.page == "list" else None

    trader._wait_for_cooking_list = wait_list
    trader._click_cooking_back = lambda _frame, *, context: screen.back(context)
    return trader


class BackFromDetailTest(unittest.TestCase):
    def test_a_dropped_返回_is_pressed_again_and_the_list_comes_back(self):
        # The player's case: the first 返回 did nothing, the second worked.
        screen = _Screen(lands=(False, True))
        trader = _trader(screen)
        self.assertTrue(trader._return_from_detail_to_list("香草牛排"))
        self.assertEqual(["香草牛排详情", "香草牛排详情补按"], screen.presses)
        self.assertTrue(any("再按一次返回" in line for line in trader.logs))

    def test_a_返回_that_works_is_pressed_once(self):
        screen = _Screen(lands=(True,))
        self.assertTrue(_trader(screen)._return_from_detail_to_list("香草牛排"))
        self.assertEqual(["香草牛排详情"], screen.presses)

    def test_no_second_press_when_the_detail_page_is_gone(self):
        # Something else is drawing (not the list, not the detail): wait only.
        screen = _Screen(lands=(False,), detail_after_drop=False)
        self.assertFalse(_trader(screen)._return_from_detail_to_list("香草牛排"))
        self.assertEqual(["香草牛排详情"], screen.presses)

    def test_返回_is_pressed_at_most_twice(self):
        screen = _Screen(lands=(False, False, True))
        self.assertFalse(_trader(screen)._return_from_detail_to_list("香草牛排"))
        self.assertEqual(2, len(screen.presses))

    def test_the_whole_wait_is_still_the_page_timeout(self):
        screen = _Screen(lands=(False, False))
        _trader(screen)._return_from_detail_to_list("香草牛排")
        self.assertEqual(COOKING_RECLICK_AFTER, screen.list_waits[0])
        self.assertGreaterEqual(sum(screen.list_waits), COOKING_PAGE_TIMEOUT - 0.5)

    def test_the_way_out_presses_返回_again_too(self):
        screen = _Screen(lands=(False, True))
        trader = _trader(screen)
        self.assertTrue(trader._recover_cooking_list())
        self.assertEqual(["料理详情恢复", "料理详情恢复补按"], screen.presses)


if __name__ == "__main__":
    unittest.main()
