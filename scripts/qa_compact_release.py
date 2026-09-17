"""Check the packaged EXE and its engines using generated, isolated audio."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import read_duration
from test_workspace import WorkspaceTests
from PIL import ImageGrab


def pump(app,seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.02)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--release",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,default=ROOT/"docs/qa/compact")
    args=parser.parse_args();release=args.release.resolve()
    class ReleaseAssets(AppPaths):
        @property
        def backend(self):return release/"backend"
        @property
        def models(self):return release/"models"
        @property
        def bin(self):return release/"bin"
    evidence=args.evidence_dir.resolve();evidence.mkdir(parents=True,exist_ok=True)
    (evidence/"captures").mkdir(exist_ok=True)
    results={"release":str(release.relative_to(ROOT)),"external_pc_tested":False,
             "method":"packaged EXE startup; real source UI with bundled audio engines; dummy playback device"}
    minimal_path=str(release/"bin")+os.pathsep+os.path.join(os.environ["SystemRoot"],"System32")
    env={**os.environ,"PATH":minimal_path,"PYTHONHOME":str(release/"intentionally-missing-python"),
         "PYTHONPATH":"","OMP_NUM_THREADS":"2","MKL_NUM_THREADS":"2","SDL_AUDIODRIVER":"dummy"}
    exe=release/"KWAK Split.exe"
    process=subprocess.run([str(exe),"--smoke-test"],cwd=release,env=env,timeout=30,
                           capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,(process.returncode,process.stderr)
    results["exe_smoke_exit"]=process.returncode
    results["exe_sha256"]=hashlib.sha256(exe.read_bytes()).hexdigest()
    python=release/"backend/demucs_runtime/python.exe"
    check=subprocess.run([str(python),"-B","-c",
        "import sys,json,torch,torchaudio,demucs;print(json.dumps({'paths':sys.path,'prefix':sys.prefix}))"],
        cwd=release,env=env,capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    runtime=json.loads(check.stdout)
    assert all(Path(p).resolve().is_relative_to(python.parent) for p in runtime["paths"])
    results["runtime_imports_confined_to_release"]=True
    case=WorkspaceTests();case.ui_scale=None;case.setUp();app=case.app
    try:
        app.paths=ReleaseAssets(case.paths.root)
        with patch.dict(os.environ,env):
            app.selection_start_var.set(2);app.selection_end_var.set(4)
            started=time.monotonic();app.separate_stems();case.wait_idle(300)
            assert len(app.stem_paths)==4 and app.stem_range==(2,4)
            results["split_seconds"]=round(time.monotonic()-started,3)
            results["stem_durations"]={name:read_duration(app.paths,path) for name,path in app.stem_paths.items()}
            assert all(abs(duration-2)<.02 for duration in results["stem_durations"].values())
            print("Bundled Demucs: four 2-second stems verified.",flush=True)
            app.eq_low_shape_var.set("High Pass");app.high_pass_slope_var.set(36)
            app.eq_high_shape_var.set("Low Pass");app.low_pass_slope_var.set(24)
            app.tempo_percent_var.set(125);app.pitch_semitones_var.set(3)
            app.fade_in_var.set(.04);app.fade_out_var.set(.04);app.loop_var.set(False)
            exports={}
            for kind,action in (("wav",app.render_wav),("mp3",app.render_mp3)):
                action();case.wait_idle();path=app.result_files[0]
                probe=subprocess.run([str(release/"bin/ffprobe.exe"),"-v","error","-show_streams",
                    "-show_format","-of","json",str(path)],env=env,capture_output=True,text=True,
                    check=True,creationflags=subprocess.CREATE_NO_WINDOW)
                data=json.loads(probe.stdout);stream=data["streams"][0]
                duration=read_duration(app.paths,path)
                assert abs(duration-1.6)<.06,(kind,duration)
                assert int(stream["sample_rate"])==48000
                if kind=="wav":assert stream["codec_name"]=="pcm_s24le"
                else:assert int(stream["bit_rate"])==320000
                exports[kind]={"duration":duration,"sample_rate":stream["sample_rate"],
                               "codec":stream["codec_name"],"bytes":path.stat().st_size}
            results["exports"]=exports
            app.toggle_playback();case.wait_idle();pump(app,.25)
            assert app.preview_playing
            app.toggle_playback();paused=app.playback_position_var.get()
            assert not app.preview_playing and 2<paused<4
            app.toggle_playback();case.wait_idle();pump(app,.12)
            assert app.preview_playing and app.playback_position_var.get()>=paused
            app.stop_preview(show_status=False)
            results["dummy_play_pause_resume"]=True
            app.status_var.set("");app._refresh_action_states();pump(app,.25)
            results["automatic_dpi_scale"]=app.ui_scale
            results["automatic_client"]=[app.winfo_width(),app.winfo_height()]
            ImageGrab.grab(window=int(app.frame(),0)).save(evidence/"captures/automatic-dpi.png")
            assert not case.callback_errors,case.callback_errors
    finally:case.tearDown()
    (evidence/"release-results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(json.dumps(results,indent=2),flush=True)


if __name__=="__main__":main()
