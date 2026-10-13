"""YES-BD2 #24 (1080p): weekly map runs stopped on the sandbox large map.

1. After a destination was picked, the game asked 「是否自动移动前往所选目的地？」.
   Its title 自动移动 was read as the walk banner, so 确认 was never pressed.
2. On snow both page arrows miss their templates, so the page was never
   identified, never closed, and going home found "no safe path".
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2

from src.tasks.map_trade.models import MapPageMode, NavigationResult, ScreenState
from src.tasks.map_trade.navigator import Navigator
from src.tasks.map_trade.vision import Vision

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None

FIXTURES = Path(__file__).resolve().parent / "fixtures/map_trade/map_pages"


class AutoMoveQuestionTest(unittest.TestCase):
    def test_the_question_is_not_the_walk_banner(self):
        self.assertTrue(Navigator._auto_move_question_shown("自动移动是否自动移动前往所选目的地"))
        self.assertFalse(Navigator._auto_move_question_shown("自动移动中魔法阵"))
        self.assertFalse(Navigator._auto_move_question_shown("已完成自动移动"))

    def test_going_home_closes_the_dialog_first(self):
        calls = []
        navigator = Navigator(SimpleNamespace(), SimpleNamespace())
        navigator._discount_close_dialog_shown = lambda: False
        navigator._cancel_auto_move_dialog = lambda *_a: calls.append("cancel") or True
        navigator.classify = lambda *_a: calls.append("classify") or ScreenState.HOME

        result = navigator._return_home_pass()

        self.assertEqual(NavigationResult(True, ScreenState.HOME), result)
        self.assertEqual(["cancel", "classify"], calls)

    def test_no_question_presses_nothing(self):
        clicks = []
        vision = SimpleNamespace(
            ocr_boxes=lambda *_a, **_k: [
                SimpleNamespace(name="取消", x=800, y=640, width=60, height=30)
            ],
            simplify=lambda text: text,
            click_client=lambda *a, **_k: clicks.append(a),
        )
        navigator = Navigator(SimpleNamespace(), vision)
        navigator._status = lambda *_a: None

        self.assertFalse(navigator._cancel_auto_move_dialog("frame"))
        self.assertEqual([], clicks)


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class PlayerFramesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False)

        def ocr(*, frame, threshold=0.2, **_kwargs):
            boxes = []
            for points, (text, score) in engine.ocr(frame)[0] or []:
                if score < threshold:
                    continue
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                boxes.append(
                    SimpleNamespace(
                        name=text,
                        x=min(xs),
                        y=min(ys),
                        width=max(xs) - min(xs),
                        height=max(ys) - min(ys),
                        confidence=score,
                    )
                )
            return boxes

        cls.ocr = staticmethod(ocr)

    def _navigator(self, name):
        frame = cv2.imread(str(FIXTURES / name))
        self.assertIsNotNone(frame)
        clicks = []
        task = SimpleNamespace(config={}, ocr=self.ocr, info_set=lambda *_a: None)
        vision = Vision(task)
        vision.click_client = lambda center, _shape, after_sleep=0: clicks.append(center)
        return Navigator(task, vision), frame, clicks

    def test_snow_large_map_is_identified_without_its_arrows(self):
        navigator, frame, _clicks = self._navigator("snow_large_map_player_fhd.jpg")

        self.assertEqual(
            MapPageMode.SANDBOX_LARGE_MAP, navigator._detect_map_page_mode(frame).mode
        )

    def test_dialog_frame_reads_the_question_and_presses_cancel(self):
        navigator, frame, clicks = self._navigator("auto_move_dialog_player_fhd.jpg")

        self.assertTrue(navigator._auto_move_question_shown(navigator._walk_text(frame)))
        self.assertTrue(navigator._cancel_auto_move_dialog(frame))
        # 取消 is the left button (1080p ~838,654); 确认 sits at ~1081.
        self.assertEqual(1, len(clicks))
        x, y = clicks[0]
        self.assertLess(abs(x - 838), 40)
        self.assertLess(abs(y - 654), 30)

    def test_dialog_frame_has_its_confirm_button(self):
        navigator, frame, _clicks = self._navigator("auto_move_dialog_player_fhd.jpg")

        label, (x, _y) = navigator._sandbox_navigation_destination_button(frame)

        self.assertEqual("确认", label)
        self.assertGreater(x, 960)


if __name__ == "__main__":
    unittest.main()
