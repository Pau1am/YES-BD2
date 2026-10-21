import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.ui.shell import data
from src.ui.shell.home import BoardTile


def _child(included=True):
    return data.Child("领取邮件", None, "领取邮件", "邮件", "mail", "claim", included)


class BoardTileCheckTest(unittest.TestCase):
    """Leo 2026-10-08: the check on a home tile decides whether 一键日常 runs it;
    the rest of the tile still opens the item's settings."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, included=True):
        self.opened, self.included = [], []
        tile = BoardTile(
            _child(included),
            on_click=lambda: self.opened.append(True),
            on_include=lambda key, on: self.included.append((key, on)),
        )
        tile.resize(180, 120)
        tile.show()
        self.addCleanup(tile.hide)
        QApplication.processEvents()
        return tile

    def test_check_follows_the_batch_setting(self):
        self.assertTrue(self.make(True).include.isChecked())
        self.assertFalse(self.make(False).include.isChecked())

    def test_clicking_the_check_switches_the_item_without_opening_it(self):
        tile = self.make(True)
        QTest.mouseClick(tile.include, Qt.LeftButton)
        self.assertEqual(self.included, [("领取邮件", False)])
        self.assertEqual(self.opened, [])
        QTest.mouseClick(tile.include, Qt.LeftButton)
        self.assertEqual(self.included[-1], ("领取邮件", True))

    def test_clicking_the_rest_of_the_tile_opens_its_settings(self):
        tile = self.make(True)
        QTest.mouseClick(tile, Qt.LeftButton, Qt.NoModifier, QPoint(20, tile.height() - 20))
        self.assertEqual(self.opened, [True])
        self.assertEqual(self.included, [])
        self.assertTrue(tile.include.isChecked())

    def test_refresh_sets_the_check_without_reporting_a_click(self):
        tile = self.make(True)
        tile.set_included(False)
        self.assertFalse(tile.include.isChecked())
        self.assertEqual(self.included, [])


class HomeIncludeTest(unittest.TestCase):
    def test_switch_writes_the_same_key_as_the_settings_page(self):
        from unittest import mock

        from src.ui.shell.home import HomePage

        batch = mock.Mock(config={"领取邮件": True})
        page = mock.Mock()
        with mock.patch.object(data, "task_by_name", return_value=batch):
            HomePage._set_included(page, "领取邮件", False)
        self.assertIs(batch.config["领取邮件"], False)
        page.refresh.assert_called_once()


class MapOrderTest(unittest.TestCase):
    """Leo 2026-10-21: a button on the 每周跑图 card moves it to the front of
    一键日常 or back to the end; the cards slide there."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_order_follows_the_setting(self):
        from src.tasks.DailyBatchTask import (
            DAILY_BATCH_CHILDREN,
            MAP_CHILD_KEY,
            MAP_FIRST_KEY,
            DailyBatchTask,
            ordered_children,
        )

        self.assertEqual(ordered_children(DAILY_BATCH_CHILDREN, False), DAILY_BATCH_CHILDREN)
        first = ordered_children(DAILY_BATCH_CHILDREN, True)
        self.assertEqual(first[0].config_key, MAP_CHILD_KEY)
        self.assertEqual(first[1:], DAILY_BATCH_CHILDREN[:-1])
        task = object.__new__(DailyBatchTask)
        task.config = {MAP_FIRST_KEY: False}
        self.assertEqual(task.child_tasks[-1].config_key, MAP_CHILD_KEY)
        task.config[MAP_FIRST_KEY] = True
        self.assertEqual(task.child_tasks[0].config_key, MAP_CHILD_KEY)
        task.child_tasks = DAILY_BATCH_CHILDREN[:2]  # tests may still set their own
        self.assertEqual(task.child_tasks, DAILY_BATCH_CHILDREN[:2])

    def test_button_moves_the_card_and_the_run(self):
        from unittest import mock

        from src.tasks.DailyBatchTask import (
            DAILY_BATCH_CHILDREN,
            MAP_CHILD_KEY,
            MAP_FIRST_KEY,
            ordered_children,
        )
        from src.ui.shell.home import HomePage

        class Batch:
            name = data.DAILY_BATCH
            info = {}
            config = {}

            @property
            def child_tasks(self):
                return ordered_children(DAILY_BATCH_CHILDREN, self.config.get(MAP_FIRST_KEY))

        batch = Batch()
        with (
            mock.patch.object(data, "task_by_name", lambda name: batch),
            mock.patch.object(data, "busy", lambda: False),
            mock.patch.object(data, "executor", lambda: None),
        ):
            page = HomePage(lambda *_a: None, lambda *_a: None)
            page.resize(900, 1000)
            page.show()
            self.addCleanup(page.hide)
            page._refresh_idle()
            QApplication.processEvents()
            tile = page._tiles[MAP_CHILD_KEY]
            self.assertIsNotNone(tile.order)
            others = [t for t in page._tiles.values() if t is not tile and t.order is not None]
            self.assertEqual(others, [])
            last = page.tiles.itemAt(page.tiles.count() - 1).widget()
            self.assertIs(last, tile)

            tile.order.click()
            self.assertTrue(batch.config[MAP_FIRST_KEY])
            self.assertIs(page.tiles.itemAt(0).widget(), tile)
            page._moving.setCurrentTime(page._moving.totalDuration())
            QApplication.processEvents()
            self.assertIsNone(page._moving)
            self.assertEqual(tile.pos(), page.tiles.itemAt(0).geometry().topLeft())

            tile.order.click()
            self.assertFalse(batch.config[MAP_FIRST_KEY])
            self.assertIs(page.tiles.itemAt(page.tiles.count() - 1).widget(), tile)


if __name__ == "__main__":
    unittest.main()
