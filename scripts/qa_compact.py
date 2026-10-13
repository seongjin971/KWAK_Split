"""Inspect controlled native app windows using generated audio, without OS input.

Does not alter desktop resolution/scaling or existing user windows/data.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import subprocess
import shutil

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_workspace import WorkspaceTests
from backend.app_paths import AppPaths
from backend.compact_model import initial_window
from backend.compact_widgets import display_metrics
from PIL import ImageGrab


class LocalAssets(AppPaths):
    @property
    def backend(self):return ROOT/"backend"
    @property
    def models(self):return ROOT/"models"


def settle(app):
    until=time.monotonic()+.3
    while time.monotonic()<until:
        app.update();time.sleep(.01)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--all-sizes",action="store_true")
    parser.add_argument("--real-demucs",action="store_true")
    parser.add_argument("--evidence-dir",type=Path,default=ROOT/"docs/qa/compact")
    args=parser.parse_args()
    out=args.evidence_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    captures=out/"captures";captures.mkdir(exist_ok=True)
    cases=[("compact-1000",1000,700,1),("compact-760",760,620,1),("compact-640",640,480,1)]
    cases += [("compact-480",480,360,1),("compact-short",1000,420,1)]
    if args.all_sizes:
        cases += [("1080p-100",1840,960,1),("1080p-125",1760,930,1.25),("1080p-150",1760,900,1.5),
                  ("1080p-175",1760,900,1.75),("1080p-200",1760,880,2),
                  ("1440p-150",2400,1280,1.5),("4k-175",3640,1980,1.75),("4k-200",3640,1980,2)]
    results={"method":"real Tk windows; app DPI override; no OS display changes; generated audio",
             "physical_monitor_switch_tested":False,"cases":[],"work_area_checks":[]}
    for screen in ((1920,1080),(2560,1440),(3840,2160)):
        for scale in (1,1.25,1.5,1.75,2):
            size=initial_window(screen[0],screen[1]-40,scale)
            assert size[0]<screen[0] and size[1]<screen[1]-40
            results["work_area_checks"].append({"screen":screen,"scale":scale,"initial_client":size})
    for name,width,height,scale in cases:
        test=WorkspaceTests();test.ui_scale=scale
        test.setUp();app=test.app;app.paths=LocalAssets(test.paths.root)
        try:
            source=test.paths.root/"qa-stereo.wav"
            subprocess.run([shutil.which("ffmpeg"),"-v","error","-f","lavfi","-i",
                "aevalsrc=.3*sin(2*PI*220*t)*(.2+.8*sin(PI*1.3*t)*sin(PI*1.3*t))|.2*sin(2*PI*660*t)*(.3+.7*sin(PI*.9*t)*sin(PI*.9*t)):s=48000:d=12",
                "-c:a","pcm_s16le",str(source)],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            app.load_audio_path(source);test.wait_idle()
            app.stem_paths={stem:app.source_wav for stem in app.stem_vars};app.stem_range=(0,12)
            app.selection_start_var.set(2);app.selection_end_var.set(8)
            app.eq_low_shape_var.set("High Pass");app.eq_high_shape_var.set("Low Pass")
            app.high_pass_q_var.set(.71);app.low_pass_q_var.set(.71)
            app.status_var.set("");app._refresh_action_states()
            app.geometry(f"{width}x{height}+16+16");settle(app)
            measured=(app.winfo_width(),app.winfo_height())
            requested=(width,height)
            width,height=measured
            assert width*7==height*10,(name,measured)
            assert app.minsize()[0]<=width<=app.maxsize()[0]
            for widget in (app.load_button,app.settings_button,app.render_button,app.render_mp3_button):
                assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+width
            for panel in (app.eq_panel,app.mixer_panel):
                assert panel.winfo_rootx()+panel.winfo_width()<=app.winfo_rootx()+width
                assert panel.winfo_rooty()+panel.winfo_height()<=app.winfo_rooty()+height+1
            assert app._layout_mode=="side-by-side"
            assert not app.workspace_scroll.bar.winfo_ismapped()
            case={"name":name,"requested":requested,"client":measured,"scale":app.ui_scale,"mode":app._layout_mode,
                  "min_client":app.minsize(),"max_client":app.maxsize(),"aspect":[10,7],
                  "scroll":bool(app.workspace_scroll.bar.winfo_ismapped()),"monitor_work_area":display_metrics(app)[0]}
            # DWM clips off-monitor captures. Validate the large geometry above,
            # then inspect the same DPI in a fully visible normal-size window.
            if width>app.winfo_screenwidth() or height>app.winfo_screenheight()-70:
                app.geometry(f"{app.px(1000)}x{app.px(700)}+16+16");settle(app)
                case["capture_note"]="Full viewport checked by widget bounds; capture uses normal window at the same DPI."
            case["capture_client"]=(app.winfo_width(),app.winfo_height())
            ImageGrab.grab(window=int(app.frame(),0)).save(captures/(name+".png"))
            if name=="compact-1000":
                app.open_render_settings();settle(app)
                ImageGrab.grab(window=int(app.render_settings_window.frame(),0)).save(captures/"settings.png")
                app._close_render_settings();app.open_advanced();settle(app)
                ImageGrab.grab(window=int(app._dialog.frame(),0)).save(captures/"advanced.png")
                app._close_render_settings()
            assert not test.callback_errors,test.callback_errors
            results["cases"].append(case);print(json.dumps(case),flush=True)
            if args.real_demucs and name=="compact-1000":
                app.stem_paths={};app.selection_start_var.set(2);app.selection_end_var.set(4)
                started=time.monotonic();app.separate_stems();test.wait_idle(timeout=300)
                assert len(app.stem_paths)==4
                results["demucs"]={"seconds":round(time.monotonic()-started,3),"range":app.stem_range}
                app.render_wav();test.wait_idle();assert app.result_files[0].is_file()
                app.render_mp3();test.wait_idle();assert app.result_files[0].is_file()
                results["real_exports"]=True
                (out/"audio-results.json").write_text(json.dumps({"demucs":results["demucs"],"real_exports":True},indent=2),encoding="utf-8")
        finally:test.tearDown()
    (out/"ui-results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")


if __name__=="__main__":main()
