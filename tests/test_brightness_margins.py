"""Pixel gates that a brighter screen pushed under (Leo 2026-10-12 根治亮度).

Every template match the test suite makes was measured on its real frames
and again on the same frames made brighter (gamma 0.8) and HDR-washed
(linear x1.5, clipped).  These three gates had the thinnest margins and fell
under on the brighter frames: the 跑图 quick-switch (P) button (0.002-0.013
above 0.85 on bright scenes, 9 of 45 lost), the 交互直传 map header (all 4
lost under HDR) and the cooking MAX slider (0.018 above 0.95, all lost;
that check was removed 2026-10-15).
With ``brightness_tolerant`` they pass again, and what they must reject
still is.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.map_trade.navigator_constants import (
    QUICK_SWITCH_TEMPLATE,
    TELEPORT_MAP_DIRECT_HEADER_TEMPLATE,
)
from src.tasks.map_trade.vision import TEMPLATE_DIR
from src.utils import task_vision
from tests.test_quick_switch_bright_field import OTHER_PAGES, SIZES, frame_4k, scenes, sized

FIXTURES = Path(__file__).parent / "fixtures"


def _lut(fn):
    return np.clip(np.round(fn(np.arange(256, dtype=np.float64))), 0, 255).astype(np.uint8)


def _to_linear(v):
    v = v / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _to_srgb(v):
    v = np.clip(v, 0.0, 1.0)
    return 255.0 * np.where(v <= 0.0031308, v * 12.92, 1.055 * np.power(v, 1 / 2.4) - 0.055)


VARIANTS = {
    "as captured": None,
    "brighter": _lut(lambda v: 255.0 * (v / 255.0) ** 0.8),
    "hdr": _lut(lambda v: _to_srgb(_to_linear(v) * 1.5)),
}


def _variant(frame, table):
    return frame if table is None else cv2.LUT(np.ascontiguousarray(frame[:, :, :3]), table)


def _passes(frame, spec) -> bool:
    result = task_vision.match_template(frame, spec, {}, TEMPLATE_DIR, cache={}, min_size=4)
    return task_vision.passes_match(result, spec, {})


class QuickSwitchTest(unittest.TestCase):
    def test_bright_scenes_pass_brighter_and_under_hdr(self):
        for scene in scenes():
            source = frame_4k(scene)
            for width, height in SIZES:
                frame = sized(source, width, height)
                for name, table in VARIANTS.items():
                    with self.subTest(scene=scene, size=width, variant=name):
                        self.assertTrue(_passes(_variant(frame, table), QUICK_SWITCH_TEMPLATE))

    def test_other_pages_still_have_no_quick_switch(self):
        for page in OTHER_PAGES + ("quick_switch/home_bottom_strip_1600x901.png",):
            frame = cv2.imread(str(FIXTURES / page), cv2.IMREAD_COLOR)
            for name, table in VARIANTS.items():
                with self.subTest(page=page, variant=name):
                    self.assertFalse(_passes(_variant(frame, table), QUICK_SWITCH_TEMPLATE))


class TeleportHeaderTest(unittest.TestCase):
    def test_direct_page_header_passes_and_others_do_not(self):
        pages = FIXTURES / "map_trade" / "map_pages"
        for page, expected in (("direct", True), ("generate", False), ("sandbox_large", False)):
            source = cv2.imread(str(pages / f"{page}.png"), cv2.IMREAD_COLOR)
            for height in (720, 1080, 1440, 2160):
                width = height * 16 // 9
                interpolation = cv2.INTER_AREA if height < 1080 else cv2.INTER_CUBIC
                frame = cv2.resize(source, (width, height), interpolation=interpolation)
                for name, table in VARIANTS.items():
                    with self.subTest(page=page, height=height, variant=name):
                        self.assertEqual(
                            expected, _passes(_variant(frame, table), TELEPORT_MAP_DIRECT_HEADER_TEMPLATE)
                        )


if __name__ == "__main__":
    unittest.main()
