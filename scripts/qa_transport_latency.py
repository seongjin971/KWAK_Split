"""Measure the legacy FFplay fallback; --qa-transport checks prepared native output."""
import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_workspace import WorkspaceTests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--cycles",type=int,default=6)
    parser.add_argument("--stems",action="store_true")
    args=parser.parse_args()
    os.environ["SDL_AUDIODRIVER"]="dummy"
    case=WorkspaceTests();case.setUp();app=case.app
    app._warm_transport.close()
    app._warm_transport.unavailable="legacy FFplay baseline measurement"
    result={"method":"real Tk Space events, generated audio, SDL dummy; output readiness observed by UI",
            "mix_inputs":4 if args.stems else 1,
            "physical_key_to_speaker_measured":False,"cycles":[]}
    spans={}
    def wrap(name):
        original=getattr(app,name)
        def measured(*a,**kw):
            start=time.perf_counter()
            try:return original(*a,**kw)
            finally:spans.setdefault(name,[]).append((time.perf_counter()-start)*1000)
        return measured
    def pump_until(predicate,timeout=5):
        deadline=time.perf_counter()+timeout
        while time.perf_counter()<deadline:
            app.update()
            if predicate():return time.perf_counter()
            time.sleep(.002)
        raise AssertionError("Transport latency check timed out")
    def press():
        began=time.perf_counter()
        app.event_generate("<KeyPress-space>")
        app.event_generate("<KeyRelease-space>")
        returned=time.perf_counter()
        app.update_idletasks()
        return began,returned,time.perf_counter()
    patches=[]
    try:
        app.loop_var.set(False);app.fade_in_var.set(0);app.fade_out_var.set(0)
        if args.stems:
            for name in ("vocals","drums","bass","other"):
                path=case.paths.root/(name+".wav");shutil.copy2(app.source_wav,path)
                app.stem_paths[name]=path
            app.stem_range=(0,app.duration_seconds);app._refresh_action_states()
        app.limiter_enabled_var.set(False);app.focus_force();app.update()
        for name in ("_stop_realtime_playback","_refresh_action_states","_build_audio_effects","_start_preview"):
            patches.append(patch.object(app,name,wrap(name)));patches[-1].start()
        for index in range(args.cycles):
            app.playback_cursor_manual=False
            spans.clear();start,returned,painted=press()
            assert app.preview_playing
            owner=app.realtime_processes
            pcm=pump_until(lambda:owner._sent_frames>0)
            clock=pump_until(lambda:owner._clock is not None and owner._clock[0]>0)
            row={"play_handler_ms":(returned-start)*1000,"play_paint_ms":(painted-start)*1000,
                 "first_pcm_ms":(pcm-start)*1000,"first_positive_clock_ms":(clock-start)*1000,
                 "play_spans_ms":dict(spans)}
            pump_until(lambda:owner.position_seconds()>.45)
            spans.clear();stopped,returned,painted=press()
            assert not app.preview_playing
            row.update(stop_handler_ms=(returned-stopped)*1000,stop_paint_ms=(painted-stopped)*1000,
                       stop_spans_ms=dict(spans),player_exited=owner.player.poll() is not None)
            result["cycles"].append(row)
        keys=("play_handler_ms","play_paint_ms","first_pcm_ms","first_positive_clock_ms",
              "stop_handler_ms","stop_paint_ms")
        result["median_ms"]={key:statistics.median(row[key] for row in result["cycles"]) for key in keys}
        result["maximum_ms"]={key:max(row[key] for row in result["cycles"]) for key in keys}
        assert not case.callback_errors
        result["status"]="passed"
    finally:
        for active in reversed(patches):active.stop()
        case.tearDown()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","median_ms","maximum_ms")},indent=2))


if __name__=="__main__":main()
