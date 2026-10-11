"""爛装强化分解: a UR is dismantled only when it is a 3★/4★ exclusive twice
over (Leo 2026-10-11 「點開裝備是五星 一定不要拆」「寧願不拆也不要誤拆」).

The item name must be on the 3★/4★ list, and the popup's owner line (the
star badge and name above 「专用装备」) must name that 3★/4★ owner.  A 5★
exclusive shows a 5★ name there; an unread line keeps the item.  Frame:
the real 4K popup of 首席勋章 (艾玛's exclusive), 2026-10-10.
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2

from src.utils.junk_gear import (
    EXCLUSIVE_TABLE,
    GearItem,
    classify,
    load_exclusive_owners,
    load_exclusive_stars,
)

FIXTURES = Path(__file__).parent / "fixtures" / "junk_gear"

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover - the tool always ships onnxocr
    ONNXPaddleOcr = None


def _ur(name, owner_line):
    return GearItem(name, "UR", False, False, False, owner_line=owner_line)


class OwnerRuleTest(unittest.TestCase):
    def setUp(self):
        self.stars = load_exclusive_stars()
        self.owners = load_exclusive_owners()

    def _junk(self, item):
        return classify(item, self.stars, exclusive_owners=self.owners)[0]

    def test_the_owner_named_on_the_popup_allows_the_dismantle(self):
        self.assertTrue(self._junk(_ur("首席勋章", "☆艾玛")))
        self.assertTrue(self._junk(_ur("首席徽章", "艾瑪")))

    def test_a_5_star_name_on_the_popup_keeps_it(self):
        self.assertFalse(self._junk(_ur("首席勋章", "☆悠丝缇亚")))

    def test_an_unread_owner_line_keeps_it(self):
        self.assertFalse(self._junk(_ur("首席勋章", None)))
        self.assertFalse(self._junk(_ur("首席勋章", "")))
        self.assertFalse(self._junk(_ur("首席勋章", "艾")))

    def test_a_5_star_exclusive_is_kept_whatever_the_owner_line(self):
        self.assertFalse(self._junk(_ur("皇家钢剑", "☆艾玛")))


class TableTest(unittest.TestCase):
    """The 3★/4★ exclusives are a closed set (Leo 2026-10-11 「就那些 不會再多了」),
    checked against browndust2-db.souseha.com on 2026-10-11."""

    def test_23_low_star_exclusives_each_with_both_owner_names(self):
        rows = json.loads(EXCLUSIVE_TABLE.read_text(encoding="utf-8"))["items"]
        low = [row for row in rows if row["star"] < 5]
        self.assertEqual(23, len(low))
        for row in low:
            self.assertTrue(row.get("character_cn") and row.get("character_tw"), row)


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class RealPopupTest(unittest.TestCase):
    def test_the_owner_line_of_the_real_popup_reads_emma(self):
        from src.tasks.JunkGearTask import DETAIL_ROI, JunkGearTask

        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True)
        crop = cv2.imread(str(FIXTURES / "detail_r_exclusive_emma_4k_at_1080.jpg"))
        x0, y0 = DETAIL_ROI[:2]
        boxes = []
        for points, (text, _score) in engine.ocr(crop)[0] or []:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            boxes.append(SimpleNamespace(
                name=text, x=x0 + min(xs), y=y0 + min(ys),
                width=max(xs) - min(xs), height=max(ys) - min(ys),
            ))
        line = JunkGearTask._owner_line(boxes)
        self.assertIn("艾玛", line)
        stars, owners = load_exclusive_stars(), load_exclusive_owners()
        self.assertTrue(classify(_ur("首席勋章", line), stars, exclusive_owners=owners)[0])


if __name__ == "__main__":
    unittest.main()
