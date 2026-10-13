"""The developer-only frame recorder (off unless BD2_RECORD_FRAMES is set)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.utils import frame_recorder


class FrameRecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = dict(frame_recorder._state)
        frame_recorder._state.update(dir=Path(self.tmp.name), count=0, thumb=None, name=None)

    def tearDown(self):
        frame_recorder._state.clear()
        frame_recorder._state.update(self.saved)
        self.tmp.cleanup()

    def test_off_without_the_variable(self):
        frame_recorder._state["dir"] = None
        with mock.patch.dict(os.environ, {}, clear=True):
            frame_recorder.install()
        self.assertIsNone(frame_recorder.folder())
        frame_recorder.note("ocr", np.zeros((1080, 1920, 3), np.uint8), text=["x"])

    def test_same_frame_saved_once_new_frame_saved_again(self):
        frame = np.zeros((1080, 1920, 3), np.uint8)
        first = frame_recorder.frame_name(frame)
        self.assertEqual(first, frame_recorder.frame_name(frame.copy()))
        second = frame_recorder.frame_name(np.full((1080, 1920, 3), 200, np.uint8))
        self.assertNotEqual(first, second)
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.png"))), 2)

    def test_crops_are_not_saved_and_4k_is_saved_at_1080(self):
        self.assertIsNone(frame_recorder.frame_name(np.zeros((56, 133, 3), np.uint8)))
        name = frame_recorder.frame_name(np.zeros((2160, 3840, 3), np.uint8))
        import cv2

        self.assertEqual(cv2.imread(str(Path(self.tmp.name) / name)).shape[:2], (1080, 1920))
        self.assertIn("3840x2160", name)

    def test_matches_are_written_once_per_top_level_call(self):
        result = SimpleNamespace(score=0.97, pixel_score=0.91, position=(1, 2), size=(3, 4))
        module = SimpleNamespace()

        def inner(frame, spec, *a, **k):
            if spec.name == "outer":
                module.match_template(frame, SimpleNamespace(name="inner", file_name="i.png"))
            return result

        module.match_template = inner
        frame_recorder._wrap_match_template(module)
        module.match_template(np.zeros((1080, 1920, 3), np.uint8), SimpleNamespace(name="outer", file_name="o.png"))
        rows = [json.loads(line) for line in open(Path(self.tmp.name) / "reads.jsonl", encoding="utf-8")]
        self.assertEqual([row["spec"] for row in rows], ["o.png"])
        self.assertEqual(rows[0]["pixel"], 0.91)
        self.assertTrue(rows[0]["frame"].endswith(".png"))


if __name__ == "__main__":
    unittest.main()
