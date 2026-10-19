import hashlib
import unittest
from pathlib import Path

import cv2
import numpy as np

import src  # noqa: F401  (installs the v6 recognizer)
from src.compat import ocr_models

try:
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
except ImportError:  # pragma: no cover
    ONNXPaddleOcr = None

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecognizerFilesTest(unittest.TestCase):
    def test_the_shipped_files_are_the_measured_ones(self):
        self.assertEqual(
            _sha256(ocr_models.RECOGNIZER_MODEL),
            "5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634",
        )
        self.assertEqual(
            _sha256(ocr_models.RECOGNIZER_DICT),
            "769e7fa79bb297b5f18d8dbd149e364a45bc61f2b3f574e5ea836f0b261c23a6",
        )

    def test_the_files_ship_to_players(self):
        shipped = (ROOT / "deploy.txt").read_text(encoding="utf-8").split()
        self.assertIn("assets", shipped)


class _FakeEngine:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs


class PatchTest(unittest.TestCase):
    def _patched(self):
        engine_class = type("Engine", (_FakeEngine,), {})
        ocr_models.patch_ocr_class(engine_class)
        ocr_models.patch_ocr_class(engine_class)  # a second install changes nothing
        return engine_class

    def test_ok_scripts_call_gets_the_v6_recognizer(self):
        engine = self._patched()(use_angle_cls=False, use_npu=False, use_openvino=True)
        self.assertEqual(engine.kwargs["rec_model_dir"], str(ocr_models.RECOGNIZER_MODEL))
        self.assertEqual(engine.kwargs["rec_char_dict_path"], str(ocr_models.RECOGNIZER_DICT))
        self.assertTrue(engine.kwargs["use_openvino"])

    def test_an_explicit_recognizer_is_kept(self):
        engine = self._patched()(rec_model_dir="other.onnx")
        self.assertEqual(engine.kwargs["rec_model_dir"], "other.onnx")
        self.assertNotIn("rec_char_dict_path", engine.kwargs)


@unittest.skipIf(ONNXPaddleOcr is None, "onnxocr not installed")
class RealEngineTest(unittest.TestCase):
    def test_the_engine_reads_with_v6_and_finds_with_v5(self):
        engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False)
        self.assertEqual(engine.args.rec_model_dir, str(ocr_models.RECOGNIZER_MODEL))
        self.assertIn("ppocrv5", engine.args.det_model_dir.replace("\\", "/"))
        frame = np.full((80, 360, 3), 255, np.uint8)
        cv2.putText(frame, "12345", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
        texts = [text for _box, (text, _score) in (engine.ocr(frame)[0] or [])]
        self.assertIn("12345", "".join(texts))


if __name__ == "__main__":
    unittest.main()
