"""活动游戏卡 in 每周跑图 (Leo 2026-10-09): cards, maps, cover art, routes."""

import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from src.tasks.map_trade import event_card_art
from src.tasks.map_trade.collector import chapter_filter
from src.tasks.map_trade.models import (
    CARD_BY_ID,
    COLLECTABLE_CARDS,
    EVENT_CARDS,
    EVENT_WALK_EDGES,
    NavigationResult,
    ScreenState,
)
from src.tasks.map_trade.navigator import Navigator
from src.ui.shell.map_page import range_text

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "quick_switch"
# Slot order on Leo's bar (live 4K 2026-10-09): card number -> slot 0..4.
SLOTS = {1: 0, 2: 1, 3: 2, 5: 3, 7: 4}


def _frame(name: str, height: int | None = None) -> np.ndarray:
    frame = cv2.imread(str(FIXTURES / name))
    if height is not None and height != frame.shape[0]:
        width = round(frame.shape[1] * height / frame.shape[0])
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    return frame


class EventCardModelTest(unittest.TestCase):
    def test_the_five_permanent_cards_run_after_the_others(self):
        ids = [card.card_id for card in EVENT_CARDS]
        self.assertEqual(["Q_ep1", "Q_ep2", "Q_ep3", "Q_ep5", "Q_ep7"], ids)
        self.assertEqual(ids, [card.card_id for card in COLLECTABLE_CARDS[-5:]])
        for card in EVENT_CARDS:
            self.assertEqual("event", card.category)
            self.assertIs(CARD_BY_ID[card.card_id], card)

    def test_labels_and_range_tokens(self):
        card = CARD_BY_ID["Q_ep2"]
        self.assertEqual("活动卡2", card.label)
        self.assertEqual("E2", card.filter_key)
        self.assertEqual({"E1", "E2", "E3"}, chapter_filter("E1-E3"))
        self.assertEqual({5, "R2", "E7"}, chapter_filter("5,R2,E7"))

    def test_range_text_names_event_cards(self):
        story, character, event = [1, 2], [1], [1, 2, 3, 5, 7]
        self.assertEqual(
            "全部", range_text(story, character, story, character, event, event)
        )
        text = range_text(story, character, story, character, [2, 3, 7], event)
        self.assertEqual("1-2,R1,E2-E3,E7", text)
        self.assertEqual({1, 2, "R1", "E2", "E3", "E7"}, chapter_filter(text))

    def test_area_map_headers_name_one_map(self):
        # Headers as OCR read them on the live frames.
        cases = {
            "Q_ep1": {"安全泳池派对场普通": "main_area", "战斗Ⅰ派对会场角落出现水属性怪物": "battle_area_1"},
            "Q_ep2": {
                "安全雷瓦汀据点普通": "main_area",
                "战斗Ⅰ恶梦之城1出现暗属性怪物": "battle_area_1",
                "战斗Ⅱ恶梦之城2出现暗属性怪物": "battle_area_2",
            },
            "Q_ep3": {"安全海岸沙滩普通": "main_area", "战斗Ⅰ海岸椰林出现暗属性怪物": "battle_area_1"},
            "Q_ep5": {"安全底层居住区普通": "main_area", "战斗Ⅰ第4区出现暗属性怪物": "battle_area_1"},
            "Q_ep7": {
                "安全水上乐园室内泳池普通": "main_area",
                "战斗｜泼水音乐节活动现场出现水属性怪物": "battle_area_1",
            },
        }
        for card_id, headers in cases.items():
            card = CARD_BY_ID[card_id]
            for header, key in headers.items():
                with self.subTest(card=card_id, header=header):
                    self.assertEqual((key,), Navigator._target_keys_in_text(card, header))
        # Splash Queen's other safe page is not its town.
        self.assertEqual(
            (), Navigator._target_keys_in_text(CARD_BY_ID["Q_ep7"], "安全水上乐园物资仓库普通")
        )

    def test_walked_cards_have_both_directions(self):
        for card_id in ("Q_ep1", "Q_ep3", "Q_ep5", "Q_ep7"):
            self.assertIn((card_id, "main_area", "battle_area_1"), EVENT_WALK_EDGES)
            self.assertIn((card_id, "battle_area_1", "main_area"), EVENT_WALK_EDGES)
        self.assertFalse(any(edge[0] == "Q_ep2" for edge in EVENT_WALK_EDGES))


class EventCardArtTest(unittest.TestCase):
    def test_every_card_is_found_in_its_slot(self):
        for name in ("event_bar_card1_playing_fhd.png", "event_bar_card2_playing_fhd.png"):
            for height in (1080, 1440, 2160):
                frame = _frame(name, height)
                for number, slot in SLOTS.items():
                    with self.subTest(fixture=name, height=height, card=number):
                        check = event_card_art.find_card(frame, number)
                        self.assertTrue(check.ok, check.reason)
                        self.assertAlmostEqual(80 + 180 * slot, check.target.card_left, delta=6)

    def test_the_played_card_is_still_found(self):
        # Dimmed with 游戏中 over it: 0.87-0.88, other cards <= 0.45.
        check = event_card_art.find_card(_frame("event_bar_card2_playing_fhd.png"), 2)
        self.assertTrue(check.ok, check.reason)
        self.assertGreater(check.target.score - check.other.score, 0.3)

    def test_a_bar_without_the_card_finds_nothing(self):
        frame = _frame("event_bar_card1_playing_fhd.png").copy()
        left = 80 + 180 * SLOTS[5]
        frame[900:1050, left - 10 : left + 170] = 30
        self.assertFalse(event_card_art.find_card(frame, 5).ok)


class EventWalkTest(unittest.TestCase):
    def _navigator(self, open_headers, headers_after_clicks, picker_rows=()):
        clicks = []
        open_headers = iter(open_headers)
        after = iter(headers_after_clicks)
        rows = [
            SimpleNamespace(name=text, x=x - 40, y=y - 15, width=80, height=30)
            for text, (x, y) in picker_rows
        ]
        vision = SimpleNamespace(
            capture=lambda: np.zeros((1080, 1920, 3), np.uint8),
            click_client=lambda point, shape, after_sleep=0: clicks.append(point),
            ocr_boxes=lambda *a, **k: rows,
            simplify=lambda text: text,
        )
        task = SimpleNamespace(operate_click=lambda *a, **k: None, sleep=lambda *a: None)
        navigator = Navigator(task, vision)
        navigator.ensure_small_minimap = lambda: True
        navigator._open_field_map = lambda: next(open_headers)
        navigator._field_map_header = lambda: next(after)
        navigator._close_field_map = lambda: None
        navigator._wait_for_field_hud = lambda **k: NavigationResult(True, ScreenState.SANDBOX)
        navigator._wait_resuming_walk = lambda timeout: None
        navigator._loading_timeout = lambda: 1.0
        return navigator, clicks

    def test_the_picker_row_starts_the_walk(self):
        # Beachside Angels from 艾琳: the battle ring opens 战斗区 / 战斗区.
        card = CARD_BY_ID["Q_ep3"]
        navigator, clicks = self._navigator(
            ["安全海岸沙滩普通", "战斗Ⅰ海岸椰林"],
            ["安全海岸沙滩普通", ""],
            picker_rows=(("战斗区", (584, 608)), ("战斗区", (584, 670))),
        )
        result = navigator._walk_to_collection_map(card, card.targets[0], card.targets[1])
        self.assertTrue(result.success, result.message)
        self.assertEqual([(733, 689), (584, 608)], clicks)

    def test_an_exit_that_does_not_react_retries_from_erin(self):
        card = CARD_BY_ID["Q_ep1"]
        travelled = []
        navigator, clicks = self._navigator(
            ["安全泳池派对场", "安全泳池派对场", "战斗Ⅰ派对会场角落"],
            ["安全泳池派对场", ""],
        )
        navigator._travel_via_nav_menu = lambda *entries: travelled.append(entries) or entries[0]
        result = navigator._walk_to_collection_map(card, card.targets[0], card.targets[1])
        self.assertTrue(result.success, result.message)
        self.assertEqual([("艾琳",)], travelled)
        self.assertEqual([(682, 392), (682, 392)], clicks)

    def _ep7_with_question(self, confirmed):
        # Player 2026-10-17 (v0.1.44): the exit click opens the 自动移动
        # question; the header stays readable above it.
        card = CARD_BY_ID["Q_ep7"]
        here = card.targets[0].title
        navigator, clicks = self._navigator([here, "战斗Ⅰ" + card.targets[1].title], [here, here, ""])
        asked = iter([True, False])
        navigator._walk_text = lambda frame: "是否自动移动前往所选目的地" if next(asked, False) else ""
        pressed, cancelled = [], []
        navigator._click_sandbox_navigation_destination_confirmation = (
            lambda frame: pressed.append(1) or confirmed
        )
        navigator._cancel_auto_move_dialog = lambda frame=None: cancelled.append(1) or True
        navigator._travel_via_nav_menu = lambda *entries: None
        return navigator, card, clicks, pressed, cancelled

    def test_the_auto_move_question_after_an_exit_click_is_confirmed(self):
        navigator, card, clicks, pressed, cancelled = self._ep7_with_question(True)
        result = navigator._walk_to_collection_map(card, card.targets[0], card.targets[1])
        self.assertTrue(result.success, result.message)
        self.assertEqual([(748, 585)], clicks)
        self.assertEqual([1], pressed)
        self.assertEqual([], cancelled)

    def test_an_unconfirmed_question_is_cancelled_before_the_next_spot(self):
        navigator, card, clicks, pressed, cancelled = self._ep7_with_question(False)
        navigator._walk_to_collection_map(card, card.targets[0], card.targets[1])
        self.assertEqual([1], cancelled)
        self.assertEqual([(748, 585), (748, 565)], clicks)

    def test_back_to_the_town_goes_to_erin_first(self):
        card = CARD_BY_ID["Q_ep5"]
        navigator, clicks = self._navigator([], [])
        navigator._travel_via_nav_menu = lambda *entries: entries[0]
        navigator.current_collection_target = lambda _card: "main_area"
        result = navigator.advance_collection_map("Q_ep5", card.targets[1], card.targets[0])
        self.assertTrue(result.success, result.message)
        self.assertEqual([], clicks)


class BattleResultLeaveTest(unittest.TestCase):
    def test_leave_is_pressed_on_a_result_screen(self):
        clicks = []
        vision = SimpleNamespace(
            ocr_boxes=lambda *a, **k: [
                SimpleNamespace(name="离开", x=1690, y=995, width=60, height=30)
            ],
            simplify=lambda text: text,
            click_client=lambda point, shape, after_sleep=0: clicks.append(point),
        )
        navigator = Navigator(SimpleNamespace(sleep=lambda *a: None), vision)
        self.assertTrue(navigator._leave_battle_result(np.zeros((1080, 1920, 3), np.uint8)))
        self.assertEqual([(1720, 1010)], clicks)


if __name__ == "__main__":
    unittest.main()
