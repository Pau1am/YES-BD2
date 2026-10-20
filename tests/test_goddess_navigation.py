import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.tasks.SquareGoddessTask import (
    GODDESS_NAVIGATION_CLICKED,
    SquareGoddessTask,
)
from src.utils.goddess_navigation import (
    NEW_DAILY_ICON,
    NavigationObservation,
    TextBox,
    choose_navigation,
    is_goddess_destination,
    scan_navigation,
)


class GoddessNavigationTest(unittest.TestCase):
    def test_destination_preserves_order_and_allows_one_action_typo(self):
        for text in ("移动至艾力克史温女", "多动至艾力克史温女…"):
            self.assertTrue(is_goddess_destination(text))
        for text in ("每日派遣", "移动至其他任务", "女温史克力艾至动移", "艾力", "前往艾力克"):
            self.assertFalse(is_goddess_destination(text))

    def test_destination_wrapped_after_the_first_two_characters(self):
        # Live 2K 2026-10-07: the row broke into "日移动至艾力" | "克史温".
        self.assertTrue(is_goddess_destination("日移动至艾力"))

    def test_title_anchor_scales_and_prefers_but_does_not_require_icon(self):
        for width, height in ((1920, 1080), (1280, 720)):
            for icon_present in (False, True):
                with self.subTest(size=(width, height), icon=icon_present):
                    calls = []

                    def ocr(**kwargs):
                        shape = kwargs["frame"].shape
                        calls.append(shape)
                        if shape[0] == int(height * .75):
                            return [SimpleNamespace(name="每日奖励", confidence=.99,
                                                    x=100, y=100, width=80, height=24)]
                        return [
                            SimpleNamespace(name="每日奖励", confidence=.99,
                                            x=100, y=40, width=100, height=30),
                            SimpleNamespace(name="多动至艾力克史温女", confidence=.99,
                                            x=100, y=75, width=240, height=30),
                        ]

                    observed_rois = []
                    result = scan_navigation(
                        np.zeros((height, width, 3), dtype=np.uint8), ocr=ocr,
                        normalize=lambda text: text,
                        match=lambda frame, spec: observed_rois.append(spec.roi),
                        passes=lambda *args: icon_present, icon_specs=(NEW_DAILY_ICON,),
                    )
                    self.assertEqual((height, width - int(width * .50), 3), calls[0])
                    # The title directly above the goddess destination is enough;
                    # the icon art changes with the task state (2026-09-26).
                    self.assertEqual("ready", result.state)
                    self.assertTrue(observed_rois)
                    if result.navigation:
                        self.assertGreaterEqual(result.navigation.x, int(width * .50))

    def test_icon_row_is_preferred_over_a_text_only_row(self):
        icon_row = TextBox("移动至艾力克史温女", .99, 1100, 335, 240, 30)
        text_row = TextBox("移动至艾力克史温女", .99, 1100, 75, 240, 30)
        result = choose_navigation([icon_row], [text_row], "")
        self.assertEqual("ready", result.state)
        self.assertIs(icon_row, result.navigation)

    def test_text_only_row_is_the_fallback_but_two_are_ambiguous(self):
        row = TextBox("移动至艾力克史温女", .99, 1100, 75, 240, 30)
        other = TextBox("移动至艾力克史温女", .99, 1100, 335, 240, 30)
        self.assertIs(row, choose_navigation([], [row], "").navigation)
        self.assertEqual("ambiguous", choose_navigation([], [row, other], "").state)
        self.assertIsNone(choose_navigation([], [], ""))

    def test_navigation_requires_two_consecutive_stable_observations(self):
        task = object.__new__(SquareGoddessTask)
        task.sleep = lambda *args: None
        task.capture_frame = lambda: np.zeros((720, 1280, 3), dtype=np.uint8)
        first = TextBox("移动至艾力克史温女", .99, 900, 200, 180, 20)
        moved = TextBox("移动至艾力克史温女", .99, 900, 300, 180, 20)
        sequence = iter([
            NavigationObservation("ready", "", first),
            NavigationObservation("unknown", ""),
            NavigationObservation("ready", "", moved),
            NavigationObservation("ready", "", moved),
        ])
        task._observe_goddess_navigation = lambda frame: next(sequence)
        clicks = []
        task._click_client = lambda *args, **kwargs: clicks.append(args)
        with patch("src.tasks.SquareGoddessTask.monotonic", return_value=0):
            self.assertEqual(
                GODDESS_NAVIGATION_CLICKED,
                task._click_goddess_daily_navigation_until(1),
            )
        self.assertEqual([(990, 310, 1280, 720)], clicks)

    def _completion_task(self, state, prayer=None, frame=None):
        task = object.__new__(SquareGoddessTask)
        task.sleep = lambda *args: None
        frame = np.full((720, 1280, 3), 120, dtype=np.uint8) if frame is None else frame
        task.capture_frame = lambda: frame
        task._observe_goddess_navigation = lambda _frame: NavigationObservation(state, "")
        task._ocr_pattern_click_point = lambda *args, **kwargs: (prayer, "")
        return task

    def test_completion_rejects_remaining_row_prompt_or_dark_screen(self):
        cases = [("ready", None, None), ("ambiguous", None, None),
                 ("absent", (100, 100), None),
                 ("absent", None, np.full((720, 1280, 3), 5, dtype=np.uint8))]
        for state, prayer, frame in cases:
            task = self._completion_task(state, prayer, frame)
            with patch("src.tasks.SquareGoddessTask.monotonic", side_effect=iter(range(20))):
                self.assertFalse(task._wait_for_daily_navigation_to_disappear(8))

    def test_completion_after_wish_needs_no_square_bar_or_empty_task_list(self):
        # Player report 2026-10-20: wished, then the tool stood at the goddess
        # for minutes and called it unfinished; the row and prompt being gone
        # is the proof (a 每日奖励 title of other rows reads as "unknown").
        for state in ("absent", "unknown"):
            task = self._completion_task(state)
            task._match = lambda *args: self.fail("square bar is not needed")
            with patch("src.tasks.SquareGoddessTask.monotonic", side_effect=iter(range(20))):
                self.assertTrue(task._wait_for_daily_navigation_to_disappear(8))
