"""活动每日战斗: the hub's mode button is found when OCR cuts it in two.

A player's 2560x1440 fullscreen run (v0.1.21, 2026-10-11) stopped with
「挑战战斗失败：活动页里没找到「挑战战斗」」 right after the hub check, which reads
the row's boxes as one text, had seen both modes.  The button lookup wanted the
whole word in one box and looked at one frame only.
"""

import unittest
from types import SimpleNamespace

from src.tasks.EventBattleTask import HUB_KEYWORDS, EventBattleTask
from src.utils.ocr_utils import keyword_match_count


def box(name, x, y=950, width=None, height=30):
    return SimpleNamespace(name=name, x=x, y=y, width=width or 30 * len(name), height=height)


# The hub row with 挑战战斗 cut in two by OCR; 普通战斗 read whole.
CUT_ROW = [box("普通战斗", 500), box("挑战", 1100), box("战斗", 1164)]


def make_task(frames):
    task = object.__new__(EventBattleTask)
    task.config = {}
    task.info = {}
    task.info_set = lambda key, value: task.info.__setitem__(key, value)
    task.log_info = lambda *args, **kwargs: None
    task.sleep = lambda *_args: None
    task._sleep_after_recognition = lambda: None
    task._enter_hub = lambda: "ok"
    frames = list(frames)
    task.reads = 0

    def capture():
        task.reads += 1
        return frames.pop(0) if len(frames) > 1 else frames[0]

    task.capture_frame = capture
    task._roi_boxes = lambda frame, roi, name: frame
    task.clicks = []
    task._click_box = lambda button, after_sleep=0: task.clicks.append(button)
    task._wait_for_stage_page = lambda mode, timeout=0, quiet=False: bool(task.clicks)
    task._wait_for_hub = lambda timeout=0: True
    # The swords and the usual spot have their own tests (test_event_hub_swords).
    task._usual_mode_button = lambda frame, mode: None
    return task


class ModeButtonTest(unittest.TestCase):
    def test_a_button_cut_in_two_is_still_pressed_in_its_middle(self):
        # The player's case as far as the code shows it: the hub passed, the
        # one-box lookup failed.
        self.assertEqual(
            2, keyword_match_count(EventBattleTask._boxes_text(CUT_ROW), HUB_KEYWORDS)
        )
        task = make_task([CUT_ROW])
        self.assertEqual("ok", task._open_mode("挑战战斗"))
        (pressed,) = task.clicks
        self.assertEqual("挑战战斗", pressed.name)
        self.assertEqual((1100, 1224), (pressed.x, pressed.x + pressed.width))

    def test_a_whole_button_is_pressed_as_before(self):
        task = make_task([CUT_ROW])
        self.assertEqual("ok", task._open_mode("普通战斗"))
        self.assertEqual("普通战斗", task.clicks[0].name)

    def test_a_frame_without_the_button_is_looked_at_again(self):
        task = make_task([[box("普通战斗", 500)], [box("普通战斗", 500), box("挑战战斗", 1100)]])
        self.assertEqual("ok", task._open_mode("挑战战斗"))
        self.assertEqual(2, task.reads)

    def test_still_missing_says_what_was_read(self):
        task = make_task([[box("普通战斗", 500)]])
        self.assertEqual("failed", task._open_mode("挑战战斗"))
        self.assertEqual([], task.clicks)
        self.assertIn("活动页里没找到「挑战战斗」", task._why)
        self.assertIn("普通战斗", task._why)

    def test_pieces_far_apart_or_on_other_lines_are_not_joined(self):
        far = [box("挑战", 600), box("战斗", 1100)]
        self.assertIsNone(EventBattleTask._joined_box(far, "挑战战斗"))
        other_line = [box("挑战", 1100, y=920), box("战斗", 1164, y=990)]
        self.assertIsNone(EventBattleTask._joined_box(other_line, "挑战战斗"))

    def test_the_word_must_run_across_the_pieces(self):
        # A box that already reads the word whole is not joined to its neighbour.
        row = [box("挑战战斗", 1100), box("解锁", 1224)]
        self.assertIsNone(EventBattleTask._joined_box(row, "挑战战斗"))
        three = [box("挑", 1100), box("战战", 1134), box("斗", 1198)]
        self.assertEqual("挑战战斗", EventBattleTask._joined_box(three, "挑战战斗").name)


if __name__ == "__main__":
    unittest.main()
