"""第6章 is done for the week with 压制 ticked and 吸取 showing 「2」, or both
ticked (Leo 2026-10-20 「第六章跑過就是我現在這個狀態 所以不要再跑」)."""

import unittest
from types import SimpleNamespace

import numpy as np

from src.tasks.map_trade.card_status import (
    CardActionDetection,
    CardActionState,
    CardIconEvidence,
    CollectionCardSelectionOutcome,
    StoryCardCompletion,
)
from src.tasks.map_trade.models import MatchResult, NavigationResult, ScreenState
from src.tasks.map_trade.navigator_story import StoryCardNavigationMixin

DONE = CardActionDetection(CardActionState.COMPLETED)
NONE = CardActionDetection(CardActionState.UNKNOWN, reason="no badge")


def _open_absorb():
    evidence = CardIconEvidence(MatchResult(0.99, (100, 900), (40, 40)), 0.3, 0.0, 0.5)
    return CardActionDetection(CardActionState.PENDING, pending=(evidence,))


def _select(card_id, absorb, suppress, number):
    nav = StoryCardNavigationMixin.__new__(StoryCardNavigationMixin)
    located = SimpleNamespace(
        frame=np.zeros((1080, 1920, 3), np.uint8),
        badge=SimpleNamespace(best=SimpleNamespace(result=SimpleNamespace(center=(530, 1000)))),
    )
    entered = []
    nav._locate_story_card = lambda _card_id: located
    nav.card_status = SimpleNamespace(
        detect=lambda _frame, _center: StoryCardCompletion(absorb, suppress, (0, 0, 1, 1), True)
    )
    nav._status = lambda *_args: None
    nav.vision = SimpleNamespace(ocr_text=lambda *_a, **_k: number)

    def enter(_located):
        entered.append(card_id)
        return NavigationResult(True, ScreenState.SANDBOX, "entered")

    nav._enter_located_story_card = enter
    return nav.select_collection_card(card_id).outcome, entered


class Chapter6BadgeTest(unittest.TestCase):
    def test_suppress_ticked_and_two_left_is_done(self):
        outcome, entered = _select("Q_sp6", _open_absorb(), DONE, "2")
        self.assertEqual(CollectionCardSelectionOutcome.VISUALLY_COMPLETE, outcome)
        self.assertEqual([], entered)

    def test_both_ticked_is_done(self):
        outcome, entered = _select("Q_sp6", DONE, DONE, "")
        self.assertEqual(CollectionCardSelectionOutcome.VISUALLY_COMPLETE, outcome)
        self.assertEqual([], entered)

    def test_more_left_means_a_map_is_still_to_do(self):
        outcome, entered = _select("Q_sp6", _open_absorb(), DONE, "9")
        self.assertEqual(CollectionCardSelectionOutcome.ENTERED, outcome)
        self.assertEqual(["Q_sp6"], entered)

    def test_unread_number_goes_by_the_suppress_tick(self):
        outcome, _entered = _select("Q_sp6", _open_absorb(), DONE, "")
        self.assertEqual(CollectionCardSelectionOutcome.VISUALLY_COMPLETE, outcome)

    def test_suppress_open_is_run(self):
        outcome, entered = _select("Q_sp6", _open_absorb(), _open_absorb(), "2")
        self.assertEqual(CollectionCardSelectionOutcome.ENTERED, outcome)
        self.assertEqual(["Q_sp6"], entered)


if __name__ == "__main__":
    unittest.main()
