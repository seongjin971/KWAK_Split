"""Measure isolated Tk resize frames using generated audio and native messages."""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
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
    parser.add_argument("--profile",action="store_true")
    parser.add_argument("--interactive",action="store_true",help="Capture before sizing and time the transient preview")
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    case=WorkspaceTests();case.setUp();app=case.app;native=app._window_constraints
    result={"method":"generated native size messages and real Tk repaint; generated audio",
            "physical_drag_tested":False,"interactive_preview":args.interactive,"runs":[]}
    def frame(units):
        width,height=app._fixed_limits.size(units)
        began=time.perf_counter();native.resize(width,height,position=(24,24));app.update()
        deadline=began+2
        preview=app._resize_preview
        def pending():
            if args.interactive and native.in_size_move:return preview.last_size!=(width,height)
            return app._layout_after or abs(app.ui_scale-width/1000)>.002
        while pending():
            assert time.perf_counter()<deadline,"Resize failed to settle"
            time.sleep(.001);app.update()
        return (time.perf_counter()-began)*1000
    try:
        app.file_label_var.set("An example with a longer original audio file name for waveform editing.wav")
        for mode in ("loaded_flat","loaded_eq"):
            if mode=="loaded_eq":
                app.eq_low_shape_var.set("High Pass");app.eq_high_shape_var.set("Low Pass")
                app.high_pass_slope_var.set(48);app.low_pass_slope_var.set(48)
                app.eq_mid_var.set(6)
            app.update();frame(100)
            edits=app._edit_snapshot();rows=[]
            capture_ms=None
            if args.interactive:
                began=time.perf_counter();native.begin_size_move();capture_ms=(time.perf_counter()-began)*1000
                assert native.resize_frame is not None
                native.interactive_resize=True
            with patch.object(app,"draw_waveform",wraps=app.draw_waveform) as wave, \
                 patch.object(app.eq_editor,"draw",wraps=app.eq_editor.draw) as eq, \
                 patch.object(app,"_layout_compact",wraps=app._layout_compact) as layout, \
                 patch.object(app,"_rescale_compact",wraps=app._rescale_compact) as rescale:
                started=time.perf_counter();cpu=time.process_time()
                for units in (*range(78,121,2),*range(118,75,-2)):rows.append(frame(units))
                app.update();drag_ms=(time.perf_counter()-started)*1000;commit_ms=None
                if args.interactive:
                    assert app._resize_preview.active and not app.editor_surface.winfo_ismapped()
                    began=time.perf_counter();native.end_size_move()
                    while app._resize_preview.active or app._resize_preview.finish_after:
                        assert time.perf_counter()-began<3,"Final controls failed to restore"
                        time.sleep(.001);app.update()
                    commit_ms=(time.perf_counter()-began)*1000
                    assert app.editor_surface.winfo_ismapped() and not app._resize_preview.canvas.winfo_ismapped()
                result["runs"].append({"mode":mode,"frames":len(rows),"frame_ms":rows,
                    "median_ms":statistics.median(rows),"p95_ms":sorted(rows)[int(.95*(len(rows)-1))],
                    "max_ms":max(rows),"wall_seconds":time.perf_counter()-started,
                    "cpu_seconds":time.process_time()-cpu,"waveform_draws":wave.call_count,
                    "eq_draws":eq.call_count,"layouts":layout.call_count,"rescales":rescale.call_count,
                    "capture_ms":capture_ms,"drag_ms":drag_ms,"commit_ms":commit_ms})
            assert app._edit_snapshot()==edits and not case.callback_errors
            assert not app.workspace_scroll.bar.winfo_ismapped()
        if args.profile:
            profile=cProfile.Profile();profile.enable()
            for units in range(80,121,4):frame(units)
            app.update();profile.disable()
            with args.output.with_suffix('.profile.txt').open('w',encoding='utf-8') as stream:
                pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(45)
        result['status']='passed'
    finally:case.tearDown();case.doCleanups()
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'runs':[{k:v for k,v in row.items() if k!='frame_ms'} for row in result['runs']]},indent=2))


if __name__=="__main__":main()
