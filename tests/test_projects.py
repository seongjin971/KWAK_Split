import json
import tempfile
import unittest
from pathlib import Path
from threading import Event

from backend.project_store import EditHistory, atomic_json, read_project, save_project, validate_edits
from backend.audio_processing.ffmpeg_tools import OperationCancelled


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="project-test-", dir=Path(__file__).resolve().parents[1] / "temp")
        self.root = Path(self.folder.name)
        self.audio = self.root / "original.wav"
        self.audio.write_bytes(b"test audio content")
        self.project = self.root / "\uc791\uc5c5.kwaksplit"
        self.document = {"edits": validate_edits({"tempo_percent": 75.0}), "stem_range": [2.0, 4.0]}

    def tearDown(self):
        self.folder.cleanup()

    def test_bundle_survives_original_removal_and_reuses_assets(self):
        save_project(self.project, self.document, self.audio, {"vocals": self.audio})
        loaded = read_project(self.project)
        self.assertEqual(loaded["edits"]["tempo_percent"], 75.0)
        self.assertEqual(loaded["source_path"], loaded["stem_paths"]["vocals"])
        self.audio.unlink()
        self.assertEqual(loaded["source_path"].read_bytes(), b"test audio content")
        save_project(self.project, self.document, loaded["source_path"], loaded["stem_paths"])
        self.assertEqual(len(list(self.project.with_name(self.project.name + ".assets").glob("*.wav"))), 1)

    def test_cancel_does_not_replace_existing_project(self):
        save_project(self.project, self.document, self.audio, {})
        original = self.project.read_bytes()
        cancellation = Event()
        cancellation.set()
        with self.assertRaises(OperationCancelled):
            save_project(self.project, self.document, self.audio, {}, cancellation)
        self.assertEqual(self.project.read_bytes(), original)
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_path_escape_is_rejected(self):
        save_project(self.project, self.document, self.audio, {})
        doc = json.loads(self.project.read_text(encoding="utf-8"))
        doc["source"] = "../outside.wav"
        atomic_json(self.project, doc)
        with self.assertRaises(ValueError):
            read_project(self.project)

    def test_malformed_and_nonfinite_edits_rejected(self):
        for edits in ({"eq_low": float("nan")}, {"tempo_percent": 0}, {"bit_depth": 8}, {"sample_rate": 96000}, {"stems": []}):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                validate_edits(edits)

    def test_history_undo_redo_branch_and_limit(self):
        history = EditHistory({"x": 0}, limit=3)
        for value in (1, 2, 3):
            history.push({"x": value})
        self.assertEqual(history.undo(), {"x": 2})
        self.assertEqual(history.redo(), {"x": 3})
        history.undo()
        history.push({"x": 4})
        self.assertEqual(history.redo(), {"x": 4})
        self.assertLessEqual(len(history.states), 3)


if __name__ == "__main__":
    unittest.main()
