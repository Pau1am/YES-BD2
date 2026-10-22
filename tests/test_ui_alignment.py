"""Shared layout fixes from the 2026-10-22 alignment check (every page and
dialog drawn in 5 languages, light/dark, 100-200 % scaling)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.ui.shell import widgets
from src.ui.shell.page import CARD_EDGE, Page, align_to_cards
from src.ui.shell.widgets import Button, Card, Text, grid_container, hbox, shell_buttons


class _Tall(QWidget):
    """A card whose content needs more than the grid's row height."""

    def minimumSizeHint(self) -> QSize:
        return QSize(80, 130)

    def sizeHint(self) -> QSize:
        return QSize(100, 130)


class TileGridRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fixed_row_height_never_cuts_a_card(self):
        container, grid = grid_container(100, 10, None, 104)
        tall, short = _Tall(), QWidget()
        grid.addWidget(tall)
        grid.addWidget(short)
        container.resize(400, grid.heightForWidth(400))
        grid.setGeometry(container.rect())
        self.assertEqual(tall.height(), 130)
        self.assertEqual(short.height(), 130)

    def test_rows_that_fit_keep_the_fixed_height(self):
        container, grid = grid_container(100, 10, None, 104)
        tile = QWidget()
        grid.addWidget(tile)
        grid.setGeometry(container.rect().adjusted(0, 0, 300, 300))
        self.assertEqual(tile.height(), 104)


class AlignToCardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_titles_move_in_to_the_card_edge_and_cards_stay(self):
        host = QWidget()
        column = QVBoxLayout(host)
        title = Text("标题", "h2")
        row = hbox(None, (0, 0, 0, 0), 8)
        row.addWidget(Text("说明", "muted"))
        card = Card()
        column.addWidget(title)
        column.addLayout(row)
        column.addWidget(card)
        align_to_cards(column)
        self.assertEqual(title.contentsMargins().left(), CARD_EDGE)
        self.assertEqual(title.contentsMargins().right(), CARD_EDGE)
        self.assertEqual(row.contentsMargins().left(), CARD_EDGE)
        self.assertEqual(card.contentsMargins().left(), widgets.SHADOW_MARGINS[0])

    def test_a_second_pass_does_not_move_them_again(self):
        host = QWidget()
        column = QVBoxLayout(host)
        title = Text("标题", "h2")
        column.addWidget(title)
        align_to_cards(column)
        align_to_cards(column)
        self.assertEqual(title.contentsMargins().left(), CARD_EDGE)

    def test_containers_with_cards_are_walked_into_and_empty_ones_wait(self):
        host = QWidget()
        column = QVBoxLayout(host)
        view = QWidget()
        inner = QVBoxLayout(view)
        note = Text("说明", "muted")
        inner.addWidget(note)
        inner.addWidget(Card())
        empty = QWidget()
        QVBoxLayout(empty)
        column.addWidget(view)
        column.addWidget(empty)
        align_to_cards(column)
        self.assertEqual(view.contentsMargins().left(), 0)
        self.assertEqual(note.contentsMargins().left(), CARD_EDGE)
        self.assertEqual(empty.contentsMargins().left(), 0)

    def test_page_header_lines_up_with_its_cards(self):
        page = Page("alignTest", "标题", "说明")
        page.body.addWidget(Card())
        page.resize(600, 400)
        page.show()
        self.app.processEvents()
        header = page.body.itemAt(0).widget()
        self.assertEqual(header.contentsMargins().left(), CARD_EDGE)
        page.hide()


class ButtonIconGapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_room_for_the_wider_gap(self):
        plain = Button("一键完成日常", "primary")
        with_icon = Button("一键完成日常", "primary", "play")
        extra = with_icon.sizeHint().width() - plain.sizeHint().width()
        self.assertGreaterEqual(extra, with_icon.iconSize().width() + Button.ICON_GAP)

    def test_icon_and_text_both_draw(self):
        button = Button("开始", "primary", "play")
        button.resize(button.sizeHint())
        self.assertFalse(button.grab().isNull())


class ShellButtonsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fluent_buttons_are_replaced_and_still_answer(self):
        from qfluentwidgets import MessageBox

        parent = QWidget()
        parent.resize(800, 600)
        box = MessageBox("标题", "内容", parent)
        box.yesButton.setText("好")
        box.cancelButton.setText("取消")
        shell_buttons(box)
        own = [b for b in box.findChildren(Button)]
        self.assertEqual([b.text() for b in own], ["好", "取消"])
        self.assertTrue(box.yesButton.isHidden())
        self.assertTrue(box.cancelButton.isHidden())
        answered = []
        box.yesSignal.connect(lambda: answered.append("yes"))
        own[0].click()
        self.assertEqual(answered, ["yes"])

    def test_a_hidden_cancel_stays_away(self):
        from qfluentwidgets import MessageBox

        parent = QWidget()
        box = MessageBox("标题", "内容", parent)
        box.cancelButton.hide()
        shell_buttons(box)
        self.assertEqual(len(box.findChildren(Button)), 1)

    def test_every_fluent_box_in_the_shell_gets_them(self):
        """A new MessageBox without shell_buttons would be teal again."""
        import re
        from pathlib import Path

        folder = Path(__file__).resolve().parents[1] / "src" / "ui" / "shell"
        for path in folder.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            boxes = len(re.findall(r"\bMessageBox(?:Base)?\(", text))
            if path.name == "trade.py":
                boxes -= 1  # 循环砍价 builds its own buttons
            self.assertLessEqual(boxes, text.count("shell_buttons("), path.name)


if __name__ == "__main__":
    unittest.main()
