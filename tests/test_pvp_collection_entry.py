"""镜中之战 is entered from 主页's cartridge machine via 游戏卡珍藏集.

Clone 10-11: 一键日常 ran 常客 just before 镜中之战; 返回战场 (the recent card)
led into 格鲁菲餐厅 and PVP failed.  Leo: 「一律回主頁 進鏡中之戰」, 「從主頁進
就點右下角的卡帶 p按鍵那邊」, 「點進去就是這個畫面 然後找鏡中之戰」 (his 4K frame
of 游戏卡珍藏集: 战斗玩法 header left 157 / middle 330, MIRROR WARS centre
about 263,452 at 1080p).
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from src.tasks.PVPTask import HOME_KEYCAP_P_TEMPLATE, PVPTask
from src.utils.cartridge_collection import (
    BATTLE_ROW_PATTERNS,
    HOME_CARTRIDGE_MACHINE_POINT,
    RowHeader,
    find_row_header,
    row_card_point,
)

# 返回战场 on 主页 (1080p reference): never pressed.
RETURN_TO_FIELD_POINT = (1512, 984)
TITLE = SimpleNamespace(name="游戏卡珍藏集", x=240, y=30, width=180, height=40)


def _header(y=318, x=157, size=(1920, 1080)):
    scale_x, scale_y = size[0] / 1920, size[1] / 1080
    return SimpleNamespace(
        name="战斗玩法游戏卡带6/6",
        x=x * scale_x,
        y=y * scale_y,
        width=215 * scale_x,
        height=24 * scale_y,
    )


class RowHeaderTest(unittest.TestCase):
    def test_leos_frame_gives_the_mirror_wars_card(self):
        for size in ((1920, 1080), (3840, 2160), (2560, 1440)):
            with self.subTest(size=size):
                header = find_row_header([TITLE, _header(size=size)], BATTLE_ROW_PATTERNS, size)
                self.assertEqual((265, 450), row_card_point(header))

    def test_shelf_opened_scrolled_down_after_the_diner(self):
        # Live 4K 10-11: with GLUPY DINER as the last card the shelf opens
        # scrolled, header middle about y=170; MIRROR WARS centre about 265,290.
        header = find_row_header([TITLE, _header(y=158)], BATTLE_ROW_PATTERNS, (1920, 1080))
        self.assertEqual((265, 290), row_card_point(header))

    def test_traditional_header_reads_too(self):
        box = SimpleNamespace(name="戰鬥玩法遊戲卡帶 6/6", x=157, y=318, width=215, height=24)
        self.assertIsNotNone(find_row_header([box], BATTLE_ROW_PATTERNS, (1920, 1080)))

    def test_other_rows_are_not_the_battle_row(self):
        life = SimpleNamespace(name="生活玩法游戏卡带4/4", x=157, y=600, width=215, height=24)
        self.assertIsNone(find_row_header([TITLE, life], BATTLE_ROW_PATTERNS, (1920, 1080)))

    def test_a_card_cut_off_at_the_bottom_is_not_pressed(self):
        self.assertIsNone(row_card_point(RowHeader(left=157, middle=1000)))


class _Game:
    """主页 → (P) → 珍藏集; every OCR read returns the current screen's boxes."""

    def __init__(
        self,
        test,
        *,
        home=True,
        opens=True,
        row_after_scrolls=0,
        keycaps=True,
        card_swallows=0,
        key_opens=False,
    ):
        self.test = test
        self.key_opens = key_opens
        self.keys = []
        self.card_swallows = card_swallows
        self.keycaps = keycaps
        self.screen = "home" if home else "other"
        self.opens = opens
        self.row_after_scrolls = row_after_scrolls
        self.scrolls = []
        self.clicks = []

    def task(self):
        task = object.__new__(PVPTask)
        task.config = {"卡带选择页确认等待秒数": 2.0, "PVP 入场等待秒数": 5.0}
        task.info_set = Mock()
        task.log_info = Mock()
        task._sleep_after_recognition = lambda: None
        task._save_flow_diagnostic = Mock()
        task.sleep = lambda seconds: self.test.advance(seconds)
        task.capture_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
        task._wait_for_cartridge_home = lambda: self.screen == "home"
        task._home_machine_keycaps_steady = lambda: self.keycaps
        task._click_reference = self.click
        task.tap_key = self.tap
        task.scroll_client = lambda _point, amount, after_sleep=0.0: self.scrolls.append(amount)
        task._ocr_text = lambda _frame, name, roi=None, **_kw: (
            "游戏卡珍藏集" if self.screen == "collection" else ""
        )
        task._ocr_boxes = lambda _frame, name, roi=None, **_kw: self.boxes()
        task._wait_for_pvp_hub_after_cart = lambda timeout: self.screen == "pvp"
        task._clear_pvp_hub_notice_if_present = lambda: None
        return task

    def click(self, x, y, after_sleep=0.0):
        self.clicks.append((x, y))
        if (x, y) == HOME_CARTRIDGE_MACHINE_POINT and self.opens:
            self.screen = "collection"
        elif self.screen == "collection":
            if self.card_swallows > 0:
                self.card_swallows -= 1
            else:
                self.screen = "pvp"

    def tap(self, key, after_sleep=0.0):
        self.keys.append(key)
        if key == "P" and self.screen == "home" and self.key_opens:
            self.screen = "collection"
        return True

    def boxes(self):
        if self.screen != "collection":
            return []
        if len(self.scrolls) < self.row_after_scrolls:
            return [TITLE]
        return [TITLE, _header()]


class PvpEntryTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        clock = patch("src.tasks.PVPTask.monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def advance(self, seconds):
        self.now += seconds

    def test_home_machine_then_the_battle_rows_first_card(self):
        game = _Game(self)
        self.assertTrue(PVPTask._enter_pvp_from_home(game.task()))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT, (265, 450)], game.clicks)
        self.assertEqual([], game.keys)
        self.assertNotIn(RETURN_TO_FIELD_POINT, game.clicks)
        self.assertEqual([], game.scrolls)

    def test_off_home_presses_nothing(self):
        game = _Game(self, home=False)
        task = game.task()
        self.assertFalse(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([], game.clicks)
        task._save_flow_diagnostic.assert_called_once_with("cartridge_collection_failed")

    def test_a_swallowed_machine_press_is_tried_once_more_from_home(self):
        game = _Game(self, opens=False)
        task = game.task()
        self.assertFalse(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT] * 2, game.clicks)
        self.assertEqual(["P"], game.keys)
        self.assertIn("没看到游戏卡珍藏集", task.log_info.call_args_list[-2].args[0])

    def test_two_swallowed_machine_presses_fall_back_to_the_p_key(self):
        # Leo 10-13: 「p如果還沒按到 也可以點快捷鍵」.
        game = _Game(self, opens=False, key_opens=True)
        task = game.task()
        self.assertTrue(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT] * 2 + [(265, 450)], game.clicks)
        self.assertEqual(["P"], game.keys)
        self.assertTrue(
            any("快捷键 P" in call.args[0] for call in task.log_info.call_args_list)
        )

    def test_the_p_key_waits_for_home_again(self):
        game = _Game(self, opens=False, key_opens=True)
        task = game.task()
        checks = iter([True, True, False])
        task._wait_for_cartridge_home = lambda: next(checks)
        self.assertFalse(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([], game.keys)

    def test_a_swallowed_card_press_is_made_once_more(self):
        # Player 2026-10-13 (v0.1.30): one press on 镜中之战 left 游戏卡珍藏集 up.
        game = _Game(self, card_swallows=1)
        task = game.task()
        self.assertTrue(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT, (265, 450), (265, 450)], game.clicks)

    def test_the_card_is_pressed_twice_at_most(self):
        game = _Game(self, card_swallows=99)
        self.assertFalse(PVPTask._enter_pvp_from_home(game.task()))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT, (265, 450), (265, 450)], game.clicks)

    def test_the_shelf_is_scrolled_until_the_battle_row_shows(self):
        game = _Game(self, row_after_scrolls=3)
        self.assertTrue(PVPTask._enter_pvp_from_home(game.task()))
        self.assertEqual([3, 3, -3], game.scrolls)
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT, (265, 450)], game.clicks)

    def test_no_battle_row_presses_no_card(self):
        game = _Game(self, row_after_scrolls=99)
        task = game.task()
        self.assertFalse(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT], game.clicks)
        task._save_flow_diagnostic.assert_called_once_with("pvp_collection_row_missing")
        self.assertIn("战斗玩法游戏卡带", task.log_info.call_args.args[0])

    def test_unsteady_key_caps_still_press_the_fixed_machine_place(self):
        # Leo: 「如果識別不穩時 也可以按畫面上固定位置右下角那一大塊」
        game = _Game(self, keycaps=False)
        task = game.task()
        self.assertTrue(PVPTask._enter_pvp_from_home(task))
        self.assertEqual([HOME_CARTRIDGE_MACHINE_POINT, (265, 450)], game.clicks)
        self.assertIn("固定位置", task.log_info.call_args_list[0].args[0])


class KeycapTest(unittest.TestCase):
    """The P key cap on 主页, two frames in a row (Leo: 「認p就好」)."""

    def _task(self, reads):
        task = object.__new__(PVPTask)
        task.info_set = Mock()
        task.sleep = lambda _seconds: None
        task.capture_frame = lambda: np.zeros((1080, 1920, 3), np.uint8)
        frames = iter(reads)
        seen = []

        def match(_frame, spec):
            seen.append(spec)
            return SimpleNamespace(score=0.97 if next(frames, False) else -1.0)

        task._match = match
        task._passes = lambda result, _spec: result.score >= 0.8
        task.seen = seen
        return task

    def test_the_p_cap_twice_in_a_row(self):
        task = self._task([True, True])
        self.assertTrue(PVPTask._home_machine_keycaps_steady(task))
        self.assertEqual({HOME_KEYCAP_P_TEMPLATE.name}, {spec.name for spec in task.seen})

    def test_a_gap_starts_the_count_again(self):
        self.assertFalse(PVPTask._home_machine_keycaps_steady(self._task([True, False, True, False])))
        self.assertTrue(PVPTask._home_machine_keycaps_steady(self._task([True, False, True, True])))

    def test_the_key_cap_template_ships(self):
        from src.tasks.PVPTask import TEMPLATE_DIR

        self.assertTrue((TEMPLATE_DIR / HOME_KEYCAP_P_TEMPLATE.file_name).is_file())


if __name__ == "__main__":
    unittest.main()
