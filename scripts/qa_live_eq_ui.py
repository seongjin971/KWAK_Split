"""Generated real-Tk drag/reset checks with a silent player and isolated audio."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from PIL import ImageGrab
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import require_ffmpeg
from backend.audio_processing.spectrum import FLOOR_DB
from test_spectrum_ui import current_frame, pump_until
from test_workspace import WorkspaceTests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    parser.add_argument("--release",type=Path)
    parser.add_argument("--mixer",action="store_true")
    args=parser.parse_args()
    evidence=args.evidence_dir.resolve();(evidence/"captures").mkdir(parents=True,exist_ok=True)
    os.environ["SDL_AUDIODRIVER"]="dummy"
    result={"method":"real source Tk, generated events/audio, silent FFplay",
            "native_exe_input_tested":False,"checks":[]}
    case=WorkspaceTests();case.setUp();app=case.app
    try:
        if args.release:
            release=args.release.resolve()
            class Assets(AppPaths):
                @property
                def bin(self):return release/"bin"
            app.paths=Assets(case.paths.root)
            result["bundled_engines"]=str(release)
        source=case.paths.root/"Generated continuous EQ check.wav"
        subprocess.run([str(require_ffmpeg(app.paths)),"-v","error","-f","lavfi","-i",
            "aevalsrc=.04*sin(2*PI*1000*t)|.04*sin(2*PI*1000*t):s=44100:d=40",
            "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        app.load_audio_path(source);case.wait_idle()
        app.loop_var.set(False);app.fade_in_var.set(0);app.fade_out_var.set(0)
        app.limiter_enabled_var.set(False);app.eq_mid_freq_var.set(1000)
        app.geometry("1000x700");app.update()

        def pump(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end:app.update();time.sleep(.005)
        def capture(name):
            app.update()
            ImageGrab.grab(window=int(app.frame(),0)).save(evidence/"captures"/(name+".png"))
        def level_near(expected):
            def ready():
                frame=app.eq_editor._spectrum_frame
                return frame if frame and abs(max(frame.levels)-expected)<.3 else None
            return pump_until(app,ready)

        app.toggle_playback();flat=max(current_frame(app).levels)
        capture("source-flat")
        owner=app.realtime_processes;graph=app.eq_editor
        x,y=graph.handles["mid"]
        graph.event_generate("<ButtonPress-1>",x=round(x),y=round(y))
        for step in range(1,31):
            x,y=graph.xy(1000,step/5)
            graph.event_generate("<B1-Motion>",x=round(x),y=round(y))
            pump(.022)
            assert app.realtime_processes is owner and not app.live_restart_after_id
        assert graph.drag_band=="mid" and owner.eq_controller.revision>=10
        assert owner.eq_controller._current[("equalizer@kw_mid","g")]>0
        result["checks"].append("EQ applied during held drag; same player/decoder")
        graph.event_generate("<ButtonRelease-1>",x=round(x),y=round(y))
        level_near(flat+app.eq_mid_var.get());capture("source-after-drag")
        # Exercise the actual graph's existing double-click reset callback.
        graph.reset(type("Point",(),{"x":x,"y":y})())
        level_near(flat)
        assert app.realtime_processes is owner
        result["checks"].append("Graph reset returns to unity without restart")
        app.stop_preview(False)

        app.eq_low_shape_var.set("High Pass");app.high_pass_slope_var.set(24)
        app.eq_low_freq_var.set(100);app.playback_cursor_manual=False
        app.toggle_playback();current_frame(app);owner=app.realtime_processes
        x,y=graph.handles["low"]
        graph.event_generate("<ButtonPress-1>",x=round(x),y=round(y))
        for frequency in (150,200,300,400):
            nx,_=graph.xy(frequency,0)
            graph.event_generate("<B1-Motion>",x=round(nx),y=round(y));pump(.06)
        graph.event_generate("<ButtonRelease-1>",x=round(nx),y=round(y));pump(.15)
        assert app.realtime_processes is owner and app.high_pass_slope_var.get()==24
        result["checks"].append("Pass cutoff drag keeps playback and slope")
        capture("pass-cutoff")

        def settled_change(action):
            previous=owner.eq_controller.revision
            action()
            pump_until(app,lambda:owner.eq_controller.revision>previous
                       and owner.eq_controller.applied_revision==owner.eq_controller.revision)
            assert app.realtime_processes is owner and not app.live_restart_after_id
            assert all(p.poll() is None for p in owner) and not owner.eq_controller.error
        def select(combo,mode):
            combo.set(mode);combo.event_generate("<<ComboboxSelected>>")
        for band,index,shelf,mode in (("low",0,"Low Shelf","High Pass"),
                                     ("high",1,"High Shelf","Low Pass")):
            combo=app.eq_shape_widgets[index];knob=app.compact_knobs[band]
            if combo.get()!=shelf:settled_change(lambda:select(combo,shelf))
            settled_change(lambda:select(combo,mode))
            for delta,expected in ((120,36),(120,48),(-120,36),(-120,24),(-120,12)):
                settled_change(lambda:knob.event_generate("<MouseWheel>",delta=delta))
                assert app._band_value(band)==expected
            capture(band+"-pass-12-continuous")
            def reset():
                knob.event_generate("<Button-1>",state=0x4,x=10,y=10)
                knob.event_generate("<ButtonRelease-1>",state=0x4,x=10,y=10)
            settled_change(reset)
            assert app._band_value(band)==24
            capture(band+"-pass-ctrl-reset")
            settled_change(lambda:select(combo,shelf))
            result["checks"].append(band+" mode menu, 12/24/36/48 slopes and Ctrl+click retain player/decoder")
        app.stop_preview(False)

        app.eq_low_shape_var.set("Low Shelf");app.eq_low_var.set(0)
        app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
        app.stem_range=(0,app.duration_seconds)
        for values in app.stem_vars.values():values["volume"].set(25)
        app._refresh_action_states();app.playback_cursor_manual=False;app.toggle_playback()
        flat=max(current_frame(app).levels);owner=app.realtime_processes
        app.eq_mid_var.set(-9);level_near(flat-9)
        assert app.realtime_processes is owner
        capture("four-stems-cut")
        result["checks"].append("Four-stem mix EQ changes without restarting playback")
        if args.mixer:
            app.eq_mid_var.set(0);level_near(flat)
            def settled_mix():
                gains=tuple(round(s.gain,6) for s in app._build_mix_stems(include_silent=True))
                pump_until(app,lambda:owner.eq_controller._mixer_current==gains
                           and owner.eq_controller.mixer_applied_revision==owner.eq_controller.mixer_revision)
                level_near(flat+20*math.log10(sum(gains)) if sum(gains) else FLOOR_DB)
                assert app.realtime_processes is owner and not app.live_restart_after_id
                assert not owner.eq_controller.error and all(p.poll() is None for p in owner)
            for name in app.stem_vars:
                fader=app.stem_widgets[name][0]
                x,y=fader.winfo_width()//2,round(fader.winfo_height()*.45)
                before=owner.eq_controller.mixer_revision
                fader.event_generate("<ButtonPress-1>",x=x,y=y)
                for i in range(16):
                    fader.event_generate("<B1-Motion>",x=x,y=y+i*3);pump(.025)
                    assert app.realtime_processes is owner and not app.live_restart_after_id
                assert fader.dragging and owner.eq_controller.mixer_revision>=before+10
                capture(name+"-held-fader")
                fader.event_generate("<ButtonRelease-1>",x=x,y=y+45)
                readout=next(w for w in fader.master.winfo_children() if w.winfo_class()=="Label"
                             and str(w.cget("textvariable"))==str(app.stem_volume_label_vars[name]))
                for widget in (fader,readout):
                    app.stem_vars[name]["volume"].set(45);pump(.025)
                    widget.event_generate("<ButtonPress-1>",state=4,x=10,y=10)
                    widget.event_generate("<ButtonRelease-1>",state=4,x=10,y=10)
                    settled_mix()
                    assert app.stem_vars[name]["volume"].get()==100
                result["checks"].append(name+" held fader and both Ctrl+click targets apply without restart")
            for name in app.stem_vars:
                app.stem_widgets[name][1].invoke()
            settled_mix();clock=owner.position_seconds();pump(.2)
            assert owner.position_seconds()>clock
            capture("mixer-all-muted")
            app.stem_widgets["vocals"][2].invoke();settled_mix()
            assert max(app.eq_editor._spectrum_frame.levels)<=FLOOR_DB+.3
            app.stem_widgets["vocals"][1].invoke();settled_mix()
            capture("mixer-solo-unmuted")
            result["checks"].append("All Mute retains transport; muted Solo stays silent; unmute resumes in sync")
        assert not case.callback_errors
        result["callback_errors"]=0
        result["status"]="passed"
    finally:case.tearDown()
    (evidence/"ui-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
