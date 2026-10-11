"""爛装强化分解 through the bag filter (Leo 2026-10-11 「篩選 r sr 出來」,
then 「只拆 R/SR」).

The 级别 row is single-select, so R and SR are two passes; worn gear is
hidden by untick 「查看穿戴中的装备」; the player's filter is put back.
SR comes as 5★ exclusives too, so an SR candidate is opened; R is not
(Leo 「點開核對 但r不點開 5星sr不拆」).  Frames: the
filter menu on Leo's 4K game (junk-filter-1011-*), at 1080, placed back at
(420, 200).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np

from src.tasks.bag_filter import (
    CATEGORY_POINTS,
    FILTER_TITLE_ROI,
    GRADE_POINTS,
    WORN_TICK_POINT,
    BagFilterMixin,
    selected_grade,
    worn_shown,
)
from src.tasks.GearTasks import GRID_COLUMNS, GRID_ROWS
from src.utils.junk_gear import (
    GearItem,
    classify_low_grade,
    load_exclusive_owners,
    load_exclusive_stars,
    occupied_cells,
)

FIXTURES = Path(__file__).parent / "fixtures" / "junk_gear"

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None


def _menu(name: str) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / f"filter_menu_{name}_leo_4k_at_1080.jpg"))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[200 : 200 + crop.shape[0], 420 : 420 + crop.shape[1]] = crop
    return frame


def _bag(name: str) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / name))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[140 : 140 + crop.shape[0], 700 : 700 + crop.shape[1]] = crop
    return frame


class FilterMenuReadTest(unittest.TestCase):
    def test_the_grade_shown_on(self):
        self.assertIsNone(selected_grade(_menu("none")))
        self.assertEqual("R", selected_grade(_menu("r")))
        self.assertEqual("SR", selected_grade(_menu("sr")))

    def test_the_worn_tick(self):
        for name in ("none", "r", "sr"):
            self.assertTrue(worn_shown(_menu(name)), name)
        frame = _menu("none")
        x, y = WORN_TICK_POINT
        frame[y - 14 : y + 14, x - 14 : x + 14] = (40, 38, 36)  # an empty box
        self.assertFalse(worn_shown(frame))

    @unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
    def test_the_title_reads(self):
        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True)
        x, y, w, h = FILTER_TITLE_ROI
        crop = _menu("none")[y : y + h, x : x + w]
        text = " ".join(t for _b, (t, _s) in engine.ocr(crop)[0] or [])
        self.assertIn("筛选", text)


class FakeMenu(BagFilterMixin):
    """A menu that switches grades single-select and toggles the worn tick."""

    def __init__(self, grade=None, worn=True, categories=None):
        self.state = {"grade": grade, "worn": worn}
        if categories is not None:
            self.state["categories"] = list(categories)
        self.open = False
        self.clicks = []

    def sleep(self, *_a):
        pass

    def _filter_menu_open(self):
        return self.open

    def _read_filter_state(self):
        if not self.open:
            return None
        state = dict(self.state)
        if "categories" in state:
            state["categories"] = list(state["categories"])
        return state

    def _category_value(self, name):
        # Off V≈42 as on Leo's menu; on like the 级别 row.
        return 92.0 if name in self.state.get("categories", []) else 42.0

    def _click_reference(self, x, y, after_sleep=0.0):
        from src.tasks.bag_filter import (
            FILTER_BUTTON_POINT,
            FILTER_CLOSE_POINT,
            FILTER_CONFIRM_POINT,
        )

        self.clicks.append((x, y))
        if (x, y) == FILTER_BUTTON_POINT:
            self.open = not self.open
        elif (x, y) in (FILTER_CLOSE_POINT, FILTER_CONFIRM_POINT):
            self.open = False
        elif (x, y) == WORN_TICK_POINT:
            self.state["worn"] = not self.state["worn"]
        elif (x, y) in CATEGORY_POINTS.values():
            name = next(n for n, point in CATEGORY_POINTS.items() if point == (x, y))
            shown = self.state.setdefault("categories", [])
            if name in shown:
                shown.remove(name)
            else:
                shown.append(name)
        else:
            grade = next(g for g, point in GRADE_POINTS.items() if point == (x, y))
            self.state["grade"] = None if self.state["grade"] == grade else grade


class CategoryFilterTest(unittest.TestCase):
    """Leo 2026-10-11: 「你把分類 點選專用 就不會拆到其他裝了」 - the SR pass
    shows exclusives only; the player's 分类 is put back after."""

    def test_the_sr_pass_ticks_exclusive_and_the_restore_unticks_it(self):
        from src.tasks.JunkGearTask import filter_for

        menu = FakeMenu(categories=[])
        original = menu._read_bag_filter()
        self.assertTrue(menu._set_bag_filter(filter_for("R")))
        self.assertEqual([], menu.state["categories"])
        self.assertTrue(menu._set_bag_filter(filter_for("SR")))
        self.assertEqual({"grade": "SR", "worn": False, "categories": ["专用"]}, menu.state)
        self.assertTrue(menu._set_bag_filter(original))
        self.assertEqual({"grade": None, "worn": True, "categories": []}, menu.state)

    def test_a_players_own_category_is_put_back(self):
        from src.tasks.JunkGearTask import filter_for

        menu = FakeMenu(categories=["魔兽"])
        original = menu._read_bag_filter()
        self.assertTrue(menu._set_bag_filter(filter_for("SR")))
        self.assertEqual(["专用"], menu.state["categories"])
        self.assertTrue(menu._set_bag_filter(original))
        self.assertEqual(["魔兽"], menu.state["categories"])

    def test_a_filter_saved_before_categories_still_restores(self):
        menu = FakeMenu(grade="SR", worn=False, categories=["专用"])
        self.assertTrue(menu._set_bag_filter({"grade": None, "worn": True}))
        self.assertEqual(None, menu.state["grade"])

    def test_leos_real_menu_with_exclusive_lit(self):
        # The SR pass on Leo's 4K game, 2026-10-11 22:20 (a half-size frame
        # from the pick-only run): 专用 reads V≈92 lit, 魔兽/制作 V≈42.
        from src.tasks.bag_filter import category_value, selected_categories

        frame = _menu("sr_exclusive")
        self.assertEqual(["专用"], selected_categories(frame))
        self.assertEqual("SR", selected_grade(frame))
        self.assertFalse(worn_shown(frame))
        self.assertGreaterEqual(category_value(frame, "专用") - category_value(frame, "魔兽"), 20)

    def test_leos_real_menus_show_no_category(self):
        from src.tasks.bag_filter import selected_categories

        for name in ("none", "r", "sr"):
            self.assertEqual([], selected_categories(_menu(name)), name)


class StubbornCategoryMenu(FakeMenu):
    """A 分类 button that ignores the first ``missed`` taps, and whose on
    state shows at ``on_value`` (under the 68 threshold: read as off)."""

    def __init__(self, missed=0, on_value=92.0, **kwargs):
        super().__init__(**kwargs)
        self.missed = missed
        self.on_value = on_value
        self.category_taps = 0

    def _read_filter_state(self):
        state = super()._read_filter_state()
        if state is not None and self.on_value < 68:
            state["categories"] = []  # on cannot be read as on
        return state

    def _category_value(self, name):
        return self.on_value if name in self.state.get("categories", []) else 42.0

    def _click_reference(self, x, y, after_sleep=0.0):
        if (x, y) in CATEGORY_POINTS.values():
            self.category_taps += 1
            if self.missed:
                self.missed -= 1
                self.clicks.append((x, y))
                return
        super()._click_reference(x, y, after_sleep)


class CategoryTickFallbackTest(unittest.TestCase):
    """Leo 2026-10-11 「你不會又點一次沒點到 或者 沒辨識到 又整個失敗吧」:
    专用 is tapped at most twice; not lit, the SR pass goes on with 级别 SR
    alone (each SR still opened for the 3★/4★ check), and the restore only
    unticks what the tool ticked."""

    def _task_menu(self, menu):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.__dict__.update(menu.__dict__)
        task.log_info = lambda *a, **k: None
        task.info_set = lambda *a: None
        for name in ("sleep", "_filter_menu_open", "_read_filter_state",
                     "_category_value", "_click_reference"):
            setattr(task, name, getattr(menu, name))
        return task

    def test_a_missed_tap_is_tapped_once_more(self):
        from src.tasks.JunkGearTask import filter_for

        menu = StubbornCategoryMenu(missed=1, categories=[])
        self.assertTrue(menu._set_bag_filter(filter_for("SR")))
        self.assertEqual(["专用"], menu.state["categories"])
        self.assertEqual(2, menu.category_taps)

    def test_on_under_the_threshold_counts_by_the_visible_change(self):
        from src.tasks.JunkGearTask import filter_for

        menu = StubbornCategoryMenu(on_value=66.0, categories=[])
        original = menu._read_bag_filter()
        self.assertTrue(menu._set_bag_filter(filter_for("SR")))
        self.assertEqual(["专用"], menu.state["categories"])
        self.assertTrue(menu._set_bag_filter(original))
        self.assertEqual([], menu.state["categories"])
        self.assertEqual(2, menu.category_taps)

    def test_never_lit_goes_on_with_the_grade_alone(self):
        menu = StubbornCategoryMenu(missed=99, categories=[])
        task = self._task_menu(menu)
        original = task._read_bag_filter()
        self.assertTrue(task._set_grade_filter("SR"))
        self.assertEqual({"grade": "SR", "worn": False, "categories": []}, menu.state)
        self.assertEqual(2, menu.category_taps)  # two taps, then no more
        self.assertTrue(task._set_bag_filter(original))
        self.assertEqual({"grade": None, "worn": True, "categories": []}, menu.state)
        self.assertEqual(2, menu.category_taps)  # nothing ticked: nothing unticked

    def test_the_test_hook_never_taps_a_category(self):
        menu = StubbornCategoryMenu(categories=[])
        task = self._task_menu(menu)
        task.category_tick_disabled = True
        self.assertTrue(task._set_grade_filter("SR"))
        self.assertEqual("SR", menu.state["grade"])
        self.assertEqual(0, menu.category_taps)

    def test_a_players_own_exclusive_tick_is_left_alone(self):
        menu = StubbornCategoryMenu(missed=99, categories=["专用"])
        task = self._task_menu(menu)
        original = task._read_bag_filter()
        task.category_tick_disabled = True
        self.assertTrue(task._set_grade_filter("SR"))
        self.assertTrue(task._set_bag_filter(original))
        self.assertEqual(["专用"], menu.state["categories"])


class FilterSetTest(unittest.TestCase):
    def test_r_then_sr_then_back(self):
        menu = FakeMenu()
        original = menu._read_bag_filter()
        self.assertEqual({"grade": None, "worn": True}, original)
        self.assertTrue(menu._set_bag_filter({"grade": "R", "worn": False}))
        self.assertEqual({"grade": "R", "worn": False}, menu.state)
        self.assertTrue(menu._set_bag_filter({"grade": "SR", "worn": False}))
        self.assertEqual({"grade": "SR", "worn": False}, menu.state)
        self.assertTrue(menu._set_bag_filter(original))
        self.assertEqual(original, menu.state)
        self.assertFalse(menu.open)

    def test_a_players_own_grade_is_put_back(self):
        menu = FakeMenu(grade="UR", worn=False)
        original = menu._read_bag_filter()
        menu._set_bag_filter({"grade": "R", "worn": False})
        menu._set_bag_filter(original)
        self.assertEqual({"grade": "UR", "worn": False}, menu.state)

    def test_an_unread_menu_changes_nothing(self):
        menu = FakeMenu()
        menu._read_filter_state = lambda: None
        self.assertFalse(menu._set_bag_filter({"grade": "R", "worn": False}))
        self.assertEqual({"grade": None, "worn": True}, menu.state)

    def test_the_saved_filter_round_trip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "junk_gear_filter.json"
            with mock.patch("src.tasks.bag_filter._filter_state_file", return_value=path):
                self.assertIsNone(BagFilterMixin._saved_filter())
                BagFilterMixin._save_filter({"grade": None, "worn": True})
                self.assertEqual({"grade": None, "worn": True}, BagFilterMixin._saved_filter())
                BagFilterMixin._clear_saved_filter()
                self.assertIsNone(BagFilterMixin._saved_filter())


class OccupiedCellsTest(unittest.TestCase):
    def test_real_filtered_bags(self):
        # Leo's 4K bag 2026-10-11: SR filter 11 items, R filter 4.
        sr = _bag("bag_sr_leo_4k_at_1080.jpg")
        r = _bag("bag_r_leo_4k_at_1080.jpg")
        self.assertEqual(10, len(occupied_cells(sr, GRID_COLUMNS, GRID_ROWS, 10)))
        self.assertEqual(11, len(occupied_cells(sr, GRID_COLUMNS, GRID_ROWS, 40)))
        self.assertEqual(4, len(occupied_cells(r, GRID_COLUMNS, GRID_ROWS, 10)))


class LowGradeRuleTest(unittest.TestCase):
    """Real items from the 4K observe run (junk-observe-1011-*).  Only SR is
    opened in the task; the rule itself also holds for R."""

    def setUp(self):
        self.stars, self.owners = load_exclusive_stars(), load_exclusive_owners()

    def _junk(self, name, grade, owner=None, text=""):
        item = GearItem(name, grade, False, False, False, owner_line=owner)
        return classify_low_grade(item, grade, self.stars, self.owners, text)[0]

    def test_plain_r_is_junk(self):
        self.assertTrue(self._junk("某某之剑", "R", text="武器 设置自定义标记"))

    def test_a_plain_sr_is_kept(self):
        # Leo 2026-10-11: his 顶级英雄盔甲 SR says no 3★ 专用装备 in the popup.
        self.assertFalse(self._junk("顶级英雄盔甲", "SR", text="盔甲 设置自定义标记"))

    def test_3_and_4_star_exclusives_with_their_owner_are_junk(self):
        self.assertTrue(self._junk("猎人之弓", "SR", "莉兹内", "专用装备"))
        self.assertTrue(self._junk("哭泣魔王", "R", "⭐克莱", "专用装备"))
        self.assertTrue(self._junk("首席勋章", "R", "艾玛", "专用装备"))

    def test_5_star_exclusives_in_sr_are_kept(self):
        # 翼角头盔 SR (格兰希特) and 名剑飞燕 SR (斑鸠) sit in Leo's bag.
        self.assertFalse(self._junk("翼角头盔", "SR", "格兰希特", "专用装备"))
        self.assertFalse(self._junk("名剑飞燕", "SR", "斑鸠", "专用装备"))

    def test_5_star_sr_exclusives_go_when_the_player_says_so(self):
        # Leo 2026-10-11 「讓玩家選擇要不要分解5星角色的SR」: the owner must
        # still be read on the popup.
        def junk(name, owner):
            item = GearItem(name, "SR", False, False, False, owner_line=owner)
            return classify_low_grade(
                item, "SR", self.stars, self.owners, "专用装备", five_star_sr=True
            )[0]

        self.assertTrue(junk("翼角头盔", "格兰希特"))
        self.assertTrue(junk("名剑飞燕", "斑鸠"))
        self.assertFalse(junk("翼角头盔", None))
        self.assertFalse(junk("翼角头盔", "斑鸠"))

    def test_any_doubt_keeps_it(self):
        self.assertFalse(self._junk("猎人之弓", "SR", None, "专用装备"))  # owner unread
        self.assertFalse(self._junk("猎人之弓", "SR", "格兰希特", "专用装备"))
        self.assertFalse(self._junk("某某之剑", "SR", "某人", "专用装备"))  # not on the table
        item = GearItem("顶级英雄盔甲", "UR", False, False, False)  # popup grade differs
        self.assertFalse(classify_low_grade(item, "SR", self.stars, self.owners)[0])
        item = GearItem("顶级英雄盔甲", "SR", True, False, False)
        self.assertFalse(classify_low_grade(item, "SR", self.stars, self.owners)[0])


class RunFlowTest(unittest.TestCase):
    def _task(self, shown):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.config = {"最多处理件数": 5}
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        task.log_warning = lambda *a, **k: None
        task.sleep = lambda *a: None
        task._still_grid_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
        task.saved = []
        task._save_filter = task.saved.append
        task.sets = []
        task._set_bag_filter = lambda wanted: task.sets.append(dict(wanted)) or True
        task.judged = []
        task._classify_cells = lambda cells, _stars, _frame, grade="R": task.judged.append(
            (grade, list(cells))
        ) or list(cells)
        task._enhance_and_dismantle = lambda cells, _frame: True
        self.shown = iter(shown)
        patcher = mock.patch(
            "src.tasks.JunkGearTask.occupied_cells",
            side_effect=lambda frame, columns, rows, cap: next(self.shown)[:cap],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return task

    def test_five_items_in_all_r_first(self):
        cells = [(0, c) for c in range(8)]
        task = self._task([cells[:3], cells])
        ok, _stage, dismantled = task._dismantle_filtered({}, {"grade": None}, False)
        self.assertTrue(ok and dismantled)
        self.assertEqual(
            [
                {"grade": "R", "worn": False, "categories": []},
                {"grade": "SR", "worn": False, "categories": ["专用"]},
            ],
            task.sets,
        )
        self.assertEqual([("R", cells[:3]), ("SR", cells[:2])], task.judged)
        self.assertEqual([{"grade": None}], task.saved)

    def test_enough_r_skips_sr(self):
        cells = [(0, c) for c in range(8)]
        task = self._task([cells])
        task._dismantle_filtered({}, {"grade": None}, False)
        self.assertEqual([("R", cells[:5])], task.judged)
        self.assertEqual([{"grade": "R", "worn": False, "categories": []}], task.sets)

    def test_a_filter_that_does_not_switch_dismantles_nothing(self):
        task = self._task([])
        task._set_bag_filter = lambda wanted: False
        ok, stage, dismantled = task._dismantle_filtered({}, {"grade": None}, False)
        self.assertEqual((False, "筛选 R", False), (ok, stage, dismantled))
        self.assertEqual([], task.judged)

    def test_sr_not_switching_after_r_keeps_the_r_done(self):
        # Leo 「又整個失敗吧」: what was dismantled stays done; no failure.
        cells = [(0, c) for c in range(8)]
        task = self._task([cells[:2]])
        task._set_grade_filter = lambda grade: task.sets.append(grade) or grade == "R"
        ok, stage, dismantled = task._dismantle_filtered({}, {"grade": None}, False)
        self.assertEqual((True, "", True), (ok, stage, dismantled))
        self.assertEqual(["R", "SR"], task.sets)

    def test_a_cancelled_selection_goes_on(self):
        cells = [(0, c) for c in range(8)]
        task = self._task([cells[:2], cells[:2]])
        task._enhance_and_dismantle = lambda cells, _frame: None
        ok, _stage, dismantled = task._dismantle_filtered({}, {"grade": None}, False)
        self.assertEqual((True, False), (ok, dismantled))
        self.assertEqual(["R", "SR"], [grade for grade, _cells in task.judged])

    def test_run_claim_puts_the_players_filter_back(self):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.config = {}
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        task.log_warning = lambda *a, **k: None
        task._colours_distorted = lambda: False
        task._open_equipment_bag = lambda: True
        task._saved_sort = lambda: None
        task._clear_saved_sort = lambda: None
        task._switch_to_newest_first = lambda: "按获得时间从晚到早排序"
        task._restore_sort = lambda _label: True
        task._restore_bag_detail_view = lambda: None
        task._clear_pending = lambda: None
        original = {"grade": "UR", "worn": True}
        saved = SimpleNamespace(value=None)
        task._saved_filter = lambda: saved.value
        task._save_filter = lambda state: setattr(saved, "value", state)
        task._clear_saved_filter = lambda: setattr(saved, "value", None)
        task._read_bag_filter = lambda: dict(original)
        task.sets = []
        task._set_bag_filter = lambda wanted: task.sets.append(dict(wanted)) or True
        task._still_grid_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
        task._dismantle_crafted_n = lambda: True
        task._leave_to_home = lambda *a: True
        with (
            mock.patch("src.tasks.JunkGearTask.load_exclusive_stars", return_value={}),
            mock.patch("src.tasks.JunkGearTask.occupied_cells", return_value=[]),
            mock.patch("src.tasks.JunkGearTask.SLOW_PC_GRACE_SECONDS", 0),
        ):
            self.assertTrue(task.run_claim())
        self.assertEqual(original, task.sets[-1])
        self.assertIsNone(saved.value)


class FallbackTest(unittest.TestCase):
    """Leo 2026-10-11 「識別不到的話也要有替代方案」: without a readable or
    switchable filter, the newest-first grid labels decide."""

    def _task(self, original):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.config = {"最多处理件数": 5}
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        task.log_warning = lambda *a, **k: None
        task.sleep = lambda *a: None
        task._colours_distorted = lambda: False
        task._open_equipment_bag = lambda: True
        task._saved_sort = lambda: None
        task._clear_saved_sort = lambda: None
        task._switch_to_newest_first = lambda: "按获得时间从晚到早排序"
        task._restore_sort = lambda _label: True
        task._restore_bag_detail_view = lambda: None
        task._clear_pending = lambda: None
        task._saved_filter = lambda: None
        task._save_filter = lambda _state: None
        task._clear_saved_filter = lambda: None
        task._filter_menu_open = lambda: False
        task._read_bag_filter = lambda: original
        task.sets = []
        task._set_bag_filter = lambda wanted: task.sets.append(dict(wanted)) or False
        task._still_grid_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
        task.judged = []
        task._classify_cells = lambda cells, _stars, _frame, grade="R": task.judged.append(
            (grade, list(cells))
        ) or []
        task._dismantle_crafted_n = lambda: True
        task._leave_to_home = lambda *a: True
        task._claim_fail = lambda _stage: False
        return task

    def _run(self, task):
        cells = [(0, c) for c in range(8)]
        with (
            mock.patch("src.tasks.JunkGearTask.load_exclusive_stars", return_value={}),
            mock.patch(
                "src.tasks.JunkGearTask.occupied_cells",
                side_effect=lambda frame, columns, rows, cap: cells[:cap],
            ),
        ):
            return task.run_claim()

    def test_an_unread_filter_uses_the_grid_labels(self):
        task = self._task(None)
        self.assertTrue(self._run(task))
        self.assertEqual([(None, [(0, c) for c in range(5)])], task.judged)
        self.assertEqual([], task.sets)

    def test_a_filter_that_does_not_switch_is_put_back_first(self):
        task = self._task({"grade": None, "worn": True})
        results = iter([False, True])  # R does not switch; the restore works
        task._set_bag_filter = lambda wanted: task.sets.append(dict(wanted)) or next(results)
        self.assertTrue(self._run(task))
        self.assertEqual(
            [{"grade": "R", "worn": False, "categories": []}, {"grade": None, "worn": True}],
            task.sets,
        )
        self.assertEqual([(None, [(0, c) for c in range(5)])], task.judged)

    def test_without_a_filter_each_label_decides(self):
        from src.tasks.JunkGearTask import JunkGearTask

        task = object.__new__(JunkGearTask)
        task.config = {}
        task.info_set = lambda *a: None
        task.log_info = lambda *a, **k: None
        task.log_warning = lambda *a, **k: None
        task._badged_cells = lambda: set()
        task._older_cell_kept = lambda *_a: ""
        labels = {(0, 0): "R", (0, 1): "UR", (0, 2): None}
        task._grid_rarity = lambda _frame, cell: labels[cell]
        task._wait_detail = lambda *a, **k: self.fail("detail opened")
        with mock.patch("src.tasks.JunkGearTask.grid_cell_locked", return_value=False):
            junk = task._classify_cells(
                [(0, 0), (0, 1), (0, 2)], {}, np.zeros((1080, 1920, 3), np.uint8), grade=None
            )
        self.assertEqual([(0, 0)], junk)


if __name__ == "__main__":
    unittest.main()
