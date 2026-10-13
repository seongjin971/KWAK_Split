"""Opt-in source/frozen checks with generated audio and isolated preferences."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from PIL import ImageGrab

from backend.app_paths import AppPaths


def check(app_type, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = AppPaths.from_runtime()
    result = {"frozen": bool(getattr(sys, "frozen", False)),
              "method": "real Tk and generated audio; current display only"}
    app = None
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-lightweight-") as folder, ExitStack() as cleanup:
            class QAPaths(AppPaths):
                @property
                def bin(self): return assets.bin
                @property
                def backend(self): return assets.backend
                @property
                def models(self): return assets.models
            paths = QAPaths(Path(folder))
            paths.ensure()
            first, second = paths.root / "first.mp3", paths.root / "second.mp3"
            for path, frequency in ((first, 440), (second, 880)):
                subprocess.run([str(paths.bin / "ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={frequency}:duration=3:sample_rate=48000", str(path)],
                    check=True, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            # A legacy recovery file is deliberately present, but must never be opened or rewritten.
            legacy = paths.temp / "recovery.json"
            legacy.write_text('{"legacy":"ignore"}', encoding="utf-8")
            cleanup.enter_context(patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}))
            cleanup.enter_context(patch.object(AppPaths, "from_runtime", return_value=paths))
            cleanup.enter_context(patch.object(app_type, "_configure_logging"))
            prompts, errors = [], []
            cleanup.enter_context(patch("tkinter.messagebox.askyesnocancel", side_effect=lambda *a, **k: prompts.append(a)))
            cleanup.enter_context(patch("tkinter.messagebox.showerror", side_effect=lambda *a, **k: errors.append(a)))

            def start():
                instance = app_type()
                instance.report_callback_exception = lambda *a: errors.append(repr(a))
                return instance

            def pump(timeout=.2, idle=False):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    app.update()
                    if idle and not app.busy:
                        return
                    time.sleep(.005)
                if idle: raise AssertionError("Audio operation timed out")

            def capture(name):
                pump()
                ImageGrab.grab(window=int(app.frame(), 0)).save(
                    output.with_name(output.stem + "-" + name + ".png"))

            def close():
                app.on_close()
                app._close_cleanup_thread.join(timeout=15)
                assert not app._close_cleanup_thread.is_alive()

            try:
                app = start()
                assert app.source_wav is None
                app.load_audio_path(first)
                pump(15, idle=True)
                previous = app.source_wav
                app.eq_low_var.set(7)
                app.pitch_semitones_var.set(4)
                app._commit_edit()
                app.drop_queue.put(second)
                pump(15, idle=True)  # The periodic drop handler may not have fired yet.
                pump(.25)
                pump(15, idle=True)
                assert app.current_input == second
                assert app.eq_low_var.get() == 0 and app.pitch_semitones_var.get() == 0
                app.undo_edit()
                assert app.eq_low_var.get() == 0
                assert not previous.exists()
                assert not prompts and not errors
                assert not hasattr(app, "save_current_project")
                assert not app.bind("<Control-Shift-R>")
                capture("replaced")
                app.open_render_settings()
                pump()
                # The dialog is inspected through its widget tree, without changing user preferences.
                labels = []
                def visit(widget):
                    if "text" in widget.keys(): labels.append(str(widget.cget("text")))
                    for child in widget.winfo_children(): visit(child)
                visit(app._dialog)
                assert not any("project" in text.lower() or "keep adjustments" in text.lower() for text in labels)
                app._close_render_settings()
                app.output_dir = paths.root / "exports"
                app.sample_rate_var.set(44100)
                app.render_wav()
                pump(15, idle=True)
                exported = list(app.output_dir.glob("*.wav"))
                assert len(exported) == 1 and exported[0].stat().st_size > 1000
                work = app.source_wav
                close()
                assert not work.exists() and first.exists() and second.exists()
                app = start()
                pump()
                assert app.source_wav is None and not app.stem_paths
                assert app.sample_rate_var.get() == 44100
                assert app.output_dir == paths.root / "exports"
                assert exported[0].exists()
                assert legacy.read_text(encoding="utf-8") == '{"legacy":"ignore"}'
                capture("fresh-start")
                assert not errors
                result.update(status="passed",replace_without_prompt=True,edits_reset=True,
                              fresh_start=True,output_preferences_retained=True,
                              exported_audio_preserved=True,legacy_recovery_untouched=True,
                              temporary_audio_removed=True,client=[app.winfo_width(),app.winfo_height()])
            finally:
                if app is not None:
                    try: alive = app.winfo_exists()
                    except Exception: alive = False
                    if alive: close()
    except Exception as exc:
        result.update(status="failed",error=repr(exc))
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"] == "passed" else 1
