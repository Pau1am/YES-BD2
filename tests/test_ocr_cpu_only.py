"""OCR runs on the CPU on every PC, the way the tests read.

ok-script turns an Intel NPU on unless told otherwise, and onnxocr then
reads every box at one fixed input size.  A player's 跑商 shop title
(v0.1.21, 2026-10-11) read 「-」; the same frame reads nothing at that size
and 「购买」 on the CPU (see test_trade_shop_title_read).
"""

import unittest

from src.config import config


class OcrDeviceTest(unittest.TestCase):
    def test_the_npu_is_not_used(self):
        params = config["ocr"]["default"]["params"]
        # ok-script 2.0.6 TaskExecutor: use_npu=config_params.get('use_npu', True).
        self.assertIs(False, params.get("use_npu", True))
        self.assertTrue(params["use_openvino"])


if __name__ == "__main__":
    unittest.main()
