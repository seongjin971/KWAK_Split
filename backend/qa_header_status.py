"""Opt-in isolated Tk checks for header feedback and fixed display geometry."""
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from backend.app_paths import AppPaths


def check(app_type, output, capture=None, *, current_display_only=False):
    output=Path(output).resolve();assets=AppPaths.from_runtime()
    result={"frozen":bool(getattr(sys,"frozen",False)),
            "method":"isolated real Tk, generated audio",
            "display_scope":"current monitor and initial size only" if current_display_only else "simulated display matrix",
            "physical_monitor_switch_tested":False,"cases":[]}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-header-qa-") as folder, ExitStack() as cleanup:
            class QAPaths(AppPaths):
                @property
                def bin(self):return assets.bin
                @property
                def backend(self):return assets.backend
                @property
                def models(self):return assets.models
            paths=QAPaths(Path(folder));paths.ensure();source=paths.root/"generated.wav"
            subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error","-f","lavfi","-i",
                "sine=frequency=440:duration=4:sample_rate=48000","-ac","2",str(source)],
                check=True,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
            cleanup.enter_context(patch.dict(os.environ,{"SDL_AUDIODRIVER":"dummy"}))
            cleanup.enter_context(patch.object(AppPaths,"from_runtime",return_value=paths))
            cleanup.enter_context(patch.object(app_type,"_configure_logging"))
            app=app_type(ui_scale=None if current_display_only else 1);manager=app._warm_transport
            cleanup.callback(manager.close);cleanup.callback(app.on_close)
            errors=[];app.report_callback_exception=lambda *args:errors.append(repr(args))
            def pump(predicate=lambda:False, timeout=.12, required=False):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    app.update()
                    if predicate():return
                    time.sleep(.002)
                assert not required,"Header check timed out"
            def geometry():
                widgets=(app.header,app.load_button,app.settings_button,app.render_button,
                         app.render_mp3_button,app.wave_canvas,app.eq_panel,app.mixer_panel)
                return tuple((w.winfo_rootx()-app.winfo_rootx(),w.winfo_rooty()-app.winfo_rooty(),
                              w.winfo_width(),w.winfo_height()) for w in widgets)
            def fits(busy):
                w,h=app.winfo_width(),app.winfo_height()
                assert w*7==h*10 and not app.workspace_scroll.bar.winfo_ismapped()
                for widget in (app.status_frame,app.status_label,app.load_button,app.render_mp3_button,
                               app.eq_editor,app.play_button,app.fade_out_spinbox,app.export_stems_button):
                    if not widget.winfo_ismapped():continue
                    assert widget.winfo_rootx()>=app.winfo_rootx()
                    assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+w+1
                    assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+h+1
                assert app.status_frame.master is app.header
                assert app.status_frame.winfo_rootx()>=app.brand.winfo_rootx()+app.brand.winfo_width()
                assert app.status_frame.winfo_rootx()+app.status_frame.winfo_width()<=app.load_button.winfo_rootx()
                assert app.status_frame.winfo_rooty()+app.status_frame.winfo_height()<=app.header.winfo_rooty()+app.header.winfo_height()
                if app.status_label.winfo_ismapped():
                    assert app.fonts["body"].measure(app.status_label.cget("text"))<=app.status_label.winfo_width()
                assert bool(app.cancel_button.winfo_ismapped())==busy
                if busy:
                    assert app.status_label.winfo_rootx()+app.status_label.winfo_width()<=app.cancel_button.winfo_rootx()
                    assert app.cancel_button.winfo_rootx()+app.cancel_button.winfo_width()<=app.load_button.winfo_rootx()
                gap=app.winfo_rooty()+h-app.mixer_panel.winfo_rooty()-app.mixer_panel.winfo_height()
                assert 0<=gap<=app.px(20),gap
                return {"client":[w,h],"status_width":app.status_frame.winfo_width(),"bottom_gap":gap}
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            def shot(name):
                if capture:
                    target=output.parent/"captures"/(name+".png");target.parent.mkdir(parents=True,exist_ok=True)
                    capture(app,target)
            def empty_status():
                assert app.status_label.winfo_ismapped()
                assert app.status_label.cget("text")==""
                assert app.status_label.cget("background")==app.header.cget("background")
                assert app.status_label.cget("cursor")=="arrow"
                assert not int(app.status_label.cget("takefocus"))
                with patch("tkinter.messagebox.showinfo") as dialog:
                    app.status_label.event_generate("<Button-1>")
                    dialog.assert_not_called()
            pump()
            empty_status();shot("startup")
            result["empty_startup_status_painted"]=True
            app.load_audio_path(source);pump(lambda:not app.busy,15,True)
            assert not errors
            app.render_wav();pump(lambda:not app.busy,15,True)
            assert app.result_files and app.result_files[0].is_file()
            saved_file=app.result_files[0]
            assert not any(w.winfo_class()=="TProgressbar" for w in descendants(app))
            details="Cannot save audio to C:/QA/"+"very-long-folder-name/"*20+"mix.wav\nAccess denied."
            edits=app._edit_snapshot()
            screens=(("current",None),) if current_display_only else (("fhd",(1920,1080)),("qhd",(2560,1440)),("4k",(3840,2160)))
            for screen_name,screen in screens:
                for scale in ((app.ui_scale,) if current_display_only else (1,1.25,1.5,1.75,2)):
                    if not current_display_only:
                        app._ui_scale_override=scale;app._display_scale=scale
                    display_context=nullcontext() if current_display_only else patch("backend.compact_ui.display_metrics",return_value=((0,0,screen[0],screen[1]-40),scale))
                    with display_context:
                        if not current_display_only:app._set_initial_compact_window()
                        pump()
                        sizes=(("initial",None),) if current_display_only else (("initial",app._fixed_limits.initial_size),("minimum",app.minsize()),("maximum",app.maxsize()))
                        for size_name,size in sizes:
                            if size is not None:app._window_constraints.resize(*size,position=(24,24))
                            app.status_var.set("");pump();baseline=geometry();idle=fits(False)
                            empty_status()
                            take_shot=current_display_only or (screen_name=="fhd" and scale==1 and size_name!="maximum")
                            if take_shot:shot("idle-"+size_name)
                            app._set_busy(True,"Stem Split");app.cancel_event=threading.Event();pump()
                            assert "%" not in app.status_label.cget("text")
                            assert geometry()==baseline;fits(True)
                            app._handle_worker_message("status","Separating stems with a very long phase description "*10)
                            app._handle_worker_message("progress",42);pump()
                            assert app.status_label.cget("text").endswith(" 42%")
                            assert geometry()==baseline;fits(True)
                            if take_shot:shot("progress-"+size_name)
                            app.cancel_button.event_generate("<Button-1>");pump()
                            assert app.cancel_event.is_set() and not app.cancel_button.enabled
                            app._handle_worker_message("cancelled","QA cancellation")
                            app._handle_worker_message("done",None);pump()
                            assert geometry()==baseline;fits(False)
                            app._show_results([saved_file]);pump()
                            with patch.object(app,"open_result_folder") as opened:
                                app.status_label.event_generate("<Button-1>");opened.assert_called_once()
                            assert geometry()==baseline;fits(False)
                            if take_shot:shot("saved-"+size_name)
                            app._set_busy(True,"Render")
                            with patch("tkinter.messagebox.showerror"),patch.object(app,"set_log_visible"):
                                app._handle_worker_message("error",details)
                            app._handle_worker_message("done",None);pump()
                            assert geometry()==baseline;fits(False)
                            assert app.status_var.get()=="Error: "+details
                            with patch("tkinter.messagebox.showinfo") as dialog,patch.object(app,"open_result_folder") as opened:
                                app.status_label.event_generate("<Button-1>")
                                assert dialog.call_args.args[1]=="Error: "+details
                                opened.assert_not_called()
                            if take_shot:shot("error-"+size_name)
                            for message in ("Ready", "Playing: generated", "Playback stopped.", ""):
                                app.status_var.set(message);pump();empty_status()
                                assert geometry()==baseline
                            if take_shot:shot("idle-after-feedback-"+size_name)
                            assert not errors and app._edit_snapshot()==edits
                            result["cases"].append({"screen":screen_name,"dpi_scale":scale,"size":size_name,**idle,
                                                    "stable_states":6,"cancel_and_detail_actions":True})
            result.update(status="passed",no_progressbar=True,real_generated_audio_load_and_export=True,
                          edits_preserved=True,callback_errors=errors)
    except Exception as exc:
        result.update(status="failed",error=repr(exc))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
