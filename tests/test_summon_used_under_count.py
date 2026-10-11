"""跑图: a used 召集 icon under its 「0/7」 count is still recognised.

A player's run (v0.1.19 log and v0.1.21 问题摘要, 1920x1080 fullscreen at
125%, Q_sp1 战斗区域1, 2026-10-11) stopped with 「技能栏部分识别但未确认：
吸收=used, 召集=absent, 制服=used」.  The log shows 召集 at its slot with
m=0.984 z=0.885 g=0.795 e=0.912 but pixel 0.649 < 0.66, three samples alike.

The fixture is the skill bar only (x 1300-1920, y 640-1080) from the summary's
frame (scaled down once, so it reads a little worse than live: 0.645).
"""

import unittest
from pathlib import Path

import cv2
import numpy as np

from src.tasks.map_trade.action_icons import (
    ABSORB_ICON,
    SUBDUE_ICON,
    SUMMON_ICON,
    ActionIconDetector,
    ActionIconState,
)
from src.tasks.map_trade.vision import Vision
from tests.test_map_trade_video_regression import _VideoFixtureTask

BAR = Path(__file__).parent / "fixtures" / "map_trade" / "skill_bar"
FIXTURE = BAR / "summon_used_under_count_player_1080.png"


def player_frame():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[640:1080, 1300:1920] = cv2.imread(str(FIXTURE))
    return frame


class SummonUnderCountTest(unittest.TestCase):
    def test_all_three_collection_icons_read_used(self):
        detector = ActionIconDetector(Vision(_VideoFixtureTask()))
        frame = player_frame()
        for icon in (ABSORB_ICON, SUMMON_ICON, SUBDUE_ICON):
            with self.subTest(icon=icon.name):
                self.assertEqual(ActionIconState.USED, detector.detect(frame, icon).state)

    def test_no_icon_on_an_empty_bar(self):
        detector = ActionIconDetector(Vision(_VideoFixtureTask()))
        blank = np.zeros((1080, 1920, 3), np.uint8)
        for icon in (ABSORB_ICON, SUMMON_ICON, SUBDUE_ICON):
            with self.subTest(icon=icon.name):
                self.assertEqual(ActionIconState.ABSENT, detector.detect(blank, icon).state)


if __name__ == "__main__":
    unittest.main()
