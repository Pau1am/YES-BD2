"""The 定时启动 window as it really opens: nothing squashed or cut.

Leo's v0.2.7 (2026-10-22, 繁中, 2560x1440): the slot rows were squashed to
half their height and their text overlapped, and the time wheel sat crooked.
These open the real window with slots in all 5 languages, light and dark,
and look at every widget inside it, without placing it by hand first.
"""

import gettext
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from src.ui.traditional import to_traditional
from src.utils import scheduled_start as ss
from src.utils.scheduled_start import KIND_RESET, Settings, Slot
from tests.ui_fit_audit import problems

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("zh_CN", "zh_TW", "en_US", "ja_JP", "ko_KR")


def _translator(language: str):
    if language == "zh_CN":
        return lambda text: text
    if language == "zh_TW":
        return to_traditional
    # The compiled catalog the tool ships (polib is not a project dependency).
    with (ROOT / "i18n" / language / "LC_MESSAGES" / "ok.mo").open("rb") as file:
        return gettext.GNUTranslations(file).gettext


def _slots(count: int) -> list[Slot]:
    slots = [
        Slot(KIND_RESET),
        Slot(hour=8, minute=5, days=[5, 6]),
        Slot(hour=21, days=[0, 1, 2, 3, 4]),
    ]
    slots += [Slot(hour=hour, minute=30) for hour in range(9, 12)]
    return slots[:count]


class ScheduleDialogFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from src.ui.quest_theme import apply_app_font

        apply_app_font()

    def setUp(self):
        from ok import og

        from src.ui.shell import data, schedule_ui, theme

        self.ui = schedule_ui
        self.theme = theme
        batch = SimpleNamespace(
            name=data.DAILY_BATCH, child_tasks=[], config={}, info={}, batch_label="一键完成日常"
        )
        patches = [
            mock.patch.object(data, "task_by_name", lambda name: batch),
            mock.patch.object(schedule_ui, "problem", ""),
            mock.patch.object(og, "app", SimpleNamespace(tr=lambda text: text), create=True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(theme.set_theme_mode, theme.theme_mode())

    def _open(self, slots: int = 3, size=(1100, 760)):
        host = QWidget()
        host.resize(*size)
        host.setStyleSheet(self.theme.style_sheet())
        host.show()
        self.addCleanup(host.close)
        with mock.patch.object(self.ui, "_settings", Settings(True, True, _slots(slots))):
            dialog = self.ui.ScheduleDialog(host)
        dialog.resize(*size)
        dialog.show()
        self.addCleanup(dialog.close)
        # As it opens for the player: the window places itself, nothing by hand.
        for _ in range(30):
            self.app.processEvents()
        dialog._open.go(1.0, animate=False)
        for _ in range(5):
            self.app.processEvents()
        return dialog

    def test_nothing_is_squashed_or_cut_in_any_language_or_look(self):
        from ok import og

        for language in LANGUAGES:
            for mode in ("light", "dark"):
                with self.subTest(language=language, mode=mode):
                    og.app.tr = _translator(language)
                    self.theme.set_theme_mode(mode)
                    dialog = self._open()
                    self.assertEqual([], problems(dialog.panel))
                    for row in dialog._rows:
                        self.assertGreaterEqual(row.height(), row.sizeHint().height())
                    dialog.close()

    def test_content_that_grows_after_opening_still_fits(self):
        # What Leo's PC did: the height was taken before the content's own
        # size was known.  Here the text grows after the window is up.
        dialog = self._open()
        before = dialog.panel.height()
        dialog.setStyleSheet(self.theme.style_sheet() + "QLabel, QLabel[role] { font-size: 22px; }")
        for _ in range(30):
            self.app.processEvents()
        self.assertGreater(dialog.panel.height(), before)
        self.assertEqual([], problems(dialog.panel))

    def test_a_row_added_while_open_gets_its_room(self):
        dialog = self._open(slots=1)
        before = dialog.panel.height()
        dialog._add_time()
        for _ in range(30):
            self.app.processEvents()
        self.assertGreater(dialog.panel.height(), before)
        self.assertEqual([], problems(dialog.panel))

    def test_a_short_window_scrolls_the_rows_instead_of_squashing(self):
        dialog = self._open(slots=6, size=(1100, 470))
        self.assertLessEqual(dialog.panel.height(), 470 - dialog.MARGIN)
        self.assertLess(dialog.scroll.height(), dialog.rows_holder.sizeHint().height())
        self.assertEqual([], problems(dialog.panel))
        for row in dialog._rows:
            self.assertGreaterEqual(row.height(), row.sizeHint().height())

    def test_times_read_with_two_digits(self):
        dialog = self._open()
        row = dialog._rows[1]
        self.assertEqual(("08", "05"), (row.hour.currentText(), row.minute.currentText()))
        self.assertEqual("00", dialog._rows[2].minute.currentText())
        self.assertEqual(24, row.hour.count())
        self.assertEqual(60, row.minute.count())
        row.hour.setCurrentIndex(6)
        row.minute.setCurrentIndex(45)
        self.assertEqual((6, 45), (row.slot.hour, row.slot.minute))


class DefaultSlotsTest(unittest.TestCase):
    def test_a_new_install_has_no_slot(self):
        # Leo 2026-10-22 「預設的8:05不要」.
        self.assertEqual([], Settings().slots)
        self.assertEqual([], Settings.from_json({}).slots)
        self.assertIsNone(ss.next_run(Settings(enabled=True), ss.local_now()))


if __name__ == "__main__":
    unittest.main()
