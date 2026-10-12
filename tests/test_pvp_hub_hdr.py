"""YES-BD2 #16 (2026-10-11, v0.1.23, 1080p window on an HDR 2560 monitor):
镜中之战 stood in the PVP hub but logged 「未能进入 PVP 箱庭」 with hub=-1.000
on every frame.  The medal matched by shape (0.95+) while the plain grey
difference fell under 0.88: the whole frame was brighter.  The older test
frame came from a normal SDR screen only, so no test saw a shifted one.

The same player's 广场女神像 stop (frame in the second test class) had the
same cause on the square's quick-switch button.

Frames: the player's hub top bar (rebuilt from a half-size screenshot of
the issue, medal strip only; it sits right at the old 0.88 edge) and the
existing SDR strip, brightened and dimmed.
"""

import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from src.tasks.PVPTask import PVP_MEDALS_TEMPLATE, PVPTask

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None

FIXTURES = Path(__file__).parent / "fixtures" / "pvp"


def _task():
    task = object.__new__(PVPTask)
    task.config = {}
    task._templates = {}
    task._match_pause_until = 0.0
    task._missing_template_names = set()
    task._match_error_names = set()
    task.info = {}
    task.info_set = lambda key, value: task.info.__setitem__(key, value)
    task.log_warning = lambda *a, **k: None
    return task


def _strip(name):
    return cv2.imread(str(FIXTURES / name))


def _shift(frame, gain, lift=0.0):
    return np.clip(frame.astype(np.float32) * gain + lift, 0, 255).astype(np.uint8)


class HubMedalBrightnessTest(unittest.TestCase):
    def _hub(self, frame):
        task = _task()
        return task._passes(task._match(frame, PVP_MEDALS_TEMPLATE), PVP_MEDALS_TEMPLATE)

    def test_the_players_hdr_hub_bar_is_the_hub(self):
        self.assertTrue(self._hub(_strip("pvp_hub_top_bar_hdr_issue16_fhd.png")))

    def test_a_normal_hub_bar_still_passes_as_before(self):
        frame = _strip("pvp_hub_top_bar_shifted_fhd.png")
        self.assertTrue(self._hub(frame))
        result = _task()._match(frame, PVP_MEDALS_TEMPLATE)
        self.assertGreaterEqual(result.pixel_score, 0.93)  # the plain gate, as before

    def test_a_brighter_or_darker_screen_is_the_hub(self):
        frame = _strip("pvp_hub_top_bar_shifted_fhd.png")
        brighter = _shift(frame, 1.25, 25)
        # The old check alone: no medal at all, as in the player's log.
        strict = replace(PVP_MEDALS_TEMPLATE, brightness_tolerant=False)
        self.assertLess(_task()._match(brighter, strict).score, 0)
        self.assertTrue(self._hub(brighter))
        self.assertTrue(self._hub(_shift(frame, 0.85)))

    def test_hub_art_dimmed_behind_a_special_page_is_not_the_hub(self):
        frame = _strip("pvp_hub_top_bar_shifted_fhd.png")
        self.assertFalse(self._hub(_shift(frame, 0.5)))

    def test_an_empty_bar_is_not_the_hub(self):
        self.assertFalse(self._hub(np.zeros((1080, 1920, 3), np.uint8)))

    def test_a_bright_home_glow_is_not_the_hub(self):
        # Player 2026-10-12 (v0.1.24, 1080p window, HDR off): 一键日常 went
        # from 女神像 straight to 镜中之战 on 主页, took the soft white glow
        # of the home art for the medal and searched 30 s for the stage
        # instead of opening 游戏卡珍藏集.  Its shape scores 0.86 and, with
        # the contrast stretched up to the medal's, its pixels pass 0.88.
        from src.tasks.PVPTask import TEMPLATE_DIR
        from src.utils import image_utils, task_vision

        frame = _strip("home_bright_skin_cues_fhd.png")
        self.assertFalse(self._hub(frame))
        loose = _task()._match(
            frame, replace(PVP_MEDALS_TEMPLATE, min_pixel_score=0.0, brightness_tolerant=False)
        )
        self.assertGreater(loose.score, PVP_MEDALS_TEMPLATE.default_threshold)
        template, mask = task_vision.load_template(TEMPLATE_DIR, PVP_MEDALS_TEMPLATE, cache={})
        (x, y), (width, height) = loose.position, loose.size
        similarity, _ratio, contrast = image_utils.brightness_matched_similarity(
            image_utils.to_gray(frame)[y : y + height, x : x + width],
            cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA),
            None
            if mask is None
            else cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST),
        )
        self.assertGreaterEqual(similarity, PVP_MEDALS_TEMPLATE.min_pixel_score)
        self.assertLess(contrast, task_vision.BRIGHTNESS_SHIFT_MIN_CONTRAST)



@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class BrightHomeSkinTest(unittest.TestCase):
    def test_the_players_home_is_read_as_home_and_the_cartridge_opened(self):
        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True)

        def ocr(frame, name, roi=None, ocr_scale=1.0):
            x, y, width, height = roi
            crop = frame[y : y + height, x : x + width]
            if ocr_scale != 1.0:
                crop = cv2.resize(crop, None, fx=ocr_scale, fy=ocr_scale)
            return " ".join(text for _points, (text, _score) in engine.ocr(crop)[0] or [])

        frame = _strip("home_bright_skin_cues_fhd.png")
        task = _task()
        task._ocr_text = ocr
        task.capture_frame = lambda: frame
        self.assertTrue(task._home_confirmation_signals(frame)[0])
        task._wait_for_template = lambda *_args, **_kwargs: self.fail("medal asked on 主页")
        entered = []
        task._enter_pvp_from_home = lambda: entered.append(True) or True
        self.assertTrue(task._ensure_pvp_hub())
        self.assertEqual([True], entered)


class SquareQuickSwitchBrightnessTest(unittest.TestCase):
    """Same player, 广场女神像: after the wish the home click did not take, and
    it was never repeated because the square's quick-switch button (the "still
    in the square" check) failed the pixel gate (0.81 < 0.85)."""

    def _match(self, frame, spec):
        from src.tasks.SquareGoddessTask import TEMPLATE_DIR
        from src.utils import task_vision

        return task_vision.match_template(frame, spec, {}, TEMPLATE_DIR, {}, min_size=5)

    def test_the_players_square_still_shows_the_quick_switch(self):
        from src.tasks.SquareGoddessTask import QUICK_SWITCH_TEMPLATE
        from src.utils import task_vision

        frame = _strip("square_quick_switch_hdr_fhd.png")
        strict = replace(QUICK_SWITCH_TEMPLATE, brightness_tolerant=False)
        self.assertLess(self._match(frame, strict).score, 0)
        result = self._match(frame, QUICK_SWITCH_TEMPLATE)
        self.assertTrue(task_vision.passes_match(result, QUICK_SWITCH_TEMPLATE, {}))

    def test_the_button_dimmed_under_an_overlay_is_not_taken(self):
        from src.tasks.SquareGoddessTask import QUICK_SWITCH_TEMPLATE

        frame = _shift(_strip("square_quick_switch_hdr_fhd.png"), 0.45)
        self.assertLess(self._match(frame, QUICK_SWITCH_TEMPLATE).score, 0)


if __name__ == "__main__":
    unittest.main()
