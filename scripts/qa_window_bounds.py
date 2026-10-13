"""Check native Tk geometry against FHD/QHD/4K work areas without OS changes."""
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_workspace import WorkspaceTests
from PIL import ImageGrab


def settle(app):
    until=time.monotonic()+.2
    while time.monotonic()<until:
        app.update();time.sleep(.01)


def check_editor(app):
    width,height=app.winfo_width(),app.winfo_height()
    assert width*7==height*10,(width,height)
    assert app.minsize()[0]<=width<=app.maxsize()[0]
    assert app._layout_mode=="side-by-side"
    assert not app.workspace_scroll.bar.winfo_ismapped()
    for widget in (app.load_button,app.settings_button,app.render_button,app.render_mp3_button,
                   app.eq_panel,app.mixer_panel,app.eq_editor,app.play_button,app.export_stems_button,
                   app.fade_out_spinbox,*app.stem_widgets["other"]):
        assert widget.winfo_ismapped(),str(widget)
        assert widget.winfo_rootx()>=app.winfo_rootx()
        assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+width+1,str(widget)
        assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+height+1,str(widget)
    return width,height


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args=parser.parse_args();out=args.evidence_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    captures=out/"captures";captures.mkdir(exist_ok=True)
    result={"method":"real isolated Tk windows, generated audio, mocked monitor work area and app DPI",
            "os_display_settings_changed":False,"physical_monitor_switch_tested":False,"cases":[]}
    test=WorkspaceTests();test.setUp();app=test.app
    try:
        edits=app._edit_snapshot()
        for name,screen in (("fhd",(1920,1080)),("qhd",(2560,1440)),("4k",(3840,2160))):
            for scale in (1,1.25,1.5,1.75,2):
                area=(0,0,screen[0],screen[1]-40)
                app._ui_scale_override=scale;app._display_scale=scale
                with patch("backend.compact_ui.display_metrics",return_value=(area,scale)):
                    app.state("normal");app._set_initial_compact_window();settle(app)
                    case={"name":name,"screen":screen,"dpi_scale":scale,"work_area":area,
                          "minimum":app.minsize(),"maximum":app.maxsize(),"initial":check_editor(app),
                          "actual_decoration":app._fixed_decoration}
                    for size in (case["minimum"],case["maximum"]):
                        dw,dh=app._fixed_decoration;margin=round(24*scale)
                        assert size[0]+dw+margin<=screen[0]
                        assert size[1]+dh+margin<=screen[1]-40
                    # Centering in a simulated 4K area can place part of the
                    # window outside the real monitor. Move only this QA window
                    # to a visible origin before capturing the same client size.
                    app._window_constraints.resize(*case["initial"],position=(24,24));settle(app)
                    case["capture_client"]=check_editor(app)
                    assert case["capture_client"]==case["initial"]
                    ImageGrab.grab(window=int(app.frame(),0)).save(captures/f"{name}-{round(scale*100)}.png")
                    for requested in ((100,70),(6000,4200)):
                        app.geometry(f"{requested[0]}x{requested[1]}");settle(app)
                        actual=check_editor(app)
                        assert actual==case["minimum" if requested[0]==100 else "maximum"],(case,actual)
                    app.state("zoomed");settle(app)
                    case["maximized"]=check_editor(app)
                    assert case["maximized"]==case["maximum"],case
                    app.state("normal");settle(app)
                    assert app._edit_snapshot()==edits
                    assert not test.callback_errors,test.callback_errors
                    case["scroll"]=False
                    result["cases"].append(case)
                    print(json.dumps(case),flush=True)
        (out/"display-matrix.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    finally:
        test.tearDown();test.doCleanups()


if __name__=="__main__":main()
