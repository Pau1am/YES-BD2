"""A still screen that shows the loading ring's percent is loading, not stuck.

Player report 2026-10-20 (1080p, v0.2.2): 镜中之战 gave up 「未能进入 PVP 箱庭」
while 「MIRROR WARS 镜中之战」 stood with 94% in its bottom-right ring
(Leo 「我之前說了10秒限制 不該在這種時候」「改成45秒」)."""

import unittest
from types import SimpleNamespace

import numpy as np

from src.utils import wait_limits
from src.utils.frozen_screen import loading_percent, loading_sign
from src.utils.wait_limits import LOADING_MAX_SECONDS, STUCK_SECONDS, load_wait

W, H = 1920, 1080
STILL = np.full((108, 192, 3), 120, np.uint8)


def box(name, x, y, w=60, h=40):
    return SimpleNamespace(name=name, x=x, y=y, width=w, height=h)


MIRROR_WARS = [box("MIRROR WARS", 760, 700, 400, 80), box("镜中之战", 880, 790, 160, 40), box("94%", 1800, 1000)]


class LoadingPercentTest(unittest.TestCase):
    def test_ring_percent_in_the_corner(self):
        self.assertEqual(loading_percent(MIRROR_WARS, W, H), "94%")
        self.assertEqual(loading_sign(MIRROR_WARS, W, H), "94%")
        self.assertEqual(loading_percent([box("100 ％", 1800, 1000)], W, H), "100%")

    def test_percent_elsewhere_or_not_a_percent_is_not_loading(self):
        self.assertEqual(loading_percent([box("94%", 900, 500)], W, H), "")
        self.assertEqual(loading_percent([box("x94%", 1800, 1000)], W, H), "")
        self.assertEqual(loading_percent([box("250%", 1800, 1000)], W, H), "")
        self.assertEqual(loading_sign([box("MIRROR WARS", 760, 700)], W, H), "")

    def test_loading_word_still_counts(self):
        self.assertEqual(loading_sign([box("连接中", 900, 500)], W, H), "连接中")


class WaitAsksBeforeStuckTest(unittest.TestCase):
    def tearDown(self):
        wait_limits.set_loading_reader(None)

    def test_still_loading_screen_waits_to_the_cap(self):
        wait_limits.set_loading_reader(lambda _frame: "94%")
        wait = load_wait(0.0, STUCK_SECONDS)
        for t in range(int(LOADING_MAX_SECONDS)):
            self.assertFalse(wait.over(STILL, float(t)), t)
        self.assertTrue(wait.over(STILL, LOADING_MAX_SECONDS))

    def test_still_screen_without_a_sign_is_stuck_after_10_s(self):
        wait_limits.set_loading_reader(lambda _frame: "")
        wait = load_wait(0.0, STUCK_SECONDS)
        self.assertFalse(wait.over(STILL, 0.0))
        self.assertTrue(wait.over(STILL, STUCK_SECONDS))

    def test_cap_is_45_s(self):
        self.assertEqual(LOADING_MAX_SECONDS, 45.0)


if __name__ == "__main__":
    unittest.main()
