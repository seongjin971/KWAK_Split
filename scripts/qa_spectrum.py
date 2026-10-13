"""Capture and measure the live post-effects spectrum on generated audio only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from PIL import ImageGrab
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import require_ffmpeg
from backend.audio_processing.spectrum import FREQUENCIES
from test_spectrum_ui import current_frame
from test_workspace import WorkspaceTests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir",type=Path,default=ROOT/"docs/qa/spectrum")
    parser.add_argument("--release",type=Path)
    args=parser.parse_args()
    evidence=args.evidence_dir.resolve();captures=evidence/"captures"
    captures.mkdir(parents=True,exist_ok=True)
    result={"method":"Real source Tk widgets and actual FFplay PCM; generated audio; dummy device",
            "native_exe_input_tested":False,"captures":[],"levels_dbfs":{}}

    def pump(app,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:app.update();time.sleep(.01)

    with patch.dict(os.environ,{"SDL_AUDIODRIVER":"dummy"}):
        case=WorkspaceTests();case.setUp();app=case.app
        try:
            if args.release:
                release=args.release.resolve()
                class Assets(AppPaths):
                    @property
                    def bin(self):return release/"bin"
                app.paths=Assets(case.paths.root)
                result["bundled_engines"]=str(release)
            source=case.paths.root/"Spectrum - generated tones and noise.wav"
            subprocess.run([str(require_ffmpeg(app.paths)),"-v","error","-f","lavfi","-i",
                "anoisesrc=color=pink:amplitude=.04:duration=15:sample_rate=44100:seed=17",
                "-f","lavfi","-i","aevalsrc=.04*(sin(2*PI*100*t)+sin(2*PI*1000*t)+sin(2*PI*8000*t)):s=44100:d=15",
                "-filter_complex","[0:a][1:a]amix=inputs=2:normalize=0","-ac","2","-c:a","pcm_f32le",str(source)],
                check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            app.load_audio_path(source);case.wait_idle()
            app.eq_mid_freq_var.set(1000);app.fade_in_var.set(0);app.fade_out_var.set(0)
            app.limiter_enabled_var.set(False);app.loop_var.set(False)
            app.geometry("1000x700");app.update();app.toggle_playback()
            def capture(name):
                app.update()
                ImageGrab.grab(window=int(app.frame(),0)).save(captures/(name+".png"))
                result["captures"].append(name)
            index=min(range(len(FREQUENCIES)),key=lambda i:abs(FREQUENCIES[i]-1000))
            for label,gain in (("flat",0),("boost",12),("cut",-12)):
                app.eq_mid_var.set(gain)
                frame=current_frame(app)
                target=result["levels_dbfs"].get("flat",frame.levels[index])+gain
                deadline=time.monotonic()+4
                while abs(app.eq_editor._spectrum_frame.levels[index]-target)>.4 and time.monotonic()<deadline:
                    pump(app,.03)
                pump(app,.15)
                frame=app.eq_editor._spectrum_frame
                result["levels_dbfs"][label]=frame.levels[index]
                result.setdefault("playback_sync",[]).append({"frame_seconds":frame.seconds,
                    "player_seconds":app.realtime_processes.position_seconds(),
                    "clock_received":app.realtime_processes._clock is not None})
                capture("spectrum-"+label)
            result["boost_delta_db"]=result["levels_dbfs"]["boost"]-result["levels_dbfs"]["flat"]
            result["cut_delta_db"]=result["levels_dbfs"]["cut"]-result["levels_dbfs"]["flat"]
            assert abs(result["boost_delta_db"]-12)<.4,result
            assert abs(result["cut_delta_db"]+12)<.4,result
            spectrum=app.realtime_processes.spectrum
            result["mean_fft_ms"]=1000*spectrum.analysis_seconds/max(1,spectrum.frames_analyzed)
            for width,height in ((760,620),(640,480)):
                app.geometry(f"{width}x{height}");pump(app,.12)
                capture(f"spectrum-{width}x{height}")
                editor=app.eq_editor
                for item in editor.find_all():
                    if editor.type(item)=="text":
                        box=editor.bbox(item)
                        assert box[0]>=-2 and box[2]<=editor.winfo_width()+2,(editor.itemcget(item,"text"),box)
            app.stop_preview(False);capture("spectrum-paused")
            assert not app.eq_editor.find_withtag("spectrum")
            result["cleared_on_pause"]=True
            result["callback_errors"]=len(case.callback_errors)
            assert not case.callback_errors,case.callback_errors
        finally:case.tearDown()
    (evidence/"ui-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":main()
