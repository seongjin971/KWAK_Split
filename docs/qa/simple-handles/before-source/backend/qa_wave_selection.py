"""Opt-in source/frozen checks using isolated generated audio and Tk events."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from PIL import ImageGrab

from backend.app_paths import AppPaths


def check(app_type, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = AppPaths.from_runtime()
    result = {"frozen": bool(getattr(sys, "frozen", False)),
              "method": "real Tk generated gestures; simulated display areas; muted native audio",
              "physical_input_tested": False, "display_cases": [], "playback": []}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-selection-qa-") as folder, ExitStack() as cleanup:
            class QAPaths(AppPaths):
                @property
                def bin(self): return assets.bin
                @property
                def backend(self): return assets.backend
                @property
                def models(self): return assets.models
            paths = QAPaths(Path(folder))
            paths.ensure()
            source = paths.root / "generated.wav"
            subprocess.run([str(paths.bin / "ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=12:sample_rate=48000", "-ac", "2", str(source)],
                           check=True, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            cleanup.enter_context(patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}))
            cleanup.enter_context(patch.object(AppPaths, "from_runtime", return_value=paths))
            cleanup.enter_context(patch.object(app_type, "_configure_logging"))
            app = app_type(ui_scale=1)
            cleanup.callback(app._warm_transport.close)
            cleanup.callback(app.on_close)
            errors = []
            app.report_callback_exception = lambda *args: errors.append(repr(args))

            def pump(predicate=lambda: True, timeout=8):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    app.update()
                    if predicate(): return
                    time.sleep(.005)
                raise AssertionError("Selection check timed out")

            def select(a, b):
                app.selection_start_var.set(a); app.selection_end_var.set(b)
                app._selection_changed(); app._commit_edit(); app.update()

            def point(seconds):
                a, b = app._wave_view_bounds()
                return round((seconds-a)/(b-a)*app.wave_canvas.winfo_width())

            def drag(x1, x2, y, button=1):
                canvas = app.wave_canvas
                for event, x in ((f"<Button-{button}>", x1), (f"<B{button}-Motion>", x2), (f"<ButtonRelease-{button}>", x2)):
                    canvas.event_generate(event, x=round(x), y=round(y))
                app.update()

            def click(seconds, shift=False):
                for event in ("<Button-1>","<ButtonRelease-1>"):
                    app.wave_canvas.event_generate(event,x=point(seconds),y=round(50*app.ui_scale),state=int(shift))
                app.update()

            def key(name):
                app.event_generate("<KeyPress-"+name+">")
                app.event_generate("<KeyRelease-"+name+">")
                app.update()

            app.load_audio_path(source); pump(lambda: not app.busy)
            app.loop_var.set(False)
            app.fade_in_var.set(0); app.fade_out_var.set(0)
            for screen_name, screen in (("fhd", (1920,1080)), ("qhd", (2560,1440)), ("4k", (3840,2160))):
                for scale in (1, 1.25, 1.5, 1.75, 2):
                    app._ui_scale_override = scale; app._display_scale = scale
                    with patch("backend.compact_ui.display_metrics", return_value=((0,0,screen[0],screen[1]-40), scale)):
                        app._set_initial_compact_window(); pump()
                        for name, size in (("minimum",app.minsize()), ("initial",app._fixed_limits.initial_size), ("maximum",app.maxsize())):
                            app._window_constraints.resize(*size, position=(24,24)); pump()
                            app.view_start, app.view_end = 0, 12
                            select(0,12);click(2);click(8,shift=True)
                            a,b=app._selection_bounds()
                            assert abs(a-2)<=.011 and abs(b-8)<=.011,(a,b)
                            select(2, 8)
                            width, height = app.winfo_width(), app.winfo_height()
                            assert width*7 == height*10 and not app.workspace_scroll.bar.winfo_ismapped()
                            y = 50 * app.ui_scale
                            offset = round(8 * app.ui_scale)
                            assert app._wave_selection.hit(SimpleNamespace(x=point(2)+offset,y=y)) == "start"
                            drag(point(2)+offset, point(3)+offset, y)
                            a,b = app._selection_bounds()
                            assert abs(a-3) <= .011 and b == 8, (a,b)
                            grip = app._wave_selection.grip()
                            x, y = (grip[0]+grip[2])/2, (grip[1]+grip[3])/2
                            assert app._wave_selection.hit(SimpleNamespace(x=x,y=y)) == "move"
                            drag(x, x+app.wave_canvas.winfo_width()/12, y)
                            moved = app._selection_bounds()
                            assert abs(moved[0]-4) <= .021 and abs((moved[1]-moved[0])-(b-a)) < 1e-9
                            app.undo_edit(); assert app._selection_bounds() == (a,b)
                            app.redo_edit(); assert app._selection_bounds() == moved
                            assert len(app.wave_canvas.find_withtag("selection-handle")) == 2
                            if screen_name == "fhd" and scale == 1 and name in ("minimum","initial"):
                                ImageGrab.grab(window=int(app.winfo_id())).save(output.with_name(output.stem+"-"+name+".png"))
                            result["display_cases"].append({"screen":screen_name,"dpi":scale,"size":name,
                                                            "client":[width,height],"range":moved})
            app._ui_scale_override = 1; app._set_initial_compact_window(); app.update()
            for target, expected in ((2,(2,4)), (6,(4,6))):
                select(4,4)
                drag(point(4),point(target),50*app.ui_scale,button=3)
                a,b = app._selection_bounds()
                assert abs(a-expected[0]) <= .011 and abs(b-expected[1]) <= .011
            result["restored_point_selects_both_directions"] = True
            for inputs in (1,4):
                if inputs == 4:
                    app.stem_paths = {stem:app.source_wav for stem in app.stem_vars}
                    app.stem_range = (0,12)
                select(0,12);click(2);app.playback_cursor_manual = False
                app._refresh_action_states(); app.focus_force(); app.update()
                key("space")
                pump(lambda: app.realtime_processes and app.realtime_processes.position_seconds() > .2)
                owner = app.realtime_processes
                click(8,shift=True);click(6,shift=True)
                a,b=app._selection_bounds()
                assert abs(a-2)<=.011 and abs(b-6)<=.011
                clock=owner.position_seconds()
                pump(lambda:owner.position_seconds()>clock+.15)
                assert app.realtime_processes is owner and app.preview_playing
                select(0,12)
                key("bracketleft")
                start = app._selection_bounds()[0]
                pump(lambda: owner.playback_position().position_seconds > start+.6)
                key("bracketright")
                end = app._selection_bounds()[1]
                pump(lambda: owner.playback_position().position_seconds > end+.2)
                assert app.preview_playing and app.realtime_processes is owner
                assert owner.player.poll() is None and owner._settings["fade_bounds"] == (0,12)
                key("space"); key("space")
                pump(lambda: app.realtime_processes and app.realtime_processes is not owner)
                assert app.realtime_processes._settings["fade_bounds"] == (start,end)
                result["playback"].append({"inputs":inputs,"marked_range":[start,end],
                                           "shift_click_keeps_stream_and_anchor":True,
                                           "same_stream_while_marking":True,"next_play_uses_range":True})
                app.stop_preview(False); app._warm_transport.cancel(wait=True)
            assert not errors, errors
            result["callback_errors"] = errors
        result["status"] = "passed"
    except Exception as exc:
        import traceback
        result["status"] = "failed"; result["error"] = repr(exc)
        result["traceback"] = traceback.format_exc()
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1
