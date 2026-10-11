import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.BargainLoopTask import (
    FULL_SKILL_MESSAGE,
    BargainLoopTask,
    loop_count,
)
from src.tasks.map_trade.models import NavigationResult, ScreenState
from src.tasks.map_trade.navigator import Navigator
from src.tasks.map_trade.navigator_constants import (
    BARGAIN_CONFIRM_POINT,
    BARGAIN_POINT,
    DISCOUNT_SHOP_CLOSE_POINT,
)
from src.utils.image_utils import relative_roi_frame
from src.tasks.map_trade.navigator_trade import (
    BARGAIN_LEGEND_MESSAGE,
    BARGAIN_PAID_MESSAGE,
    BARGAIN_UPGRADE_MESSAGE,
)

FIXTURES = Path(__file__).parent / "fixtures" / "map_trade"


MENU = NavigationResult(True, ScreenState.MERCHANT_DIALOG, "已回到商人菜单")


class FakeNavigator:
    def __init__(self, enters, closes=None):
        # One result per bargain, whether from the field or from the menu.
        self.enters = list(enters)
        self.closes = list(closes or [])
        self.calls = []

    def enter_q_sp6_buy_flow(self, **kwargs):
        self.calls.append(("enter", kwargs))
        return self.enters.pop(0)

    def bargain_in_menu(self, **kwargs):
        self.calls.append(("bargain", kwargs))
        return self.enters.pop(0)

    def close_discount_shop_to_menu(self):
        self.calls.append(("close", {}))
        if self.closes:
            return self.closes.pop(0)
        return MENU


def _task():
    task = object.__new__(BargainLoopTask)
    task.info = {}
    task.problems = []
    task.warnings = []
    task.info_set = lambda key, value: task.info.__setitem__(key, value)
    task._note_phase_problem = lambda how, note: task.problems.append((how, note))
    task._save_diagnostic = lambda name: None
    task.log_warning = lambda message, **_kw: task.warnings.append(message)
    task.log_info = lambda *_a, **_kw: None
    return task


SHOP = NavigationResult(True, ScreenState.SHOP, "已通过OCR确认商店页面")


class BargainLoopTest(unittest.TestCase):
    def test_runs_the_set_number_of_rounds_and_never_buys(self):
        task = _task()
        navigator = FakeNavigator([SHOP] * 3)

        ok, message = task._loop(navigator, 3)

        self.assertTrue(ok, message)
        self.assertEqual(3, task._done)
        # Leo 2026-10-11: talk to the merchant once, then stay in his menu.
        self.assertEqual(
            ["enter", "close", "bargain", "close", "bargain", "close"],
            [name for name, _ in navigator.calls],
        )
        for name, kwargs in navigator.calls:
            if name == "enter":
                self.assertEqual(
                    {"bargain": True, "refuse_paid": True, "stop_at_legend": True}, kwargs
                )
            if name == "bargain":
                self.assertEqual({"refuse_paid": True, "stop_at_legend": True}, kwargs)
        self.assertEqual("3/3", task.info["已砍价次数"])

    def test_menu_not_read_after_closing_finds_the_merchant_again(self):
        task = _task()
        lost = NavigationResult(False, ScreenState.SANDBOX, "关闭折扣商店后没看到商人菜单（砍价）")
        navigator = FakeNavigator([SHOP] * 3, closes=[MENU, lost, MENU])

        ok, message = task._loop(navigator, 3)

        self.assertTrue(ok, message)
        self.assertEqual(3, task._done)
        self.assertEqual(
            ["enter", "close", "bargain", "close", "enter", "close"],
            [name for name, _ in navigator.calls],
        )

    def test_full_skill_stops_early_without_failing(self):
        task = _task()
        upgrade = NavigationResult(False, ScreenState.SANDBOX, BARGAIN_UPGRADE_MESSAGE)
        navigator = FakeNavigator([SHOP, upgrade, SHOP])

        ok, message = task._loop(navigator, 5)

        self.assertTrue(ok)
        self.assertEqual(FULL_SKILL_MESSAGE, message)
        self.assertEqual(1, task._done)
        self.assertEqual([], task.problems)

    def test_legend_rank_stops_without_failing(self):
        task = _task()
        legend = NavigationResult(False, ScreenState.MERCHANT_DIALOG, BARGAIN_LEGEND_MESSAGE)
        navigator = FakeNavigator([SHOP, legend, SHOP])

        ok, message = task._loop(navigator, 5)

        self.assertTrue(ok)
        self.assertEqual(BARGAIN_LEGEND_MESSAGE, message)
        self.assertEqual(1, task._done)
        self.assertEqual([], task.problems)

    def test_a_failed_round_stops_and_says_why(self):
        task = _task()
        failed = NavigationResult(False, ScreenState.SANDBOX, "未识别到砍价技能折扣说明")
        navigator = FakeNavigator([SHOP, failed])

        ok, message = task._loop(navigator, 4)

        self.assertFalse(ok)
        self.assertIn("第 2 次", message)
        self.assertIn("未识别到砍价技能折扣说明", message)
        self.assertEqual(1, task._done)
        self.assertEqual([("fail", message)], task.problems)

    def test_shop_not_closed_stops_after_counting_the_bargain(self):
        task = _task()
        stuck = NavigationResult(False, ScreenState.SHOP, "点击返回后未识别到折扣商店关闭确认")
        navigator = FakeNavigator([SHOP, SHOP], closes=[stuck])

        ok, message = task._loop(navigator, 2)

        self.assertFalse(ok)
        self.assertIn("关闭商店", message)
        self.assertEqual(1, task._done)
        self.assertEqual(["enter", "close"], [name for name, _ in navigator.calls])

    def test_started_in_the_merchant_menu_bargains_right_there(self):
        task = _task()
        task._start_spot = "menu"
        navigator = FakeNavigator([SHOP] * 2)

        ok, message = task._loop(navigator, 2)

        self.assertTrue(ok, message)
        self.assertEqual(
            ["bargain", "close", "bargain", "close"], [name for name, _ in navigator.calls]
        )

    def test_standing_at_the_merchant_skips_going_home(self):
        from unittest import mock

        from src.tasks.BaseBD2Task import BaseBD2Task

        for spot, home_calls in (("menu", 0), ("prompt", 0), ("", 1)):
            task = _task()
            task._merchant_spot = lambda spot=spot: spot
            with mock.patch.object(BaseBD2Task, "_go_home_before_run") as home:
                task._go_home_before_run()
            self.assertEqual(home_calls, home.call_count, spot)
            self.assertEqual(spot, task._start_spot)

    def test_loop_count_is_clamped(self):
        self.assertEqual(1, loop_count(0))
        self.assertEqual(1, loop_count(-5))
        self.assertEqual(200, loop_count(5000))
        self.assertEqual(200, loop_count(200))
        self.assertEqual(10, loop_count("abc"))
        self.assertEqual(7, loop_count("7"))

    def test_task_starts_from_home_and_recovers_home(self):
        self.assertTrue(BargainLoopTask.start_from_home)
        self.assertTrue(BargainLoopTask.recover_home_on_failure)
        self.assertTrue(getattr(BargainLoopTask.run, "_bd2_home_guard", False))


class BargainPaidGuardTest(unittest.TestCase):
    def _navigator(self, popup_text):
        clicks = []
        task = SimpleNamespace(
            config={},
            operate_click=lambda x, y, after_sleep=0: clicks.append((x, y)),
            sleep=lambda _s: None,
            log_warning=lambda *_a, **_k: None,
        )
        navigator = Navigator(task, SimpleNamespace(simplify=lambda text: text))
        navigator._enter_q_sp6_shop = lambda timeout, *, log_timeout: True
        navigator._confirm_merchant_menu = lambda: True
        navigator.classify = lambda: ScreenState.SANDBOX

        def tip(_tip):
            navigator.bargain_popup_text = popup_text
            return "tip"

        navigator._wait_for_bargain_tip = tip
        navigator._wait_for_bargain_shop_confirmation = lambda: True
        navigator._bargain_card_is_legend = lambda: False
        return navigator, clicks

    def test_live_popup_text_is_pressed(self):
        # Words read on Leo's 4K frame (2026-10-11): the cost is an icon + 10.
        navigator, clicks = self._navigator(
            "与无聊收集狂大叔砍价 砍价成功率100% 使用砍价技能后，可享受商店折扣价。"
            "使用时享受60%的折扣 取消 砍价 10"
        )

        result = navigator.enter_q_sp6_buy_flow(bargain=True, refuse_paid=True)

        self.assertTrue(result.success)
        self.assertEqual([BARGAIN_POINT, BARGAIN_CONFIRM_POINT], clicks)

    def test_popup_naming_diamonds_is_never_confirmed(self):
        navigator, clicks = self._navigator("使用砍价技能后可享受商店折扣价 砍价 钻石 10")

        result = navigator.enter_q_sp6_buy_flow(bargain=True, refuse_paid=True)

        self.assertFalse(result.success)
        self.assertEqual(BARGAIN_PAID_MESSAGE, result.message)
        self.assertNotIn(BARGAIN_CONFIRM_POINT, clicks)


    def test_legend_card_is_never_pressed(self):
        navigator, clicks = self._navigator("使用砍价技能后可享受商店折扣价")
        navigator._bargain_card_is_legend = lambda: True

        result = navigator.enter_q_sp6_buy_flow(
            bargain=True, refuse_paid=True, stop_at_legend=True
        )

        self.assertFalse(result.success)
        self.assertEqual(BARGAIN_LEGEND_MESSAGE, result.message)
        self.assertEqual([], clicks)


class CloseDiscountShopToMenuTest(unittest.TestCase):
    def _navigator(self, *, dialog, menu_reads):
        clicks = []
        task = SimpleNamespace(
            config={},
            operate_click=lambda x, y, after_sleep=0: clicks.append((x, y)),
            sleep=lambda _s: None,
        )
        navigator = Navigator(task, SimpleNamespace(capture=lambda: FRAME_1080))
        navigator._close_sale_dialog_before_return = lambda: True
        navigator._click_shop_close_control = lambda after_sleep=0.0: clicks.append("close")
        navigator._wait_for_ocr_keywords = lambda *_a, **_k: dialog
        reads = list(menu_reads)
        navigator._ocr_keywords_in_frame = lambda *_a, **_k: (reads.pop(0) if reads else False, "")
        navigator.classify = lambda: ScreenState.SANDBOX
        return navigator, clicks

    def test_closes_only_the_shop_and_stays_in_the_menu(self):
        navigator, clicks = self._navigator(dialog=True, menu_reads=[False, True])

        result = navigator.close_discount_shop_to_menu()

        self.assertTrue(result.success)
        self.assertEqual(ScreenState.MERCHANT_DIALOG, result.state)
        # One close press and the 是否关闭折扣商店 confirm; the menu is not closed.
        self.assertEqual(["close", DISCOUNT_SHOP_CLOSE_POINT], clicks)

    def test_menu_never_read_says_why(self):
        navigator, clicks = self._navigator(dialog=True, menu_reads=[])

        result = navigator.close_discount_shop_to_menu()

        self.assertFalse(result.success)
        self.assertIn("商人菜单", result.message)
        self.assertEqual(["close", DISCOUNT_SHOP_CLOSE_POINT], clicks)


def _box(name, x, y, width=40, height=22):
    return SimpleNamespace(name=name, x=x, y=y, width=width, height=height)


def _legend_navigator(boxes):
    navigator = Navigator(SimpleNamespace(config={}, sleep=lambda _s: None), SimpleNamespace())
    navigator.vision = SimpleNamespace(
        ocr_boxes=lambda *_a, **_k: list(boxes), simplify=lambda text: text
    )
    return navigator


FRAME_1080 = np.zeros((1080, 1920, 3), dtype=np.uint8)


class BargainLegendReadTest(unittest.TestCase):
    def test_legend_under_the_bargain_card(self):
        navigator = _legend_navigator(
            [_box("砍价", 165, 916), _box("传说", 168, 986), _box("高手", 292, 976)]
        )
        self.assertTrue(navigator._legend_under_bargain_card(FRAME_1080))

    def test_legend_under_another_card_does_not_count(self):
        navigator = _legend_navigator(
            [_box("砍价", 165, 916), _box("高手", 168, 986), _box("传说", 292, 976)]
        )
        self.assertFalse(navigator._legend_under_bargain_card(FRAME_1080))

    def test_no_bargain_card_read_means_not_legend(self):
        navigator = _legend_navigator([_box("传说", 168, 986)])
        self.assertFalse(navigator._legend_under_bargain_card(FRAME_1080))


try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class LeoLegendFrameTest(unittest.TestCase):
    """Leo's 4K merchant menu (2026-10-11), the 砍价 card at 传说."""

    @classmethod
    def setUpClass(cls):
        crop = cv2.imread(str(FIXTURES / "bargain_card_legend_leo_4k_as_1080.png"))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[670 : 670 + crop.shape[0], 100 : 100 + crop.shape[1]] = crop
        cls.frame = frame
        cls.engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False)

    def _navigator(self, frame):
        def ocr_boxes(target, _name, relative_roi):
            left, top, crop = relative_roi_frame(target, relative_roi)
            boxes = []
            for points, (text, score) in self.engine.ocr(crop)[0] or []:
                if score < 0.2:
                    continue
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                boxes.append(
                    _box(text, left + min(xs), top + min(ys), max(xs) - min(xs), max(ys) - min(ys))
                )
            return boxes

        navigator = _legend_navigator([])
        navigator.vision = SimpleNamespace(ocr_boxes=ocr_boxes, simplify=lambda text: text)
        return navigator

    def test_leos_frame_reads_legend(self):
        self.assertTrue(self._navigator(self.frame)._legend_under_bargain_card(self.frame))

    def test_leos_frame_without_the_rank_is_not_legend(self):
        frame = self.frame.copy()
        # Cover the 传说 under the 砍价 card with the card's own background.
        frame[980:1010, 150:220] = frame[1012, 185]
        self.assertFalse(self._navigator(frame)._legend_under_bargain_card(frame))


if __name__ == "__main__":
    unittest.main()
