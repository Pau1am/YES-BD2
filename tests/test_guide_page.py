import gettext
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.shell import guide_page
from src.ui.shell.guide_page import GuidePage, GuidePicture
from src.ui.shell.sidebar import Sidebar

CATALOG_ROOT = Path(__file__).resolve().parents[1] / "i18n"
PICTURES = ("skills", "minimap_small", "minimap_big", "battle_button", "battle_dialog")
SOURCE = Path(guide_page.__file__).read_text(encoding="utf-8")


class _Item:
    def __init__(self):
        self.badge = ""

    def set_badge(self, text, kind=""):
        self.badge = text


class GuidePageTest(unittest.TestCase):
    """Leo 2026-10-05: a picture guide in the sidebar for new players."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.mkdtemp()
        patcher = mock.patch.object(guide_page, "SEEN_FILE", Path(folder) / "ui_guide.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sidebar_lists_the_guide_above_settings(self):
        keys = [key for key, _label, _icon in Sidebar.BOTTOM]
        # Leo 2026-10-14: 桌面分身 has its own guide page under 使用说明.
        self.assertEqual(["problem", "guide", "clone", "settings", "about"], keys)

    def test_every_picture_exists_and_loads(self):
        for name in PICTURES:
            with self.subTest(name=name):
                self.assertTrue(Path(guide_page.picture_path(name)).exists())
                self.assertTrue(GuidePicture(name, 300).has_picture())

    def test_badge_always_says_must_read(self):
        # Leo 2026-10-09: always marked 必看 (it used to go once opened).
        sidebar = SimpleNamespace(items={"guide": _Item()})
        navigated = []
        page = GuidePage(navigated.append, sidebar)
        self.assertEqual("必看", sidebar.items["guide"].badge)
        page.show()
        self.app.processEvents()
        self.assertEqual("必看", sidebar.items["guide"].badge)
        self.assertTrue(guide_page.seen())
        GuidePage(navigated.append, sidebar)
        self.assertEqual("必看", sidebar.items["guide"].badge)
        page.close()

    def test_settings_buttons_open_their_pages(self):
        navigated = []
        page = GuidePage(navigated.append)
        page._go("trade")
        self.assertEqual(["trade"], navigated)

    def test_guide_text_is_translated(self):
        # Every quoted Chinese line in the page has an English entry.
        import re

        catalog = gettext.translation("ok", CATALOG_ROOT, languages=["en_US"])
        texts = set(re.findall(r'"([^"\n]*[一-鿿][^"\n]*)"', SOURCE))
        texts = {text for text in texts if not text[:1].isascii()}  # docstrings
        missing = [text for text in texts if catalog.gettext(text) == text]
        self.assertEqual([], sorted(missing))


if __name__ == "__main__":
    unittest.main()
