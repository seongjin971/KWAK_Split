"""Opt-in package transport timing through real Tk events and a silent device."""
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from backend.app_paths import AppPaths


def check(app_type, output):
    output=Path(output).resolve();assets=AppPaths.from_runtime();app=None
    previous_driver=os.environ.get("SDL_AUDIODRIVER");os.environ["SDL_AUDIODRIVER"]="dummy"
    result={"frozen":bool(getattr(sys,"frozen",False)),"method":"real Tk Space events and SDL dummy",
            "physical_key_to_speaker_measured":False,"runs":[]}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-transport-qa-") as folder:
            class QAPaths(AppPaths):
                @property
                def bin(self):return assets.bin
                @property
                def backend(self):return assets.backend
                @property
                def models(self):return assets.models
            paths=QAPaths(Path(folder));paths.ensure();source=paths.root/"generated.wav"
            subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error","-f","lavfi","-i",
                "sine=frequency=440:duration=6:sample_rate=48000","-c:a","pcm_s24le",str(source)],
                check=True,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
            with patch.object(AppPaths,"from_runtime",return_value=paths),patch.object(app_type,"_configure_logging"):
                app=app_type();errors=[]
                app.report_callback_exception=lambda *args:errors.append(repr(args))
                def pump(predicate,timeout=5):
                    deadline=time.perf_counter()+timeout
                    while time.perf_counter()<deadline:
                        app.update()
                        if predicate():return time.perf_counter()
                        time.sleep(.002)
                    raise AssertionError("Transport check timed out")
                def space():
                    began=time.perf_counter()
                    app.event_generate("<KeyPress-space>");app.event_generate("<KeyRelease-space>")
                    returned=time.perf_counter();app.update_idletasks()
                    return began,returned,time.perf_counter()
                app.load_audio_path(source);pump(lambda:not app.busy)
                app.loop_var.set(False);app.fade_in_var.set(0);app.fade_out_var.set(0)
                app.limiter_enabled_var.set(False);app.focus_force();app.update()
                for inputs in (1,4):
                    if inputs==4:
                        for name in ("vocals","drums","bass","other"):
                            path=paths.root/(name+".wav");shutil.copy2(app.source_wav,path)
                            app.stem_paths[name]=path
                        app.stem_range=(0,app.duration_seconds);app._refresh_action_states();app.update()
                    rows=[]
                    for _ in range(6):
                        app.playback_cursor_manual=False
                        start,returned,painted=space()
                        assert app.preview_playing and app.play_button.cget("text")=="Pause"
                        owner=app.realtime_processes
                        ready=pump(lambda:owner._sent_frames>0)
                        clock=pump(lambda:owner._clock is not None and owner._clock[0]>0)
                        pump(lambda:owner.position_seconds()>.45)
                        stopped,ended,painted_stop=space()
                        assert not app.preview_playing and app.play_button.cget("text")=="Play"
                        assert owner.player.poll() is not None and all(not t.is_alive() for t in owner._threads)
                        assert not owner.spectrum._thread.is_alive() and not owner.eq_controller._thread.is_alive()
                        rows.append({"play_handler_ms":(returned-start)*1000,"play_paint_ms":(painted-start)*1000,
                                     "pcm_observed_ms":(ready-start)*1000,"clock_observed_ms":(clock-start)*1000,
                                     "stop_handler_ms":(ended-stopped)*1000,"stop_paint_ms":(painted_stop-stopped)*1000})
                    medians={key:statistics.median(row[key] for row in rows) for key in rows[0]}
                    result["runs"].append({"mix_inputs":inputs,"cycles":rows,"median_ms":medians})
                    # This is a regression bound, not a device latency guarantee.
                    assert medians["play_paint_ms"]<180 and medians["stop_paint_ms"]<80,medians
                app.playback_cursor_manual=False
                app.event_generate("<KeyPress-space>");owner=app.realtime_processes
                for _ in range(20):app.event_generate("<KeyPress-space>")
                assert app.preview_playing and app.realtime_processes is owner
                app.event_generate("<KeyRelease-space>");space()
                assert not app.preview_playing and not errors
                result["held_space_toggles_once"]=True
                app.on_close();app=None
            result["clean_shutdown"]=True;result["status"]="passed"
    except Exception as exc:
        result["status"]="failed";result["error"]=repr(exc)
    finally:
        if app is not None:
            try:app.on_close()
            except Exception:pass
        if previous_driver is None:os.environ.pop("SDL_AUDIODRIVER",None)
        else:os.environ["SDL_AUDIODRIVER"]=previous_driver
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
