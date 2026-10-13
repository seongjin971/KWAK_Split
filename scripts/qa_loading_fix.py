"""Measure real load completion and idle UI state without modifying the input."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_workspace import WorkspaceTests


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--audio",type=Path,required=True)
    args=parser.parse_args();case=WorkspaceTests();case.ui_scale=None;case.setUp()
    try:
        app=case.app;started=time.perf_counter();app.load_audio_path(args.audio)
        case.wait_idle(30);loaded=time.perf_counter()-started
        assert app.play_button.enabled and app.render_button.enabled and app.separate_button.enabled
        assert not app.cancel_button.winfo_ismapped()
        assert not app.stem_paths
        cpu_start=time.process_time();until=time.monotonic()+1.5
        while time.monotonic()<until:app.update();time.sleep(.01)
        idle_cpu=time.process_time()-cpu_start
        assert not case.callback_errors,case.callback_errors
        result={"input":"reported local MP3; original retained",
            "duration_seconds":app.duration_seconds,"load_until_controls_ready_seconds":round(loaded,3),
            "selection_end_exact":app.selection_end_var.get(),"selection_end_display":app.end_spinbox.get(),
            "idle_cpu_seconds_over_1_5_seconds":round(idle_cpu,3),"automatic_dpi_scale":app.ui_scale,
            "controls_enabled":True,"loading_and_cancel_hidden":True,"automatic_split":False,
            "callback_errors":0}
        out=ROOT/"docs/qa/loading-fix";out.mkdir(parents=True,exist_ok=True)
        (out/"reported-file-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2),flush=True)
    finally:case.tearDown()


if __name__=="__main__":main()
