"""爛装强化分解: a taller item popup sits higher (player report 2026-10-12).

The detail popup is centred, so an item with 基本能力 and 属性 rows (猎人之弓
SR, 莉兹内's exclusive, from the player's 问题摘要 at 2560x1440) shows its
name, lock switch and ✕ about 130 px higher than 首席勋章's, and its buttons
lower.  The fixed boxes read no name ("识别装备失败") and the fixed ✕ press
landed inside the popup twice ("关闭装备详情：按了2次都没看到结果").
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.utils.junk_gear import POPUP_CLOSE_REFERENCE_Y, popup_close_point, popup_shift

FIXTURES = Path(__file__).parent / "fixtures" / "junk_gear"

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None


def _tall_bow():
    return cv2.imread(str(FIXTURES / "detail_sr_tall_hunter_bow_player_1440_at_1080.jpg"))


def _short_emma():
    """首席勋章's popup (the boxes' reference) pasted back into a 1080 frame."""
    from src.tasks.JunkGearTask import DETAIL_ROI

    frame = np.zeros((1080, 1920, 3), np.uint8)
    x, y, width, height = DETAIL_ROI
    frame[y : y + height, x : x + width] = cv2.imread(
        str(FIXTURES / "detail_r_exclusive_emma_4k_at_1080.jpg")
    )
    return frame


class CloseCrossTest(unittest.TestCase):
    def test_the_cross_is_found_where_each_popup_has_it(self):
        x, y = popup_close_point(_short_emma())
        self.assertAlmostEqual(1419, x, delta=4)
        self.assertAlmostEqual(POPUP_CLOSE_REFERENCE_Y, y, delta=3)
        x, y = popup_close_point(_tall_bow())
        self.assertAlmostEqual(1419, x, delta=4)
        self.assertAlmostEqual(196, y, delta=4)
        self.assertLess(popup_shift(_tall_bow()), -120)
        self.assertEqual(0, popup_shift(np.zeros((1080, 1920, 3), np.uint8)))

    def test_the_rows_move_with_the_popup(self):
        from src.tasks.JunkGearTask import DETAIL_NAME_ROW, LOCK_SWITCH_ROI, JunkGearTask

        self.assertEqual(
            {"name": DETAIL_NAME_ROW, "lock": LOCK_SWITCH_ROI}, JunkGearTask._popup_rois(0)
        )
        rois = JunkGearTask._popup_rois(-129)
        self.assertEqual(DETAIL_NAME_ROW[1] - 129, rois["name"][1])
        self.assertEqual(LOCK_SWITCH_ROI[1] - 129, rois["lock"][1])

    def test_the_wide_read_covers_every_popup_height(self):
        # Leo 「本來裝備詳情欄就有高有低」「不要視窗抓那麼緊」.
        from src.tasks.JunkGearTask import DETAIL_WIDE_ROI

        x, y, width, height = DETAIL_WIDE_ROI
        self.assertLessEqual(y, 196 - 30)  # the tall popup's ✕ and name row
        self.assertGreaterEqual(y + height, 863 + 30)  # its 穿戴 / 强化 buttons

    def test_the_close_press_goes_to_the_cross_on_screen(self):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.capture_frame = _tall_bow
        clicks = []
        task._click_reference = lambda x, y, after_sleep=0: clicks.append((x, y))
        state = {"open": True}
        task._wait_detail = lambda open_, timeout=0: state["open"] == open_

        def press(label, do, confirmed, **kwargs):
            do()
            state["open"] = False
            return confirmed()

        task.press_and_confirm = press
        self.assertTrue(task._close_detail())
        self.assertEqual(1, len(clicks))
        self.assertAlmostEqual(196, clicks[0][1], delta=4)


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class RealTallPopupTest(unittest.TestCase):
    def test_the_tall_popup_reads_name_owner_and_buttons(self):
        from src.tasks.JunkGearTask import JunkGearTask

        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True)

        def boxes(frame, roi, _name):
            x, y, width, height = roi
            found = []
            for points, (text, _score) in engine.ocr(frame[y : y + height, x : x + width])[0] or []:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                found.append(SimpleNamespace(
                    name=text, x=x + min(xs), y=y + min(ys),
                    width=max(xs) - min(xs), height=max(ys) - min(ys),
                ))
            return found

        task = object.__new__(JunkGearTask)
        task.capture_frame = _tall_bow
        task._reference_boxes = boxes
        task._boxes_text = lambda found: " ".join(str(b.name) for b in found)
        task.info_set = lambda *a, **k: None

        self.assertTrue(task._detail_open())
        item, text = task._read_detail()
        self.assertEqual("猎人之弓", item.name)
        self.assertEqual("SR", item.rarity)
        self.assertIn("莉兹内", item.owner_line)
        self.assertFalse(item.locked)
        # The bottom buttons are read too: 卸除 / 精炼 there keep an item.
        self.assertIn("穿戴", text)
        self.assertIn("强化", text)

        # ✕ not found (painted over): the wide read still finds the title.
        hidden = _tall_bow()
        hidden[170:225, 1395:1445] = hidden[240:295, 1395:1445]
        self.assertIsNone(popup_close_point(hidden))
        task.capture_frame = lambda: hidden
        item, _text = task._read_detail()
        self.assertEqual("猎人之弓", item.name)
        self.assertEqual("SR", item.rarity)


if __name__ == "__main__":
    unittest.main()
