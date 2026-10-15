"""Leo 2026-10-14: every number read by OCR stays in a sane range."""

import unittest

from src.tasks.quick_hunt import quick_hunt_free_pool
from src.utils.ocr_numbers import pool_amount, within
from src.utils.pvp_dialog import parse_free_cocktails, parse_multiplier


class PoolAmountTest(unittest.TestCase):
    def test_an_amount_within_its_top_is_kept(self):
        self.assertEqual(3, pool_amount(3, 5))
        self.assertEqual(0, pool_amount(0, 90))

    def test_an_amount_above_its_top_is_refused_not_guessed(self):
        self.assertIsNone(pool_amount(25, 5))
        self.assertIsNone(pool_amount(124, 90))

    def test_no_fit_or_an_absurd_top_is_refused(self):
        self.assertIsNone(pool_amount(3, 0))
        self.assertIsNone(pool_amount(3, 5000))

    def test_within(self):
        self.assertEqual(4, within(4, 1, 40))
        self.assertIsNone(within(41, 1, 40))
        self.assertIsNone(within(None, 1, 40))


class ParsersTest(unittest.TestCase):
    def test_pvp_free_cocktails_never_above_the_pool(self):
        self.assertEqual(12, parse_free_cocktails("12/40"))
        self.assertIsNone(parse_free_cocktails("70/40"))

    def test_pvp_multiplier_range(self):
        self.assertEqual(20, parse_multiplier("20倍"))
        self.assertIsNone(parse_multiplier("90倍"))

    def test_quick_hunt_free_rice_never_above_the_pool(self):
        self.assertEqual(84, quick_hunt_free_pool("84/90 +5.6K"))
        self.assertIsNone(quick_hunt_free_pool("124/90"))



if __name__ == "__main__":
    unittest.main()
