import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.shell.report_page import ReportPage


class ReportStatHeightTest(unittest.TestCase):
    """Leo 2026-10-14: 「報表 0的底部被切到」 — the count boxes fit their numbers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_count_boxes_are_tall_enough_for_the_big_number(self):
        page = ReportPage()
        page.resize(1400, 600)
        page.show()
        self.app.processEvents()
        for value in (page.stat_tasks, page.stat_done, page.stat_fail, page.stat_runs):
            card = value.parentWidget()
            self.assertGreaterEqual(card.height(), card.sizeHint().height() + 4)
        page.close()


if __name__ == "__main__":
    unittest.main()
