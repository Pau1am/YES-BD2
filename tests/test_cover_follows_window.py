"""Overlays over the whole tool window keep covering it at any size (Leo
2026-10-21 「以後這種通知 全螢幕也要做適配」: after 最大化 the 救赎之塔 walk-through
dimmed only the top-left part, the size the window had when it opened)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

from src.ui.shell import cover, new_setting_notice

app = QApplication.instance() or QApplication([])

SIZES = ((918, 585), (1920, 1080), (2560, 1380), (3840, 2160), (800, 600))


def _settle():
    for _ in range(5):
        app.processEvents()


def _window(size=SIZES[0]):
    window = QWidget()
    window.setAttribute(Qt.WA_StyledBackground, True)
    window.setStyleSheet("background: #f4f4f8;")
    window.resize(*size)
    target = QLabel("救赎之塔", window)
    target.setGeometry(260, 560, 280, 36)
    window.show()
    _settle()
    return window, target


def _dimmed(window, point: QPoint) -> bool:
    shot = window.grab().toImage()
    ratio = shot.devicePixelRatio()
    colour = QColor(shot.pixel(round(point.x() * ratio), round(point.y() * ratio)))
    return colour.lightness() < QColor("#f4f4f8").lightness() - 30


class CoachMarksFollowWindowTest(unittest.TestCase):
    def _tour(self, window, target):
        steps = [new_setting_notice.Step(lambda: target, "救赎之塔", "每天到恶魔城")]
        tour = new_setting_notice.CoachMarks(window, steps, lambda: None)
        tour.start()
        _settle()
        return tour

    def test_dims_whole_window_after_each_resize(self):
        window, target = _window()
        tour = self._tour(window, target)
        for size in SIZES:
            with self.subTest(size=size):
                window.resize(*size)
                _settle()
                self.assertEqual(window.rect(), tour.geometry())
                corner = QPoint(window.width() - 5, window.height() - 5)
                self.assertTrue(_dimmed(window, corner), "far corner is not dimmed")
                self.assertTrue(tour.mask().contains(corner))
                # The lit control stays clickable and the card stays inside.
                self.assertFalse(tour.mask().contains(target.geometry().center()))
                self.assertTrue(window.rect().contains(tour.card.geometry()))
        tour.finish()

    def test_maximize_state_change_resyncs(self):
        window, target = _window()
        tour = self._tour(window, target)
        window.setWindowState(Qt.WindowMaximized)
        window.resize(2560, 1380)
        _settle()
        self.assertEqual(window.rect(), tour.geometry())
        self.assertTrue(_dimmed(window, QPoint(window.width() - 5, window.height() - 5)))
        tour.finish()

    def test_timer_catches_a_missed_resize(self):
        window, target = _window()
        tour = self._tour(window, target)
        window.removeEventFilter(tour._cover)
        window.resize(1920, 1080)
        tour._tick()
        _settle()
        self.assertEqual(window.rect(), tour.geometry())
        self.assertTrue(tour.mask().contains(QPoint(1915, 1075)))
        tour.finish()


class DialogFollowsWindowTest(unittest.TestCase):
    def test_dialog_tracks_window_geometry(self):
        window, _ = _window()
        dialog = QDialog(window)
        dialog.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        cover.follow(dialog, window)
        self.assertEqual(window.geometry(), dialog.geometry())
        window.setGeometry(0, 0, 2560, 1380)
        _settle()
        self.assertEqual(window.geometry(), dialog.geometry())

    def test_every_window_overlay_uses_cover(self):
        """New overlays must follow the window too, not copy its size once."""
        import pathlib
        import re

        shell = pathlib.Path(__file__).resolve().parents[1] / "src" / "ui" / "shell"
        once = re.compile(r"setGeometry\([^)]*(window\(\)|_window|window)\.(geometry|rect)\(\)")
        offenders = [
            path.name
            for path in shell.glob("*.py")
            if path.name != "cover.py" and once.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
