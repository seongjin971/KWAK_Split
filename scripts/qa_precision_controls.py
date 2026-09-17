"""Capture the numeric/fade changes in an isolated generated-audio workspace."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from PIL import ImageGrab
import test_workspace


def main():
    evidence = ROOT / "docs/qa/precision-controls"
    captures = evidence / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    case = test_workspace.WorkspaceTests()
    case.setUp()
    app = case.app
    results = {"method": "Isolated Tk app with generated six-second audio; app scale 100%", "captures": []}

    def capture(name, window=None):
        app.update()
        window = window or app
        ImageGrab.grab(window=int(window.frame(), 0)).save(captures / (name + ".png"))
        results["captures"].append(name)

    try:
        app.selection_start_var.set(.5)
        app.selection_end_var.set(5.5)
        app.fade_in_var.set(.8)
        app.fade_out_var.set(.6)
        app.eq_low_var.set(-24)
        app.eq_mid_var.set(6)
        app.eq_high_var.set(12)
        for width, height in ((1000, 700), (760, 620), (640, 480)):
            app.geometry(f"{width}x{height}")
            app.update()
            app.draw_waveform()
            capture(f"fades-{width}x{height}")
            if width == 640:
                app.workspace_scroll.canvas.yview_moveto(1)
                capture("narrow-mixer")
        app.geometry("1000x700")
        app.workspace_scroll.canvas.yview_moveto(0)
        app.fade_in_var.set(.02)
        app.fade_out_var.set(.02)
        app.view_start, app.view_end = .49, .55
        app.update()
        app.draw_waveform()
        capture("20ms-fade-zoom")
        assert app.wave_canvas.find_withtag("fade-envelope")
        assert app.start_spinbox.get() == "0.50"
        assert app.end_spinbox.get() == "5.50"
        app.open_render_settings()
        app.update()
        capture("settings", app._dialog)
        app._close_render_settings()
        app.view_start, app.view_end = 0, app.duration_seconds
        app.update()
        samples = []
        for _ in range(5):
            started = time.perf_counter()
            app.draw_waveform()
            samples.append((time.perf_counter() - started) * 1000)
        results["waveform_draw_ms"] = [round(value, 2) for value in samples]
        results["callback_errors"] = len(case.callback_errors)
        assert not case.callback_errors, case.callback_errors
    finally:
        case.tearDown()
    (evidence / "ui-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
