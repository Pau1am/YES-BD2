"""Leo 2026-10-14: the gap between skill presses is the player's, 0.5-2 s."""

import unittest
from types import SimpleNamespace

from src.tasks.map_trade.collector_skills import SkillExecutionMixin


class SkillIntervalTest(unittest.TestCase):
    def _interval(self, config):
        skills = object.__new__(SkillExecutionMixin)
        skills.task = SimpleNamespace(config=config)
        return skills._click_interval()

    def test_default_and_range(self):
        self.assertEqual(1.2, self._interval({}))
        self.assertEqual(0.8, self._interval({"技能间隔秒数": 0.8}))
        self.assertEqual(0.5, self._interval({"技能间隔秒数": 0.1}))
        self.assertEqual(2.0, self._interval({"技能间隔秒数": 9}))
        self.assertEqual(1.2, self._interval({"技能间隔秒数": "abc"}))


if __name__ == "__main__":
    unittest.main()
