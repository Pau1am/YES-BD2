"""广场女神像: the daily row is read over a busy backdrop (real OCR).

A player's 问题摘要 (v0.1.21, 1920×1080 windowed, 2026-10-11) stopped at
「未确认每日导航」 with 「每日奖励 / 移动至艾力克史温女…」 drawn over the square's
pink food truck (Leo: 「那個位置常常有不同東西 上次是雕像」).  The fixture keeps
only the task list and the truck behind it, from the summary's frame (already
scaled down once, so it reads worse than a live frame).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.utils.goddess_navigation import is_daily_title, scan_navigation

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "goddess" / "task_row_over_food_truck_1080.png"
)


def _engine():
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr

    try:
        return ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False)
    except ImportError:
        return ONNXPaddleOcr(use_angle_cls=False)


def _ocr(engine):
    def ocr(frame, threshold, target_height=0, log=False):
        boxes = []
        for points, (text, score) in engine.ocr(frame, cls=False)[0] or []:
            if score < threshold:
                continue
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            boxes.append(SimpleNamespace(
                name=text, confidence=score, x=min(xs), y=min(ys),
                width=max(xs) - min(xs), height=max(ys) - min(ys),
            ))
        return boxes

    return ocr


class TaskRowOverBackdropTest(unittest.TestCase):
    def test_the_row_over_the_food_truck_is_found(self):
        try:
            engine = _engine()
        except Exception as exc:  # pragma: no cover - OCR missing on this machine
            self.skipTest(f"onnxocr unavailable: {exc}")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        crop = cv2.imread(str(FIXTURE))
        frame[0:540, 1190:1920] = crop
        observation = scan_navigation(
            frame, ocr=_ocr(engine), normalize=lambda text: text,
            match=lambda *_a: None, passes=lambda *_a: False, icon_specs=(),
        )
        self.assertEqual("ready", observation.state, observation.text)
        x, y = observation.navigation.center
        # 「移动至艾力克史温女…」 sits right of the E key, under 每日奖励.
        self.assertTrue(1560 <= x <= 1800 and 200 <= y <= 250, (x, y))

    def test_one_misread_reward_character_still_counts_as_the_daily_title(self):
        self.assertTrue(is_daily_title("每日买励"))
        self.assertTrue(is_daily_title("每日奖励"))
        self.assertFalse(is_daily_title("每日任务"))


if __name__ == "__main__":
    unittest.main()
