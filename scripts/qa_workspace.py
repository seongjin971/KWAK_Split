"""Capture the controlled test app and optionally check real Demucs separation.

python -B scripts/qa_workspace.py --real-demucs
Generated test inputs are isolated under temp/; model weights stay in models/.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import read_duration
from backend.project_store import atomic_json
from test_workspace import WorkspaceTests


class ModelPaths(AppPaths):
    @property
    def backend(self):
        return ROOT / "backend"

    @property
    def models(self):
        return ROOT / "models"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-demucs", action="store_true")
    parser.add_argument("--no-capture", action="store_true")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "docs" / "qa")
    args = parser.parse_args()
    evidence_root = args.evidence_dir.resolve()
    evidence = evidence_root / "captures"
    evidence.mkdir(parents=True, exist_ok=True)
    test = WorkspaceTests()
    test.setUp()
    app = test.app
    results = {"real_demucs": False, "captures": [], "source": "generated 6-second sine WAV"}
    try:
        if args.real_demucs:
            os.environ["OMP_NUM_THREADS"] = "2"
            os.environ["MKL_NUM_THREADS"] = "2"
            app.paths = ModelPaths(test.paths.root)
            app.selection_start_var.set(2.0)
            app.selection_end_var.set(4.0)
            app.split_scope_var.set("Selection")
            started = time.monotonic()
            print("Real Demucs: splitting original 2..4 seconds", flush=True)
            app.separate_stems()
            test.wait_idle(timeout=300)
            assert len(app.stem_paths) == 4, app.log_messages[-20:]
            assert app.stem_range == (2.0, 4.0)
            results["real_demucs"] = True
            results["split_seconds"] = round(time.monotonic() - started, 3)
            results["stem_durations"] = {name: read_duration(app.paths, path) for name, path in app.stem_paths.items()}
            assert all(abs(value - 2.0) < 0.1 for value in results["stem_durations"].values())
            app.sample_rate_var.set(48000)
            app.bit_depth_var.set(24)
            app.export_individual_stems()
            test.wait_idle()
            assert len(app.result_files) == 4
            results["exported_durations"] = [read_duration(app.paths, path) for path in app.result_files]
            print("Real Demucs: four stems and four exports passed", flush=True)
        if not args.no_capture:
            from PIL import ImageGrab
            for width, height, name, tab, scroll in (
                (1280, 720, "desktop-top", 0, 0), (900, 600, "compact-top", 0, 0),
                (900, 600, "compact-eq", 2, 0.6), (640, 480, "small-results", 0, 1)):
                app.geometry(f"{width}x{height}+20+20")
                app.editor_tabs.select(tab)
                app.update()
                app.workspace_scroll.canvas.yview_moveto(scroll)
                # Let deferred resize/redraw callbacks settle before capturing.
                settled_at = time.monotonic() + 0.25
                while time.monotonic() < settled_at:
                    app.update()
                    time.sleep(0.01)
                shot = ImageGrab.grab(window=int(app.frame(), 0))
                path = evidence / f"{name}.png"
                shot.save(path)
                results["captures"].append(path.relative_to(ROOT).as_posix())
                print(f"Captured {name}: {shot.size}", flush=True)
            app.open_render_settings()
            app.update()
            window = app.render_settings_window
            ImageGrab.grab(window=int(window.frame(), 0)).save(evidence / "settings.png")
            results["captures"].append((evidence / "settings.png").relative_to(ROOT).as_posix())
            app._close_render_settings()
        test.assertFalse(test.callback_errors, test.callback_errors)
        atomic_json(evidence_root / ("workflow-results.json" if args.real_demucs else "ui-results.json"), results)
        print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    finally:
        test.tearDown()


if __name__ == "__main__":
    main()
