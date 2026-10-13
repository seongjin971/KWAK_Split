"""Opt-in resize checks in an isolated editor with generated, muted audio."""
from contextlib import ExitStack
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from PIL import Image, ImageChops, ImageGrab

from backend.app_paths import AppPaths


def check(app_type, output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    assets=AppPaths.from_runtime()
    result={"frozen":bool(getattr(sys,"frozen",False)),
            "method":"real Tk, generated sizing and native modal loop, muted generated audio",
            "physical_drag_tested":False,"runs":[],"modal":[]}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-resize-qa-") as folder, ExitStack() as cleanup:
            class QAPaths(AppPaths):
                @property
                def bin(self):return assets.bin
                @property
                def backend(self):return assets.backend
                @property
                def models(self):return assets.models
            paths=QAPaths(Path(folder));paths.ensure();source=paths.root/"generated.wav"
            subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error","-f","lavfi","-i",
                "sine=frequency=440:duration=20:sample_rate=48000","-ac","2",str(source)],
                check=True,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
            cleanup.enter_context(patch.dict(os.environ,{"SDL_AUDIODRIVER":"dummy"}))
            cleanup.enter_context(patch.object(AppPaths,"from_runtime",return_value=paths))
            cleanup.enter_context(patch.object(app_type,"_configure_logging"))
            app=app_type(ui_scale=1);manager=app._warm_transport
            cleanup.callback(manager.close);cleanup.callback(app.on_close)
            errors=[];app.report_callback_exception=lambda *args:errors.append(repr(args))
            native=app._window_constraints;preview=app._resize_preview

            def pump(predicate,timeout=5):
                deadline=time.perf_counter()+timeout
                while time.perf_counter()<deadline:
                    app.update()
                    if predicate():return
                    time.sleep(.001)
                raise AssertionError("Resize check timed out")

            def visible():
                width,height=app.winfo_width(),app.winfo_height()
                assert width*7==height*10 and not app.workspace_scroll.bar.winfo_ismapped()
                assert app.editor_surface.winfo_ismapped() and not preview.canvas.winfo_ismapped()
                assert app.ui_scale==width/1000
                for widget in (app.load_button,app.render_mp3_button,app.play_button,
                               app.eq_editor,app.fade_out_spinbox,*app.stem_widgets["other"]):
                    assert widget.winfo_ismapped()
                    assert widget.winfo_rootx()>=app.winfo_rootx()
                    assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+width+1
                    assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+height+1
                assert not errors,errors

            def begin():
                start=time.perf_counter();native.begin_size_move()
                elapsed=(time.perf_counter()-start)*1000
                assert native.resize_frame is not None
                native.interactive_resize=True
                return elapsed

            def step(units):
                size=app._fixed_limits.size(units);start=time.perf_counter()
                native.resize(*size,position=(24,24))
                pump(lambda:preview.last_size==size)
                assert preview.active and preview.canvas.winfo_ismapped()
                assert not app.editor_surface.winfo_ismapped()
                return (time.perf_counter()-start)*1000

            def finish():
                start=time.perf_counter();native.end_size_move()
                pump(lambda:not preview.active and preview.finish_after is None)
                visible()
                return (time.perf_counter()-start)*1000

            native.resize(1000,700,position=(24,24));app.update();visible()
            begin();step(76);finish()  # Empty project.
            app.load_audio_path(source);pump(lambda:not app.busy)
            app.loop_var.set(False);app.fade_in_var.set(0);app.fade_out_var.set(0)
            app.limiter_enabled_var.set(False)
            native.resize(1000,700,position=(24,24));app.update()
            expected=ImageGrab.grab(window=int(app.editor_surface.winfo_id())).convert("RGB")
            begin();size,data=native.resize_frame
            copied=Image.frombytes("RGB",size,data,"raw","BGRX")
            assert ImageChops.difference(expected,copied).getbbox() is None,"Incomplete editor snapshot"
            step(76)
            ImageGrab.grab(window=int(app.winfo_id())).save(output.with_name(output.stem+"-preview.png"))
            finish()
            ImageGrab.grab(window=int(app.winfo_id())).save(output.with_name(output.stem+"-restored.png"))
            result["complete_snapshot_pixel_match"]=True

            for mix_inputs in (1,4):
                if mix_inputs==4:
                    app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
                    app.stem_range=(0,app.duration_seconds);app._refresh_action_states()
                app.playback_cursor_manual=False;app.toggle_playback()
                pump(lambda:bool(app.realtime_processes) and app.realtime_processes.position_seconds()>.1)
                owner=app.realtime_processes;device=manager.device;clock=owner.position_seconds()
                edits=app._edit_snapshot();capture_ms=begin()
                rows=[step(n) for n in (*range(78,121,2),*range(118,75,-2))]
                advanced=owner.position_seconds()-clock
                assert advanced>.3 and app.preview_playing and app.realtime_processes is owner
                assert manager.device is device and not owner.player.paused
                commit_ms=finish()
                assert app.realtime_processes is owner and app._edit_snapshot()==edits
                result["runs"].append({"mix_inputs":mix_inputs,"frames":len(rows),
                    "median_ms":statistics.median(rows),"p95_ms":sorted(rows)[int(.95*(len(rows)-1))],
                    "max_ms":max(rows),"capture_ms":capture_ms,"commit_ms":commit_ms,
                    "audio_clock_advance_seconds":advanced,"same_audio_stream":True})
                app.focus_force();app.update()
                app.event_generate("<KeyPress-space>");app.event_generate("<KeyRelease-space>");app.update()
                assert not app.preview_playing and owner.player.paused
                app.stop_preview(False);manager.cancel(wait=True)

            # Capture/allocation failures retain a usable editor.
            with patch("backend.window_bounds.capture_client",return_value=None):
                native.begin_size_move();native.interactive_resize=True
                native.resize(1000,700,position=(24,24));app.update()
                assert not preview.active;visible();native.end_size_move()
            begin()
            with patch("backend.resize_preview.Image.frombytes",side_effect=OSError("injected allocation failure")):
                native.resize(800,560,position=(24,24));app.update()
                pump(lambda:not preview.active and preview.finish_after is None)
            native.end_size_move();visible()
            result["capture_and_image_failure_fallback"]=True

            # New status/edit values must be visible after the frozen preview ends.
            begin();step(90);app._set_busy(True,"Render");app.status_var.set("Rendering audio")
            app._handle_worker_message("progress",42);app.update();finish()
            assert app.cancel_button.winfo_ismapped() and app.status_label.cget("text").endswith(" 42%")
            app._set_busy(False);app.status_var.set("");app.update()
            result["status_updated_after_resize"]=True

            # Same sizing path at simulated display/DPI limits, including a
            # screen too small to offer any range at a large UI scale.
            result["display_cases"]=[]
            for name,(width,height) in (("fhd",(1920,1040)),("qhd",(2560,1400)),("4k",(3840,2120))):
                for scale in (1,1.25,1.5,1.75,2):
                    app._ui_scale_override=scale
                    with patch("backend.compact_ui.display_metrics",return_value=((0,0,width,height),scale)):
                        app._set_initial_compact_window();app.update();limits=app._fixed_limits
                        row={"screen":name,"dpi_scale":scale,"min":limits.minsize,"max":limits.maxsize}
                        if limits.minimum==limits.maximum:
                            row["fixed_at_screen_limit"]=True;visible()
                        else:
                            begin();frames=[]
                            for units in (limits.minimum,limits.maximum):
                                if limits.size(units)!=(app.winfo_width(),app.winfo_height()):frames.append(step(units))
                            row["frame_ms"]=frames;row["commit_ms"]=finish()
                        result["display_cases"].append(row)
            app._ui_scale_override=1;app._set_initial_compact_window();app.update();visible()

            # Repeated capture must not retain per-drag Windows GDI resources.
            api=ctypes.windll.user32
            api.GetGuiResources.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            before=api.GetGuiResources(wintypes.HANDLE(-1),0)
            for _ in range(20):
                native.begin_size_move();assert native.resize_frame is not None;native.end_size_move()
            after=api.GetGuiResources(wintypes.HANDLE(-1),0)
            assert before==after,(before,after)
            result["capture_gdi_resources"]={"before":before,"after":after,"captures":20}

            # Exercise actual modal entry/exit. Never inject bare ENTER/EXITSIZEMOVE.
            api=ctypes.windll.user32
            api.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            api.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            api.SendMessageW.restype=ctypes.c_ssize_t
            for ending in (0x0d,0x1b):  # Enter accepts; Escape cancels.
                record={"ending":"Enter" if ending==0x0d else "Escape","steps":[]}
                cursor=wintypes.POINT();api.GetCursorPos(ctypes.byref(cursor))
                native.resize(1000,700,position=(24,24));app.update()
                def drive():
                    try:
                        deadline=time.perf_counter()+4
                        while not native.in_size_move and time.perf_counter()<deadline:time.sleep(.002)
                        assert native.in_size_move,"Native modal sizing did not start"
                        for width in (900,800,1100,1200):
                            dw,dh=native.decoration
                            rect=wintypes.RECT(24,24,24+width+dw,24+width*7//10+dh)
                            api.SendMessageW(wintypes.HWND(native.hwnd),0x214,8,ctypes.addressof(rect))
                            native.resize(width,width*7//10,position=(24,24))
                            deadline=time.perf_counter()+2
                            while preview.last_size!=(width,width*7//10) and time.perf_counter()<deadline:time.sleep(.002)
                            assert preview.active and preview.last_size==(width,width*7//10)
                            record["steps"].append(list(preview.last_size))
                    except Exception as exc:record["error"]=repr(exc)
                    finally:
                        record["finished"]=True
                        api.PostMessageW(wintypes.HWND(native.hwnd),0x100,ending,0)
                helper=threading.Thread(target=drive,daemon=True);helper.start()
                app.after(20,lambda:api.PostMessageW(wintypes.HWND(native.hwnd),0x112,0xf008,0))
                deadline=time.perf_counter()+12
                def settled():
                    if record.get("finished") and not native.in_size_move and not preview.active and not preview.finish_after:
                        app.quit()
                    elif time.perf_counter()>deadline:
                        record["error"]="Modal check timed out";app.quit()
                    else:app.after(10,settled)
                app.after(30,settled)
                try:app.mainloop();helper.join(2)
                finally:api.SetCursorPos(cursor.x,cursor.y)
                app.update();visible();assert "error" not in record,record
                assert not native.in_size_move and len(record["steps"])==4
                result["modal"].append(record)

            # Close with a queued preview frame; all callbacks/images must release.
            begin();step(90);preview.request();app.on_close();manager.close()
            assert not preview.active and preview.photo is None and preview.snapshot is None
            assert preview.frame_after is preview.watch_after is preview.finish_after is None
            assert native.hwnd==0 and native.resize_frame is None
            result.update(status="passed",clean_shutdown=True,callback_errors=errors)
    except Exception as exc:
        result.update(status="failed",error=repr(exc))
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
