"""跑商 shop title: read again with more room when the small box reads nothing.

A player's 每日跑商 (v0.1.21, 1920×1080 windowed, scaling 250%, 2026-10-11)
stopped with 「卖：未能通过标题区域确认已切换到出售页面，OCR=-」 while the
shop showed 「购买」: nothing was read, so 出售 was never pressed.  The same
frame read 「购买」 every time with some room around the title, including
with the fixed-size OCR input a PC with an NPU uses.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.map_trade.trader import Trader
from src.tasks.map_trade.trader_constants import (
    SELL_MODE_POINT,
    SHOP_MODE_TITLE_REGION,
    SHOP_MODE_TITLE_WIDER_REGION,
)
from src.utils.image_utils import relative_roi_frame

FIXTURES = Path(__file__).parent / "fixtures" / "map_trade"
# The player's frame around the title, cut at the wider region's 1080p bounds.
PLAYER_TITLE = "shop_title_buy_player_1080.png"
PLAYER_TITLE_ORIGIN = (186, 4)


def _trader(reads, clicks, warnings=None):
    """reads: {region: [text per look]}; an exhausted list keeps its last text."""
    calls = []

    def ocr_text(_frame, name, relative_roi):
        calls.append((name, relative_roi))
        texts = reads.get(relative_roi, [""])
        return texts.pop(0) if len(texts) > 1 else texts[0]

    trader = object.__new__(Trader)
    trader.task = SimpleNamespace(
        operate_click=lambda x, y, after_sleep=0: clicks.append((x, y)),
        sleep=lambda *_args: None,
        log_info=lambda *_args, **_kwargs: None,
        log_warning=(warnings.append if warnings is not None else lambda *_a: None),
        info_set=lambda *_args: None,
    )
    trader.vision = SimpleNamespace(
        capture=lambda: np.zeros((1080, 1920, 3), dtype=np.uint8),
        ocr_text=ocr_text,
        simplify=lambda value: value,
    )
    trader.calls = calls
    return trader


class ShopTitleReadTest(unittest.TestCase):
    def test_an_unread_title_is_read_again_and_出售_pressed(self):
        clicks = []
        trader = _trader(
            {
                SHOP_MODE_TITLE_REGION: [""],
                SHOP_MODE_TITLE_WIDER_REGION: ["购买", "出售"],
            },
            clicks,
        )
        self.assertTrue(trader._ensure_sell_page())
        self.assertEqual([SELL_MODE_POINT], clicks)

    def test_a_read_title_needs_no_second_read(self):
        clicks = []
        trader = _trader({SHOP_MODE_TITLE_REGION: ["出售"]}, clicks)
        self.assertTrue(trader._ensure_sell_page())
        self.assertEqual(
            [SHOP_MODE_TITLE_REGION], [region for _name, region in trader.calls]
        )

    def test_nothing_read_anywhere_presses_nothing(self):
        clicks, warnings = [], []
        trader = _trader({}, clicks, warnings)
        self.assertFalse(trader._ensure_sell_page(timeout=0.0))
        self.assertEqual([], clicks)
        self.assertIn("OCR=-", warnings[-1])

    def test_after_buying_an_unread_sell_title_is_read_again(self):
        clicks = []
        trader = _trader(
            {SHOP_MODE_TITLE_REGION: [""], SHOP_MODE_TITLE_WIDER_REGION: ["出售"]},
            clicks,
        )
        trader.vision.match = lambda *_args: self.fail("出售页不应等售罄")
        self.assertTrue(trader._switch_from_completed_buy_to_sell())
        self.assertEqual([], clicks)

    def test_the_wider_region_holds_the_title_and_leaves_the_tabs_out(self):
        left, top, right, bottom = SHOP_MODE_TITLE_WIDER_REGION
        small = SHOP_MODE_TITLE_REGION
        self.assertTrue(left < small[0] and top < small[1])
        self.assertTrue(right > small[2] and bottom > small[3])
        # The left 购买 / 出售 tabs start at y 165 (1080p): never in the region.
        self.assertLess(bottom * 1080, 165)


try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class PlayerFrameTest(unittest.TestCase):
    """The player's title, read by the OCR as a normal PC and as an NPU PC runs it."""

    @classmethod
    def setUpClass(cls):
        image = cv2.imread(str(FIXTURES / PLAYER_TITLE))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = PLAYER_TITLE_ORIGIN
        frame[y : y + image.shape[0], x : x + image.shape[1]] = image
        cls.frame = frame
        cls.engines = {
            "cpu": ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False),
            # An NPU takes one fixed input size; this is the same on a CPU.
            "fixed size": ONNXPaddleOcr(
                use_angle_cls=False,
                use_openvino=True,
                use_npu=False,
                force_static_shape=True,
            ),
        }

    def _title(self, engine):
        def ocr_text(frame, _name, relative_roi):
            _left, _top, crop = relative_roi_frame(frame, relative_roi)
            lines = engine.ocr(crop)[0] or []
            return " ".join(text for _box, (text, score) in lines if score >= 0.2)

        trader = object.__new__(Trader)
        trader.vision = SimpleNamespace(ocr_text=ocr_text, simplify=lambda value: value)
        return trader._shop_mode_title(self.frame)

    def test_the_players_title_reads_购买(self):
        for name, engine in self.engines.items():
            with self.subTest(engine=name):
                self.assertIn("购买", self._title(engine))


if __name__ == "__main__":
    unittest.main()
