"""每日精炼: the item popup's buttons are read when the popup is taller.

A player's 问题摘要 (v0.1.19, 1920x1080 fullscreen at 125%, 2026-10-11):
「第5行第6列的装备详情里没有精炼按钮（按钮处读到「没读到字」）」 three times, with
卸除 / 精炼 plainly on the screen.  That item lists 基本能力 and three 属性
lines, so the popup is taller and its buttons sit at y 762-796; the read box
(1150, 700, 320, 70) ended at 770 and read nothing (proven with real OCR on the
summary's frame).  On Leo's frames the buttons are at 717-752.

Fixtures (1080 coordinates): the player's whole popup (x 450-1600, y 280-900)
and the button area (x 1150-1560, y 680-880) of the player's frame (from the
summary, scaled down once) and of Leo's 1080p frame (2026-10-10).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.GearTasks import DETAIL_BUTTONS_ROI, plain_refine_box, refine_pill_point

HERE = Path(__file__).resolve().parent / "fixtures" / "refine"
OLD_ROI = (1150, 700, 320, 70)


def frame_with(name):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    part = cv2.imread(str(HERE / name))
    frame[680 : 680 + part.shape[0], 1150 : 1150 + part.shape[1]] = part
    return frame


def read(frame, roi):
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr

    try:
        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False)
    except ImportError:
        engine = ONNXPaddleOcr(use_angle_cls=False)
    x, y, w, h = roi
    boxes = []
    for points, (text, _score) in engine.ocr(frame[y : y + h, x : x + w], cls=False)[0] or []:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        boxes.append(SimpleNamespace(
            name=text, x=x + min(xs), y=y + min(ys), width=max(xs) - min(xs),
            height=max(ys) - min(ys),
        ))
    return boxes


def whole_popup():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[280:900, 450:1600] = cv2.imread(str(HERE / "tall_popup_player_1080.jpg"))
    return frame


class TallPopupTest(unittest.TestCase):
    def test_refine_is_found_anywhere_in_the_whole_popup(self):
        # Leo 2026-10-11 「只要辨別到 精煉就可了吧」: the whole popup is read and
        # only the button reads exactly 精炼.
        boxes = read(whole_popup(), DETAIL_BUTTONS_ROI)
        button = plain_refine_box(boxes)
        self.assertIsNotNone(button)
        self.assertTrue(762 <= button.y + button.height / 2 <= 796)
        self.assertEqual(1, sum(1 for box in boxes if "精炼" in box.name))

    def test_the_players_buttons_were_outside_the_old_box(self):
        frame = frame_with("tall_popup_buttons_player_1080.png")
        self.assertIsNone(plain_refine_box(read(frame, OLD_ROI)))
        button = plain_refine_box(read(frame, DETAIL_BUTTONS_ROI))
        self.assertIsNotNone(button)
        self.assertTrue(762 <= button.y + button.height / 2 <= 796)

    def test_leos_buttons_are_still_read(self):
        frame = frame_with("popup_buttons_leo_1080.png")
        self.assertIsNotNone(plain_refine_box(read(frame, DETAIL_BUTTONS_ROI)))

    def test_the_right_pill_is_found_at_either_height(self):
        x, y = refine_pill_point(frame_with("tall_popup_buttons_player_1080.png"))
        self.assertTrue(762 <= y <= 796)
        self.assertTrue(1340 <= x <= 1383)
        _x, y = refine_pill_point(frame_with("popup_buttons_leo_1080.png"))
        self.assertTrue(717 <= y <= 752)
        big = cv2.resize(frame_with("popup_buttons_leo_1080.png"), (3840, 2160))
        self.assertTrue(717 <= refine_pill_point(big)[1] <= 752)

    def test_no_pill_without_a_popup(self):
        self.assertIsNone(refine_pill_point(np.zeros((1080, 1920, 3), np.uint8)))
        self.assertIsNone(refine_pill_point(None))


if __name__ == "__main__":
    unittest.main()
