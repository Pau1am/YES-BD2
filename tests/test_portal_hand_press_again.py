"""跑图: the portal-circle hand (交互) is pressed once more when it stays.

A player (B站 cwbdsg, 2026-10-11): 「点不到那个手，它就会找快速移动找狩猎场虽然
也能跑 但跑一张图要3分钟左右」.  The hand was pressed once; a press the game
dropped cost the 10 s map wait and then the way round via 狩猎场.
"""

import unittest
from types import SimpleNamespace

from src.tasks.map_trade.navigator import Navigator
from src.utils.vision_models import MatchResult


class _Screen:
    """The hand stays until a press lands; ``lands`` says which presses do."""

    def __init__(self, lands, flicker=False):
        self.lands = list(lands)
        self.hand = True
        self.flicker = flicker
        self.presses = 0
        self.looks = 0

    def capture(self):
        self.looks += 1
        return SimpleNamespace(shape=(1080, 1920, 3))

    def match(self, _frame, _spec):
        shown = self.hand and not (self.flicker and self.presses and self.looks % 2)
        return MatchResult(0.99 if shown else 0.1, (1500, 900), (60, 60), 0.99, 0.99)

    def passes(self, result, _spec):
        return result.score > 0.9

    def click_client(self, _center, _shape, after_sleep=0):
        self.presses += 1
        if self.lands.pop(0) if self.lands else False:
            self.hand = False


def navigator(screen):
    logs = []
    task = SimpleNamespace(
        info_set=lambda *_a: None, sleep=lambda *_a: None, log_info=logs.append
    )
    nav = Navigator(task, SimpleNamespace())
    nav.vision = screen
    nav.task = task
    nav._status = lambda *_a: None
    nav.logs = logs
    return nav


class PortalHandPressAgainTest(unittest.TestCase):
    def test_a_dropped_press_is_pressed_again(self):
        screen = _Screen(lands=(False, True))
        nav = navigator(screen)
        self.assertTrue(nav._click_sandbox_teleport_interaction())
        self.assertEqual(2, screen.presses)
        self.assertTrue(any("再按一次" in line for line in nav.logs))

    def test_a_press_that_works_is_pressed_once(self):
        screen = _Screen(lands=(True,))
        self.assertTrue(navigator(screen)._click_sandbox_teleport_interaction())
        self.assertEqual(1, screen.presses)

    def test_at_most_two_presses(self):
        screen = _Screen(lands=(False, False, False))
        self.assertTrue(navigator(screen)._click_sandbox_teleport_interaction())
        self.assertEqual(2, screen.presses)

    def test_no_second_press_when_the_hand_is_gone_even_once(self):
        # The map may be opening: one look without the hand stops the re-press.
        screen = _Screen(lands=(False,), flicker=True)
        self.assertTrue(navigator(screen)._click_sandbox_teleport_interaction())
        self.assertEqual(1, screen.presses)


if __name__ == "__main__":
    unittest.main()
