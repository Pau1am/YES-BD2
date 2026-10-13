"""Leo 2026-10-13 「感覺每個按鍵都要等個2秒」: the pause after a recognised cue
is 0.3 s.  The setting got a new name so the change applies once: an old
saved value other than the old 1.0 default moves over."""

import unittest
from types import SimpleNamespace

from src.tasks.BaseBD2Task import (
    RECOGNITION_SETTLE_KEY,
    RECOGNITION_SETTLE_SECONDS,
    BaseBD2Task,
    recognition_settle_from_old,
)

OLD_KEY = "识别成功后等待秒数"


def _slept(config):
    slept = []
    task = SimpleNamespace(config=config, sleep=slept.append)
    BaseBD2Task._sleep_after_recognition(task)
    return slept


class WaitAfterRecognitionTest(unittest.TestCase):
    def test_default_is_short(self):
        self.assertEqual([RECOGNITION_SETTLE_SECONDS], _slept({}))
        self.assertLessEqual(RECOGNITION_SETTLE_SECONDS, 0.3)

    def test_the_setting_is_used(self):
        self.assertEqual([1.0], _slept({RECOGNITION_SETTLE_KEY: 1.0}))
        self.assertEqual([], _slept({RECOGNITION_SETTLE_KEY: 0}))


class MigrationTest(unittest.TestCase):
    def test_old_default_takes_the_new_one(self):
        self.assertIsNone(recognition_settle_from_old({OLD_KEY: 1.0}))

    def test_a_changed_old_value_moves_over(self):
        self.assertEqual(2.0, recognition_settle_from_old({OLD_KEY: 2.0}))
        self.assertEqual(0.0, recognition_settle_from_old({OLD_KEY: 0}))

    def test_only_once(self):
        # Once the new key is saved, the old one is never read again.
        self.assertIsNone(
            recognition_settle_from_old({OLD_KEY: 2.0, RECOGNITION_SETTLE_KEY: 1.0})
        )
        self.assertIsNone(recognition_settle_from_old({}))
        self.assertIsNone(recognition_settle_from_old({OLD_KEY: "x"}))


if __name__ == "__main__":
    unittest.main()
