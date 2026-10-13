"""Opt-in current-display checks for numeric resets in source and frozen builds."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from backend.app_paths import AppPaths
from backend.project_store import EDIT_DEFAULTS


def check(app_type, output):
    output=Path(output).resolve();assets=AppPaths.from_runtime()
    result={"frozen":bool(getattr(sys,"frozen",False)),
            "method":"real Tk generated input events and generated audio",
            "display_scope":"current monitor and initial size only","cases":[]}
    try:
        with tempfile.TemporaryDirectory(prefix="kwak-numeric-reset-") as folder, ExitStack() as cleanup:
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
            errors=[]
            cleanup.enter_context(patch("tkinter.messagebox.showerror",side_effect=lambda *a,**k:errors.append(repr(a))))
            app=app_type();cleanup.callback(app._warm_transport.close);cleanup.callback(app.on_close)
            app.report_callback_exception=lambda *args:errors.append(repr(args))
            def pump(predicate=lambda:False,timeout=.05,required=False):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    app.update()
                    if predicate():return
                    time.sleep(.002)
                assert not required,"Numeric reset check timed out"
            app.load_audio_path(source);pump(lambda:not app.busy,15,True)
            assert not errors
            app.playback_cursor_seconds=2;app.playback_cursor_manual=True
            result.update(client=[app.winfo_width(),app.winfo_height()],ui_scale=app.ui_scale)
            stamp=100000
            for key,changed in (("eq_low_freq",1150),("eq_mid_freq",2400),("eq_high_freq",6000),
                                ("tempo_percent",162),("pitch_semitones",-4),("fade_in",.8),("fade_out",1.2)):
                variable=getattr(app,key+"_var")
                widget=next(w for w,_,v,_ in app._numeric_fields if v is variable)
                variable.set(changed);pump();app._commit_edit()
                before,index=app._edit_snapshot(),app.history.index
                x,y=min(12,widget.winfo_width()//2),widget.winfo_height()//2
                widget.event_generate("<ButtonPress-1>",x=x,y=y,state=12,time=stamp)
                pump();assert variable.get()==EDIT_DEFAULTS[key]
                # Ctrl released first: the held mouse must not scrub the reset value.
                widget.event_generate("<B1-Motion>",x=x,y=y-30,state=0x108,time=stamp+50)
                widget.event_generate("<ButtonRelease-1>",x=x,y=y-30,state=8,time=stamp+80)
                pump()
                expected=dict(before);expected[key]=EDIT_DEFAULTS[key]
                assert app._edit_snapshot()==expected,key
                assert app.history.index==index+1 and not app._history_dragging,key
                assert float(widget.get())==EDIT_DEFAULTS[key],key
                assert app.playback_cursor_seconds==2
                app.undo_edit();assert app._edit_snapshot()==before,key
                app.redo_edit();assert app._edit_snapshot()==expected,key
                result["cases"].append({"field":key,"before":changed,"default":variable.get(),
                    "display":widget.get(),"one_undo_and_redo":True,"no_follow_on_drag":True})
                stamp+=1000
            assert not errors
            result.update(status="passed",num_lock_enabled=True,callback_errors=errors,
                          generated_audio_only=True,range_and_cursor_preserved=True)
    except Exception as exc:
        result.update(status="failed",error=repr(exc))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
