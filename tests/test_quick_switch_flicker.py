"""A see-through button over moving scenery keeps being looked for.

Clone 10-11: 一键日常 ran 常客 just before 镜中之战, so the recent cartridge
was 格鲁菲餐厅.  Its quick-switch button (立刻前往游戏卡) is see-through and
chefs walk behind it; one missed one-second stability window ended the whole
search with most of the timeout left, and PVP failed.
"""

import unittest
from types import SimpleNamespace

import numpy as np

from src.tasks.map_trade.models import MatchResult, TemplateSpec
from src.tasks.map_trade.vision import Vision
from src.tasks.PVPTask import QUICK_PACK_TEMPLATE, PVPTask
from src.tasks.SquareGoddessTask import QUICK_SWITCH_TEMPLATE, SquareGoddessTask
from src.utils.image_utils import STABLE_MATCH_MAX_SAMPLES
from tests.helpers.map_trade import FakeTask

# Every other frame a chef covers the button: no 5-of-6 window can form.
FLICKER = [index % 2 == 0 for index in range(STABLE_MATCH_MAX_SAMPLES)]


class _Matches:
    """Hands out pass/miss matches in order; passes once the list runs out."""

    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        seen = self.sequence[self.calls] if self.calls < len(self.sequence) else True
        self.calls += 1
        score = 0.95 if seen else 0.40
        return SimpleNamespace(
            score=score,
            pixel_score=score,
            zncc_score=score,
            position=(358, 134),
            size=(44, 36),
            center=(380, 152),
        )


def _helper_task(cls, matches):
    task = object.__new__(cls)
    task.config = {}
    task.info_set = lambda *_args, **_kwargs: None
    task.capture_frame = lambda: np.zeros((1080, 1920, 3), dtype=np.uint8)
    task._match = matches
    task._passes = lambda result, _spec: result.score > 0.9
    task._mf_offset_for_frame = lambda *_args: (0, 0)
    task.sleep = lambda _seconds: None
    task.clicks = []
    task._click_client = lambda x, y, *_args, **_kwargs: task.clicks.append((x, y))
    return task


class TaskHelperTest(unittest.TestCase):
    def _check(self, cls, spec):
        matches = _Matches(FLICKER)
        task = _helper_task(cls, matches)
        self.assertTrue(
            cls._click_template_until(
                task, spec, timeout=30.0, name="快速切换按钮", stabilize=True
            )
        )
        self.assertEqual([(380, 152)], task.clicks)
        self.assertGreater(matches.calls, len(FLICKER))

    def test_pvp_looks_again_after_a_missed_window(self):
        self._check(PVPTask, QUICK_PACK_TEMPLATE)

    def test_goddess_looks_again_after_a_missed_window(self):
        self._check(SquareGoddessTask, QUICK_SWITCH_TEMPLATE)

    def test_a_button_never_steady_is_never_pressed(self):
        for cls, spec in (
            (PVPTask, QUICK_PACK_TEMPLATE),
            (SquareGoddessTask, QUICK_SWITCH_TEMPLATE),
        ):
            with self.subTest(cls.__name__):
                task = _helper_task(cls, _Matches(FLICKER * 1000))
                self.assertFalse(
                    cls._click_template_until(
                        task, spec, timeout=0.05, name="快速切换按钮", stabilize=True
                    )
                )
                self.assertEqual([], task.clicks)


class VisionTest(unittest.TestCase):
    def _vision(self, sequence):
        task = FakeTask()
        task.sleep = lambda _seconds: None
        vision = Vision(task)
        matches = iter(sequence)

        def match(*_args, **_kwargs):
            seen = next(matches, True)
            return MatchResult(0.95 if seen else 0.40, (100, 200), (40, 20), pixel_score=0.95)

        vision.match = match
        vision.passes = lambda result, _spec: result.score > 0.9
        return task, vision

    def test_map_vision_looks_again_after_a_missed_window(self):
        task, vision = self._vision(FLICKER)
        self.assertTrue(vision.click_stable_template(TemplateSpec("q", "unused.png"), timeout=30.0))
        self.assertEqual((120 / 1280, 210 / 720, 0.8), task.clicks[-1])

    def test_map_vision_never_presses_a_button_that_never_steadies(self):
        task, vision = self._vision(FLICKER * 1000)
        spec = TemplateSpec("q", "unused.png")
        self.assertFalse(vision.click_stable_template(spec, timeout=0.05))
        self.assertEqual([], task.clicks)


if __name__ == "__main__":
    unittest.main()
