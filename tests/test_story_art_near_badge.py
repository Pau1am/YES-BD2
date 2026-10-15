"""Live 4K 2026-10-14: card 16 sat in view while its art scored 0.63-0.70
(floor 0.72); the bar slid 12 times (22 s) before the badge found it.  When
the bar's numbers put the card in view, the badge now decides right there."""

import unittest
from types import SimpleNamespace

import numpy as np

from src.tasks.map_trade.navigator import Navigator
from src.tasks.map_trade.navigator_story import STORY_ART_NEAR_BADGE_LOOKS


def _detection():
    result = SimpleNamespace(score=0.99, pixel_score=0.95, zncc_score=0.93)
    return SimpleNamespace(best=SimpleNamespace(result=result), margin=0.07, ocr_number=16)


def _navigator(in_view, badge_finds):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    navigator = Navigator(SimpleNamespace(), SimpleNamespace(capture=lambda: frame))
    navigator._status = lambda *_a: None
    navigator.task = SimpleNamespace(
        sleep=lambda _s: None,
        log_warning=lambda *_a, **_k: None,
        # With swiping available the old blind wheel scan is not used.
        executor=SimpleNamespace(interaction=SimpleNamespace(post_swipe=object())),
    )
    navigator._scan_story_bar_by_swipe = lambda *_a: None
    navigator._badge_category = "story"
    navigator._story_bar_offset = lambda _f: 0.0
    # The first look: off screen, so the bar wheels; every later look in view.
    xs = iter([5000.0] + [960.0 if in_view else 5000.0] * 50)
    navigator._story_card_x = lambda _o, _n: next(xs)
    navigator._scan_story_bar_guided = lambda *_a, **_k: None
    navigator._wheel_story_bar = lambda _larger, _notches: True
    navigator.badge_looks = 0

    def by_art(_frame, _number):
        return None, "相似度低"

    def full(_frame, _number):
        navigator.badge_looks += 1
        return (_detection(), "") if badge_finds else (None, "角标不确定")

    navigator._find_story_card_by_art = by_art
    navigator._find_story_card = full
    return navigator


class NearArtBadgeTest(unittest.TestCase):
    def test_a_near_art_score_lets_the_badge_find_the_card_at_once(self):
        navigator = _navigator(True, badge_finds=True)
        found = navigator._wait_for_story_badge_with_scroll(16)
        self.assertIsNotNone(found)
        self.assertEqual(1, navigator.badge_looks)

    def test_a_card_the_numbers_put_off_screen_gets_no_badge_look(self):
        navigator = _navigator(False, badge_finds=False)
        navigator._wait_for_story_badge_with_scroll(16)
        self.assertEqual(0, navigator.badge_looks)

    def test_near_badge_looks_are_capped(self):
        navigator = _navigator(True, badge_finds=False)
        navigator._wait_for_story_badge_with_scroll(16)
        self.assertEqual(STORY_ART_NEAR_BADGE_LOOKS, navigator.badge_looks)


if __name__ == "__main__":
    unittest.main()
