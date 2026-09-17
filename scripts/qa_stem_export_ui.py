"""Capture stem-export controls with generated audio and disposable settings."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from PIL import ImageGrab
import test_workspace
from test_stem_export import attach_stems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "docs/qa/stem-export")
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    captures = evidence / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    case = test_workspace.WorkspaceTests()
    case.setUp()
    app = case.app
    results = {"method": "Isolated Tk app; generated audio; app scale 100%", "captures": []}

    def capture(name, window=None):
        app.update()
        window = window or app
        ImageGrab.grab(window=int(window.frame(), 0)).save(captures / (name + ".png"))
        results["captures"].append(name)

    try:
        attach_stems(case)
        for width, height in ((1000, 700), (760, 620), (640, 480)):
            app.geometry(f"{width}x{height}")
            app.update()
            app.workspace_scroll.canvas.yview_moveto(1 if width == 640 else 0)
            capture(f"export-{width}x{height}")
        app.geometry("1000x700")
        app.workspace_scroll.canvas.yview_moveto(0)
        app.update()
        app.open_render_settings()
        app.stem_export_format_var.set("MP3")
        app.update()
        capture("settings-stem-format", app._dialog)
        app._save_compact_settings()
        app.export_stems_button.invoke()
        case.wait_idle()
        assert len(app.result_files) == 4
        assert all(path.suffix == ".mp3" for path in app.result_files)
        capture("four-files-saved")
        results["output_names"] = [path.name for path in app.result_files]
        results["callback_errors"] = len(case.callback_errors)
        assert not case.callback_errors
    finally:
        case.tearDown()
    (evidence / "ui-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
