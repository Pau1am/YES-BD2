"""每日精炼: an item popup that never opened is not read as its buttons.

YES-BD2 #26 (v0.1.32, 1920x1080 windowed on 2560x1440 at 125%, 2026-10-14):
「第1行第6列的装备详情里没认出精炼按钮（按钮处读到「JR 20 22 兴 IR UR 20 B B R
22 ...」）」.  Those are the bag grid's UR tags and badge numbers: the popup read
box lies over the grid, the popup had not opened, and the usual 精炼 spot was
then pressed on the bare grid, where it is another item (row 5, column 6).

Fixture: the popup read box (x 450-1600, y 280-900) of the summary's last
frame, scaled up to 1080 (issue26_grid_no_popup_1080.jpg).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np

from src.tasks import GearTasks
from src.tasks.GearTasks import (
    CELL_PRESS_ATTEMPTS,
    DETAIL_BUTTONS_ROI,
    GRID_COLUMNS,
    GRID_ROWS,
    REFINE_NO_POPUP_PROBES,
    grid_covered,
    popup_shown,
    refine_pill_point,
)
from tests.test_refine_tall_popup import read, whole_popup

HERE = Path(__file__).resolve().parent / "fixtures" / "refine"


def player_grid():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[280:900, 450:1600] = cv2.imread(str(HERE / "issue26_grid_no_popup_1080.jpg"))
    return frame


class RealFrameTest(unittest.TestCase):
    def test_the_players_bare_grid_is_not_a_popup(self):
        boxes = read(player_grid(), DETAIL_BUTTONS_ROI)
        text = " ".join(box.name for box in boxes)
        self.assertRegex(text, r"\b(18|20|22|24)\b")  # the grid's badge numbers
        self.assertFalse(popup_shown(boxes), text)
        self.assertIsNone(refine_pill_point(player_grid()))

    def test_an_open_popup_is_seen(self):
        self.assertTrue(popup_shown(read(whole_popup(), DETAIL_BUTTONS_ROI)))

    def test_a_popup_over_the_grid_counts_as_covered(self):
        grid = player_grid()
        popup = grid.copy()
        popup[280:900, 450:1600] = whole_popup()[280:900, 450:1600]
        self.assertTrue(grid_covered(grid, popup))
        self.assertTrue(grid_covered(cv2.resize(grid, (3840, 2160)), cv2.resize(popup, (3840, 2160))))
        self.assertFalse(grid_covered(grid, grid.copy()))
        # The character art on the left moving does not count.
        moved = grid.copy()
        moved[:, :700] = 255 - moved[:, :700]
        self.assertFalse(grid_covered(grid, moved))


GRID_READ = [SimpleNamespace(name=name, x=1000, y=300, width=30, height=20)
             for name in ("JR", "20", "22", "兴", "UR")]


def _task(reads):
    from src.tasks.GearTasks import DailyRefineTask

    task = object.__new__(DailyRefineTask)
    task.logs, task.diagnostics, task.presses = [], [], []
    task.log_info = lambda message, *_a, **_k: task.logs.append(message)
    task._sleep_after_recognition = lambda: None
    task._click_reference = lambda x, y, **_k: task.presses.append((x, y))
    reads = iter(reads)
    task._wait_boxes = lambda *_a, **_k: next(reads)
    task._save_flow_diagnostic = task.diagnostics.append
    task.capture_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
    task._title_visible = lambda *_a, **_k: False
    task.sleep = lambda *_a: None
    return task


class PopupNotOpenedTest(unittest.TestCase):
    def test_the_cell_is_pressed_again_and_nothing_else(self):
        task = _task([GRID_READ] * CELL_PRESS_ATTEMPTS)
        self.assertEqual("no_popup", task._refine_cell(0, 5))
        # Only the cell itself, twice: never the usual 精炼 spot on the grid.
        self.assertEqual([(GRID_COLUMNS[5], GRID_ROWS[0])] * CELL_PRESS_ATTEMPTS, task.presses)
        self.assertIn("装备详情都没打开", task._why)
        self.assertEqual(["daily_refine_popup_not_opened"], task.diagnostics)

    def test_a_popup_that_opens_on_the_second_press_goes_on(self):
        popup = [SimpleNamespace(name="基本能力", x=500, y=500, width=80, height=20),
                 SimpleNamespace(name="精炼", x=1330, y=720, width=60, height=30)]
        task = _task([GRID_READ, popup])
        task._click_box = lambda *_a, **_k: task.presses.append("精炼")
        task._wait_for_title = lambda *_a, **_k: True
        task._refine_on_page = lambda: "refined"
        self.assertEqual("refined", task._refine_cell(0, 5))
        self.assertEqual("精炼", task.presses[-1])

    def test_no_second_press_when_something_opened_unread(self):
        # 开源前检查 2026-10-14: a popup that opened but read as nothing must
        # not get a second press (it could land on its 强化).
        task = _task([GRID_READ] * CELL_PRESS_ATTEMPTS)
        frames = iter([np.zeros((1080, 1920, 3), np.uint8)] + [np.full((1080, 1920, 3), 200, np.uint8)] * 9)
        task.capture_frame = lambda: next(frames)
        self.assertEqual("failed", task._refine_cell(3, 4))
        self.assertEqual([(GRID_COLUMNS[4], GRID_ROWS[3])], task.presses)
        self.assertIn("画面变了", task._why)
        self.assertEqual(["daily_refine_popup_unread"], task.diagnostics)

    def test_daily_refine_gives_up_after_a_few_items(self):
        task = _task([])
        task._why = ""
        task.info_set = lambda *_a, **_k: None
        task._open_equipment_bag = lambda **_k: True
        cells = [(0, column, 20) for column in range(6)]
        task._wait_for_grid_cells = lambda: cells
        task._grid_frame = None
        tried = []

        def refine_cell(row, column):
            tried.append((row, column))
            task._why = "点了装备，装备详情都没打开"
            return "no_popup"

        task._refine_cell = refine_cell
        task._restore_bag_detail_view = lambda: None
        task._leave_to_home = lambda *_a: True
        fails = []
        task._claim_fail = lambda stage: fails.append((stage, task._why)) or False
        self.enterContext(mock.patch.object(GearTasks, "purple_badges", lambda _f: set()))
        self.assertFalse(task.run_claim())
        self.assertEqual(REFINE_NO_POPUP_PROBES, len(tried))
        self.assertIn("装备详情都没打开", fails[0][1])


if __name__ == "__main__":
    unittest.main()
