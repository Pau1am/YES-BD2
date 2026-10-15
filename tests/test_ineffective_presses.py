"""Leo 2026-10-14: pressing on and on while nothing changes means something
covers the page; after INEFFECTIVE_PRESSES a known popup is looked for."""

import unittest

import numpy as np

from src.utils.frozen_screen import INEFFECTIVE_PRESSES, FrozenWatch


def _frame(value):
    return np.full((108, 192, 3), value, np.uint8)


class IneffectivePressTest(unittest.TestCase):
    def test_presses_on_an_unchanged_screen_are_counted(self):
        watch = FrozenWatch()
        for _ in range(INEFFECTIVE_PRESSES + 1):
            watch.look(_frame(50), now=0.0)
            watch.pressed((0.1, 0.5))
        self.assertEqual(INEFFECTIVE_PRESSES, watch.ineffective)

    def test_presses_on_different_spots_are_not_counted(self):
        watch = FrozenWatch()
        for index in range(INEFFECTIVE_PRESSES + 1):
            watch.look(_frame(50), now=0.0)
            watch.pressed((0.1 * index, 0.5))
        self.assertEqual(0, watch.ineffective)

    def test_a_press_that_changed_the_screen_resets_the_count(self):
        watch = FrozenWatch()
        for value in (50, 50, 90, 90):
            watch.look(_frame(value), now=0.0)
            watch.pressed((0.1, 0.5))
        self.assertEqual(1, watch.ineffective)


if __name__ == "__main__":
    unittest.main()
