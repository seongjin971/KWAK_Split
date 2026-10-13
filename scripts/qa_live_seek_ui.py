"""Visible source Tk checks using generated waveform gestures and isolated audio."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from PIL import ImageGrab
from test_workspace import WorkspaceTests
from test_spectrum_ui import current_frame,pump_until
from test_live_seek_ui import click,pump


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args=parser.parse_args();evidence=args.evidence_dir.resolve()
    (evidence/"captures").mkdir(parents=True,exist_ok=True)
    os.environ["SDL_AUDIODRIVER"]="dummy"
    result={"method":"real source Tk; generated Tk gestures/audio; SDL dummy",
            "native_exe_mouse_input_tested":False,"native_listening_tested":False,"checks":[]}
    case=WorkspaceTests();case.setUp();app=case.app
    try:
        app.geometry("1000x700");app.loop_var.set(False)
        app.fade_in_var.set(0);app.fade_out_var.set(0);app.limiter_enabled_var.set(False)
        app.eq_mid_freq_var.set(440);app.update()
        def capture(name):
            app.update();ImageGrab.grab(window=int(app.frame(),0)).save(evidence/"captures"/(name+".png"))
        app.toggle_playback();current_frame(app);owner=app.realtime_processes;player=owner.player
        target=click(app,3.2)
        pump_until(app,lambda:app.playback_start_seconds==target);capture("after-click")
        canvas=app.wave_canvas;width=canvas.winfo_width();before=owner.applied_seek_revision;dispatch=[]
        canvas.event_generate("<Button-1>",x=round(width*.15),y=40)
        for step in range(24):
            x=round(width*(.15+.023*step));began=time.perf_counter()
            canvas.event_generate("<B1-Motion>",x=x,y=40)
            dispatch.append(time.perf_counter()-began);pump(app,.045)
        assert app.playback_seek_dragging and owner.applied_seek_revision>before+2
        capture("during-held-drag")
        result["held_drag_applied_revision"]=owner.applied_seek_revision
        canvas.event_generate("<ButtonRelease-1>",x=x,y=40)
        pump_until(app,lambda:not owner.playback_position().seeking)
        assert app.realtime_processes is owner and owner.player is player and player.poll() is None
        result["maximum_motion_callback_ms"]=max(dispatch)*1000
        assert result["maximum_motion_callback_ms"]<100
        result["checks"].append("Click and held left drag keep the player and apply before release")
        app.stop_preview(False)
        app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
        app.stem_range=(0,app.duration_seconds);app.playback_cursor_manual=False
        app.stem_vars["vocals"]["solo"].set(True);app.stem_vars["vocals"]["volume"].set(50)
        app.eq_mid_var.set(-6);app._refresh_action_states();app.toggle_playback()
        flat=max(current_frame(app).levels);owner=app.realtime_processes
        target=click(app,3.2);pump_until(app,lambda:app.playback_start_seconds==target)
        pump_until(app,lambda:(f:=owner.spectrum_frame()) and abs(max(f.levels)-flat)<.25)
        assert owner.eq_controller._mixer_desired==(.5,0,0,0)
        assert owner.eq_controller._desired[("equalizer@kw_mid","g")]==-6
        capture("mix-eq-after-seek")
        result["checks"].append("Four-stem Solo/gain and EQ survive the seek")
        app.stop_preview(False);target=click(app,2)
        assert not app.preview_playing and app.playback_position_var.get()==target
        assert not case.callback_errors
        result["checks"].append("Paused seek stays paused; cleanup releases playback")
        result["status"]="passed"
    except Exception as exc:
        result["status"]="failed";result["error"]=repr(exc)
        raise
    finally:
        case.tearDown()
        (evidence/"ui-checks.json").write_text(json.dumps(result,indent=2),encoding="utf-8")


if __name__=="__main__":main()
