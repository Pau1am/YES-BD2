"""第13章 (snow): the success toast proves a press, no wait for a grey icon
(Leo 2026-10-21 「只有雪山這樣 其他不用改」; 2K 2026-10-20 ~12 s a skill)."""

import unittest
from types import SimpleNamespace

from src.tasks.map_trade.action_icons import ActionIconState
from src.tasks.map_trade.collector import Collector
from src.tasks.map_trade.collector_constants import ABSORB_ACTION, SUMMON_ACTION


def _collector(card_snow):
    collector = object.__new__(Collector)
    collector._snow_card = card_snow
    collector._status = lambda *a: None
    waited = []
    seen = SimpleNamespace(state=ActionIconState.USED)
    collector._icon_state_within = lambda *a: waited.append(a) or (True, None, seen)
    return collector, waited


SUCCESS = SimpleNamespace(outcome="success")
UNREAD = SimpleNamespace(outcome=None)


class SnowCardTest(unittest.TestCase):
    def test_snow_card_with_success_toast_does_not_wait_for_grey(self):
        collector, waited = _collector(True)
        clicked = [(ABSORB_ACTION, None, (3, 21), SUCCESS)]
        self.assertEqual(5.0, collector._settle_before_next_press(clicked, SUMMON_ACTION, 5.0))
        self.assertEqual([], waited)

    def test_snow_card_without_a_toast_still_waits(self):
        collector, waited = _collector(True)
        clicked = [(ABSORB_ACTION, None, (3, 21), UNREAD)]
        collector._settle_before_next_press(clicked, SUMMON_ACTION, 5.0)
        self.assertTrue(waited)

    def test_other_cards_still_wait_for_grey(self):
        collector, waited = _collector(False)
        clicked = [(ABSORB_ACTION, None, (3, 21), SUCCESS)]
        collector._settle_before_next_press(clicked, SUMMON_ACTION, 5.0)
        self.assertTrue(waited)


if __name__ == "__main__":
    unittest.main()
