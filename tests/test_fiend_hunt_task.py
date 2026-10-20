import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.tasks.FiendHuntTask import (
    CARDS_ALL,
    CARDS_SUMMONS,
    KEEP_OPTION,
    MODE_REPLAY,
    PUSH_OPTION,
    VK_F8,
    F8Key,
    FiendHuntRecordTask,
    FiendHuntTask,
    HotKey,
    chosen_save,
    key_code,
    known_character_names,
    valid_record_name,
)
from src.tasks.takeover import TakeoverMonitor


def bare_task(cls=None):
    cls = cls or FiendHuntTask
    task = object.__new__(cls)
    task.default_config = {}
    task.config_description = {}
    task.config_type = {}
    with mock.patch("src.tasks.FiendHuntTask.BaseBD2Task.__init__", return_value=None):
        cls.__init__(task)
    return task


class FiendHuntTaskConfigTest(unittest.TestCase):
    def test_options(self):
        task = bare_task()
        self.assertEqual("魔兽追踪者自动站位", task.name)
        self.assertEqual(MODE_REPLAY, task.default_config["模式"])
        self.assertEqual([MODE_REPLAY], task.config_type["模式"]["options"])  # 导入攻略图 removed
        self.assertEqual(0, task.default_config["打到第几回合"])
        self.assertFalse(task.player_plays_along)

    def test_player_chooses_whose_attack_or_skill_is_checked(self):
        # Leo 2026-09-30: all units (slower) or only the summons (faster, steadier).
        task = bare_task()
        self.assertEqual(CARDS_SUMMONS, task.default_config["技能判断"])
        self.assertEqual([CARDS_SUMMONS, CARDS_ALL], task.config_type["技能判断"]["options"])

        task.config = {"技能判断": CARDS_ALL}
        self.assertIsNone(task._card_check())
        task.config = {"技能判断": CARDS_SUMMONS}
        check = task._card_check()
        self.assertTrue(check("魔法增幅器ET001"))
        self.assertFalse(check("格兰希特"))

    def test_record_names_are_plain_folder_names(self):
        self.assertTrue(valid_record_name("chart_0bCJm6hOPk7MyGI4Ezlv"))
        self.assertTrue(valid_record_name("我的魔兽战"))
        for bad in ("", ".", "..", "a/b", "a\\b", "a:b", "a?"):
            with self.subTest(name=bad):
                self.assertFalse(valid_record_name(bad))

    def test_known_names_from_the_character_list(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "characters.json"
            path.write_text(
                json.dumps(
                    {
                        "characters": [{"name_zh_cn": "格兰希特"}, {"name_zh_cn": ""}],
                        "summons": [{"name_zh_cn": "魔法增幅器"}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual({"格兰希特", "魔法增幅器"}, known_character_names(path))
            self.assertEqual(set(), known_character_names(Path(folder) / "missing.json"))


class ModeRowsTest(unittest.TestCase):
    """魔兽追踪者 replays; recording is its own page (Leo 2026-10-01), the chart
    import is gone (Leo 2026-10-06)."""

    def test_rows_per_mode(self):
        rows = bare_task().config_type["模式"]["sub_configs"]
        self.assertEqual(
            ["存档", "技能判断", "打到第几回合", PUSH_OPTION, KEEP_OPTION], rows[MODE_REPLAY]
        )
        self.assertEqual([MODE_REPLAY], list(rows))

    def test_screenshot_fights_are_kept_as_a_save_by_default(self):
        # Leo 2026-10-01: ticked by default.
        self.assertIs(True, bare_task().default_config[KEEP_OPTION])
        self.assertNotIn(KEEP_OPTION, bare_task(FiendHuntRecordTask).default_config)

    def test_save_is_chosen_as_a_folder(self):
        the_type = bare_task().config_type["存档"]
        self.assertEqual(("file_selector", "folder"), (the_type["type"], the_type["selector_type"]))
        self.assertTrue(bare_task().config_type["存档名称"]["hidden"])

    def test_chosen_save_falls_back_to_the_old_typed_name(self):
        with tempfile.TemporaryDirectory() as root:
            save = Path(root) / "self_2k_b"
            save.mkdir()
            (save / "record.json").write_text("{}", encoding="utf-8")
            with mock.patch("src.tasks.FiendHuntTask.saves_root", return_value=Path(root)):
                self.assertEqual(save, chosen_save({"存档": str(save)}))
                self.assertEqual(save, chosen_save({"存档": "", "存档名称": "self_2k_b"}))
                self.assertIsNone(chosen_save({"存档": "", "存档名称": ""}))

    def test_chosen_folder_of_screenshots_wins_over_the_old_typed_name(self):
        # 4K PC 2026-10-01: 存档 = a folder of screenshots only, 存档名称 still
        # set from before; the old name's save was replayed instead.
        with tempfile.TemporaryDirectory() as root:
            old, shots = Path(root) / "self_1001c", Path(root) / "幹只有截圖"
            old.mkdir()
            (old / "record.json").write_text("{}", encoding="utf-8")
            shots.mkdir()
            with mock.patch("src.tasks.FiendHuntTask.saves_root", return_value=Path(root)):
                self.assertEqual(shots, chosen_save({"存档": str(shots), "存档名称": "self_1001c"}))

    def test_replay_without_a_save_says_how_to_choose_one(self):
        task = bare_task()
        task.config = {"模式": MODE_REPLAY, "存档": ""}
        task.info = {}
        task.info_set = task.info.__setitem__
        task.log_warning = mock.Mock()
        self.assertFalse(task.run())
        self.assertIn("浏览", task.info["停下原因"])

    def test_folder_with_neither_record_nor_screenshots_says_what_it_needs(self):
        with tempfile.TemporaryDirectory() as root:
            task = bare_task()
            task.config = {"模式": MODE_REPLAY, "存档": root}
            task.info = {}
            task.info_set = task.info.__setitem__
            task.log_warning = mock.Mock()
            task._turn_log = mock.Mock()
            with mock.patch("src.tasks.FiendHuntTask.GameFightScreen"):
                self.assertFalse(task.run())
        self.assertIn("没有 record.json", task.info["停下原因"])
        self.assertIn("俯视视角", task.info["停下原因"])


class KeepScreenshotFightTest(unittest.TestCase):
    """Leo 2026-10-01: only a fight played to its end is kept as a save."""

    def run_fight(self, finished, keep=True, shots=None):
        task = bare_task()
        task.config = {"模式": MODE_REPLAY, KEEP_OPTION: keep}
        task.info = {}
        task.info_set = task.info.__setitem__
        task._turn_log = mock.Mock()
        task._auto_skills = mock.Mock(return_value=True)
        task._finish = mock.Mock(return_value=finished)
        outcome = SimpleNamespace(finished=finished, turns_played=(1, 3))
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch("src.tasks.FiendHuntTask.GameFightScreen") as screen,
            mock.patch(
                "src.tasks.FiendHuntTask.find_screenshots", return_value=shots or {1: "a.png"}
            ),
            mock.patch("src.tasks.FiendHuntTask.ScreenshotTurns"),
            mock.patch("src.tasks.FiendHuntTask.load_game_names"),
            mock.patch("src.tasks.FiendHuntTask.replay_fight", return_value=outcome) as replay,
            mock.patch("src.tasks.FiendHuntTask.KeptFight") as kept,
        ):
            screen.return_value.read_turn.return_value = 1
            task.log_warning = mock.Mock()
            task._replay_screenshots(Path(root))
        self.task, self.replay = task, replay
        return kept.return_value.keep

    def test_a_finished_fight_is_kept(self):
        self.run_fight(finished=True).assert_called_once_with((1, 3))

    def test_a_stopped_fight_is_not_kept(self):
        self.run_fight(finished=False).assert_not_called()

    def test_unticked_keeps_nothing(self):
        self.run_fight(finished=True, keep=False).assert_not_called()

    def test_a_missing_turn_stops_before_the_fight(self):
        # Leo 2026-10-01: say what's missing before the fight, not halfway.
        self.run_fight(finished=True, shots={1: "a.png", 5: "c.png"})
        self.replay.assert_not_called()
        self.assertIn("缺第 3 回合", self.task.info["停下原因"])


class RecordReplayModesTest(unittest.TestCase):
    """Leo 2026-10-06: a save is played 调整服装技能 (every card) or 不调整
    (the costume order plays the characters' skills, only summons checked)."""

    def replay(self, cards, **options):
        from src.tasks.fiend_hunt.record import FightRecord, TurnState

        task = bare_task()
        task.config = {"模式": MODE_REPLAY, "技能判断": cards, **options}
        task.info = {}
        task.info_set = task.info.__setitem__
        task._turn_log = mock.Mock()
        task._auto_skills = mock.Mock(return_value=True)
        task._finish = mock.Mock(return_value=True)
        record = FightRecord({1: TurnState(1, 1, ("克蕾西亚",), {"克蕾西亚": (0, 2)})})
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch("src.tasks.FiendHuntTask.GameFightScreen"),
            mock.patch("src.tasks.FiendHuntTask.load_record", return_value=record),
            mock.patch(
                "src.tasks.FiendHuntTask.bursts_from_screenshots", side_effect=lambda r, f: r
            ),
            mock.patch("src.tasks.FiendHuntTask.replay_fight") as replay,
        ):
            (Path(root) / "record.json").write_text("{}", encoding="utf-8")
            task._replay(Path(root))
        return task, replay.call_args.kwargs

    def test_adjusting_checks_every_card_with_auto_skills_off(self):
        task, kwargs = self.replay(CARDS_ALL)
        self.assertIsNone(kwargs["check_card"])
        self.assertEqual(False, task._auto_skills.call_args.kwargs["on"])
        self.assertEqual("照排轴，全部判断", task._finish.call_args.args[-1])

    def test_not_adjusting_checks_only_summons_with_auto_skills_on(self):
        task, kwargs = self.replay(CARDS_SUMMONS)
        check = kwargs["check_card"]
        self.assertFalse(check("克蕾西亚"))
        self.assertTrue(check("魔法增幅器ET001"))
        self.assertEqual(True, task._auto_skills.call_args.kwargs["on"])
        self.assertEqual("照排轴，只看召唤物", task._finish.call_args.args[-1])

    def test_boss_pushing_is_off_unless_ticked(self):
        # Leo 2026-10-06: one boss in a year moved anyone.
        self.assertFalse(bare_task().default_config[PUSH_OPTION])
        self.assertFalse(self.replay(CARDS_SUMMONS)[1]["pushes"])
        self.assertTrue(self.replay(CARDS_SUMMONS, **{PUSH_OPTION: True})[1]["pushes"])
        self.assertNotIn(PUSH_OPTION, bare_task(FiendHuntRecordTask).default_config)


class RecordTaskTest(unittest.TestCase):
    def test_hidden_with_its_own_rows(self):
        task = bare_task(FiendHuntRecordTask)
        self.assertEqual("魔兽录制", task.name)
        self.assertFalse(task.visible)
        self.assertIsNone(task.group_name)
        self.assertEqual({"存档", "录制按键"}, {"存档", "录制按键"} & set(task.default_config))
        self.assertNotIn("模式", task.default_config)
        self.assertNotIn("技能判断", task.config_type)

    def test_record_key_is_an_f_key(self):
        task = bare_task(FiendHuntRecordTask)
        self.assertEqual("F8", task.default_config["录制按键"])
        # Leo 2026-10-20: 「无」 turns the key off.
        self.assertEqual(
            ["无", *[f"F{n}" for n in range(6, 13)]], task.config_type["录制按键"]["options"]
        )
        self.assertEqual(0x75, key_code("F6"))
        self.assertEqual(VK_F8, key_code("F8"))
        self.assertEqual(0x79, key_code("F10"))
        self.assertEqual(VK_F8, key_code("A"))
        self.assertEqual(0x7B, key_code("F12"))
        self.assertEqual(VK_F8, key_code("F13"))  # outside F6-F12

    def test_record_key_none_stops_and_says_to_pick_a_key(self):
        task = bare_task(FiendHuntRecordTask)
        task.config = {"录制按键": "无"}
        task.info = {}
        task.info_set = task.info.__setitem__
        task.log_warning = mock.Mock()
        with mock.patch("src.tasks.FiendHuntTask.record_fight") as record:
            self.assertFalse(task._record(Path("unused"), "self_1020"))
        record.assert_not_called()
        self.assertIn("选一个键", task.info["停下原因"])

    def test_without_a_save_it_points_to_the_page(self):
        task = bare_task(FiendHuntRecordTask)
        task.config = {"存档": ""}
        task.info = {}
        task.info_set = task.info.__setitem__
        task.log_warning = mock.Mock()
        self.assertFalse(task.run())
        self.assertIn("魔兽追踪者」页", task.info["停下原因"])

    def test_recording_reads_each_units_card(self):
        # 尤里光盾 T21 (4K PC 2026-10-01): a save without the cards left
        # 全部判断 to icons, and 克蕾西亚's two skills look alike.
        task = bare_task(FiendHuntRecordTask)
        task.config = {"录制按键": "F8"}
        task.info = {}
        task.info_set = task.info.__setitem__
        task._turn_log = mock.Mock()
        task.log_info = mock.Mock()
        task.sleep = mock.Mock()
        outcome = SimpleNamespace(
            record=SimpleNamespace(turns={}), finished=True, unsaved_turns=(), reason=""
        )
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch("src.tasks.FiendHuntTask.GameFightScreen") as screen,
            mock.patch("src.tasks.FiendHuntTask.HotKey"),
            mock.patch("src.tasks.FiendHuntTask.record_fight", return_value=outcome),
        ):
            task._record(Path(root), "存档")
        self.assertIs(True, screen.call_args.kwargs["read_cards"])


class HotKeyTest(unittest.TestCase):
    def test_the_chosen_key_is_polled(self):
        with mock.patch("win32api.GetAsyncKeyState", return_value=0) as get:
            HotKey(key_code("F6")).pressed()
        self.assertTrue(all(call.args == (0x75,) for call in get.call_args_list))

    def test_one_press_is_reported_once(self):
        states = iter([0, 0, 0, 0x8000, 0x8000, 0, 0x0001, 0])
        with mock.patch("win32api.GetAsyncKeyState", side_effect=lambda vk: next(states)) as get:
            key = F8Key()
            seen = [key.pressed() for _ in range(6)]
        self.assertEqual([False, True, False, False, True, False], seen)
        self.assertTrue(all(call.args == (VK_F8,) for call in get.call_args_list))


class TakeoverTest(unittest.TestCase):
    def test_recording_lets_the_player_click(self):
        task = SimpleNamespace(name="魔兽追踪者自动站位", player_plays_along=False)
        executor = SimpleNamespace(current_task=task, onetime_tasks=[task])
        monitor = TakeoverMonitor(executor)
        self.assertIs(task, monitor._running_task())
        task.player_plays_along = True
        self.assertIsNone(monitor._running_task())


if __name__ == "__main__":
    unittest.main()
