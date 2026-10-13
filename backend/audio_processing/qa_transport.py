"""Opt-in real-Tk transport check through a muted Windows output device."""
import json
from contextlib import ExitStack
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
    output=Path(output).resolve();assets=AppPaths.from_runtime();app=None;manager=None
    previous_driver=os.environ.get("SDL_AUDIODRIVER");os.environ["SDL_AUDIODRIVER"]="dummy"
    result={"frozen":bool(getattr(sys,"frozen",False)),
            "method":"real Tk Space events, muted WinMM device and native playback clock",
            "physical_key_to_speaker_measured":False,"runs":[]}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-transport-qa-") as folder, ExitStack() as cleanup:
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
                app=app_type();manager=app._warm_transport;errors=[]
                cleanup.callback(manager.close)
                cleanup.callback(app.on_close)
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
                def prepared():
                    cached=manager._cached
                    return (cached and cached[0]==app._prepared_request()
                            and cached[1].player.queued_seconds>.08)
                app.load_audio_path(source);pump(lambda:not app.busy)
                app.loop_var.set(False);app.fade_in_var.set(0);app.fade_out_var.set(0)
                app.limiter_enabled_var.set(False);app.focus_force();app.update()
                device=None
                for inputs in (1,4):
                    if inputs==4:
                        for name in ("vocals","drums","bass","other"):
                            path=paths.root/(name+".wav");shutil.copy2(app.source_wav,path)
                            app.stem_paths[name]=path
                        app.stem_range=(0,app.duration_seconds);app._refresh_action_states();app.update()
                    app.playback_cursor_manual=False
                    pump(prepared)
                    if device is None:device=manager.device;result["device_handle"]=device.handle
                    rows=[];owner=manager._cached[1];decoder=owner.decoder
                    for _ in range(6):
                        clock=owner.position_seconds();queued=owner.player.queued_seconds
                        start,returned,painted=space()
                        assert app.preview_playing and app.realtime_processes is owner
                        assert app.play_button.cget("text")=="Pause"
                        advanced=pump(lambda:owner.position_seconds()>clock+.003)
                        pump(lambda:owner.position_seconds()>clock+.25)
                        stopped,ended,painted_stop=space()
                        assert not app.preview_playing and app.play_button.cget("text")=="Play"
                        paused=owner.position_seconds();cursor=app.playback_position_var.get()
                        pump(lambda:time.perf_counter()>ended+.08)
                        assert owner.position_seconds()==paused and app.playback_position_var.get()==cursor
                        assert owner.player.paused and owner.player.poll() is None
                        assert owner.decoder is decoder and decoder.poll() is None
                        assert manager.device is device and device.handle==result["device_handle"]
                        assert manager._cached[1] is owner
                        rows.append({"play_handler_ms":(returned-start)*1000,
                                     "play_paint_ms":(painted-start)*1000,
                                     "device_advance_ms":(advanced-start)*1000,
                                     "queued_before_ms":queued*1000,
                                     "pause_handler_ms":(ended-stopped)*1000,
                                     "pause_paint_ms":(painted_stop-stopped)*1000})
                    medians={key:statistics.median(row[key] for row in rows) for key in rows[0]}
                    maximums={key:max(row[key] for row in rows) for key in rows[0]}
                    result["runs"].append({"mix_inputs":inputs,"cycles":rows,"median_ms":medians,
                                           "maximum_ms":maximums,"same_decoder_throughout":True})
                    assert medians["play_paint_ms"]<80 and medians["pause_paint_ms"]<80,medians
                    assert medians["device_advance_ms"]<100,medians
                    app.stop_preview(False);manager.cancel(wait=True)
                    assert all(not t.is_alive() for t in owner._threads)
                    assert not owner.spectrum._thread.is_alive() and not owner.eq_controller._thread.is_alive()
                pump(prepared)
                app.event_generate("<KeyPress-space>");owner=app.realtime_processes
                for _ in range(20):app.event_generate("<KeyPress-space>")
                assert app.preview_playing and app.realtime_processes is owner
                app.event_generate("<KeyRelease-space>");space()
                assert not app.preview_playing and not errors
                result["held_space_toggles_once"]=True
                result["single_device_for_all_sessions"]=True
                app.on_close();app=None;manager.close()
                assert not manager._thread.is_alive() and device._closed
            result["clean_shutdown"]=True;result["status"]="passed"
    except Exception as exc:
        result["status"]="failed";result["error"]=repr(exc)
    finally:
        if app is not None:
            try:app.on_close()
            except Exception:pass
        if manager is not None:manager.close()
        if previous_driver is None:os.environ.pop("SDL_AUDIODRIVER",None)
        else:os.environ["SDL_AUDIODRIVER"]=previous_driver
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
