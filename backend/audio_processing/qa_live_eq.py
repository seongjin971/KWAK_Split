"""Opt-in frozen-package self-check, using generated audio and a silent device."""
from array import array
from contextlib import ExitStack
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, _build_mix_filter, start_realtime_mix
from backend.audio_processing.spectrum import analyze_pcm, FFT_SIZE, FLOOR_DB


def check(output, native=False):
    output = Path(output).resolve()
    result = {"frozen": bool(getattr(sys, "frozen", False)), "audio_device": "SDL dummy",
              "native_listening_tested": False}
    original_driver = os.environ.get("SDL_AUDIODRIVER")
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    assets = AppPaths.from_runtime()
    playback = device = None
    try:
        import zmq
        result["pyzmq"] = zmq.__version__
        result["libzmq"] = zmq.zmq_version()
        with tempfile.TemporaryDirectory(prefix="kwak-live-eq-qa-") as folder, ExitStack() as cleanup:
            class QAPaths(AppPaths):
                @property
                def bin(self): return assets.bin
            paths = QAPaths(Path(folder))
            source = paths.root / "generated.wav"
            subprocess.run([str(paths.bin / "ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
                "aevalsrc=.04*sin(2*PI*1000*t)|.04*sin(2*PI*1000*t):s=44100:d=32",
                "-c:a", "pcm_f32le", str(source)], check=True, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            effects = AudioEffects(limiter_enabled=False)
            stems=[MixStem(name,source,.25) for name in ("vocals","drums","bass","other")]
            kwargs={}
            if native:
                from backend.audio_processing.wave_output import WaveOutputDevice
                device=WaveOutputDevice(muted=True)
                cleanup.callback(device.close)
                kwargs["output_player"]=device.begin()
                result["audio_device"]="muted WinMM device"
            playback = start_realtime_mix(paths,stems,0,32,0,0,effects,**kwargs)
            cleanup.callback(playback.close)
            if native:playback.resume()
            assert playback.eq_controller is not None, "Missing frozen live EQ client"

            def wait(predicate, timeout=4):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    value=predicate()
                    if value:return value
                    time.sleep(.01)
                raise AssertionError("Live EQ check timed out")

            initial = wait(lambda:playback.spectrum_frame())
            flat = max(initial.levels)
            chunks=[]
            feed=playback.spectrum.feed
            def capture(data): chunks.append(data);feed(data)
            playback.spectrum.feed=capture
            pids=[p.pid for p in playback]
            result["updates"]=[]
            clock=playback.position_seconds();wall=time.monotonic()
            for gain in (12,-12,0):
                began=time.monotonic()
                assert playback.update_eq(replace(effects,mid_db=gain))
                def settled():
                    frame=playback.spectrum_frame()
                    return frame if frame and abs(max(frame.levels)-flat-gain)<.2 else None
                frame=wait(settled)
                result["updates"].append({"gain_db":gain,"measured_delta_db":max(frame.levels)-flat,
                    "spectrum_settle_seconds":round(time.monotonic()-began,3)})
                assert [p.pid for p in playback]==pids and all(p.poll() is None for p in playback)
                assert not playback.eq_controller.error
            result["audio_clock_per_wall_second"]=(playback.position_seconds()-clock)/(time.monotonic()-wall)
            assert .9 < result["audio_clock_per_wall_second"] < 1.1
            samples=array("h");samples.frombytes(b"".join(chunks));left=samples[::2]
            result["minimum_512_sample_rms"]=min(math.sqrt(sum(v*v for v in left[i:i+512])/512)
                                                for i in range(0,len(left)-512,512))
            result["maximum_sample_step"]=max(abs(b-a) for a,b in zip(left,left[1:]))
            assert result["minimum_512_sample_rms"]>100 and result["maximum_sample_step"]<1800
            result["mode_updates"]=[]
            modes=[replace(effects,low_shape="Low Shelf",low_db=-9,low_freq=1500)]
            modes.extend(replace(effects,low_shape="High Pass",high_pass_hz=1500,high_pass_slope=s)
                         for s in (12,24,36,48))
            modes.extend([effects,replace(effects,high_shape="High Shelf",high_db=-9,high_freq=1500)])
            modes.extend(replace(effects,high_shape="Low Pass",low_pass_hz=1500,low_pass_slope=s)
                         for s in (12,24,36,48))
            modes.append(effects)
            for updated in modes:
                inputs,filters=_build_mix_filter(stems,0,1,0,0,updated)
                raw=subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error",*inputs,
                    "-filter_complex",filters,"-map","[outa]","-ar","44100","-ac","2","-f","s16le","-"],
                    check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10).stdout
                midpoint=(len(raw)//2//4)*4
                expected=max(analyze_pcm(raw[midpoint:midpoint+FFT_SIZE*4]))
                began=time.monotonic()
                assert playback.update_eq(updated)
                wait(lambda:playback.eq_controller.applied_revision==playback.eq_controller.revision)
                def settled_mode():
                    frame=playback.spectrum_frame()
                    return frame if frame and abs(max(frame.levels)-expected)<.2 else None
                frame=wait(settled_mode)
                result["mode_updates"].append({"low_shape":updated.low_shape,"high_shape":updated.high_shape,
                    "high_pass_hz":updated.high_pass_hz,"low_pass_hz":updated.low_pass_hz,
                    "high_pass_slope":updated.high_pass_slope,"low_pass_slope":updated.low_pass_slope,
                    "export_error_db":round(max(frame.levels)-expected,4),
                    "spectrum_settle_seconds":round(time.monotonic()-began,3)})
                assert [p.pid for p in playback]==pids and all(p.poll() is None for p in playback)
                assert not playback.eq_controller.error
            result["audio_clock_per_wall_second_including_modes"]=(playback.position_seconds()-clock)/(time.monotonic()-wall)
            assert .9 < result["audio_clock_per_wall_second_including_modes"] < 1.1
            result["mixer_updates"]=[]
            for weights in ((1,0,0,0),(0,0,0,0),(0,.5,0,0),(.25,.25,.25,.25),
                            (0,0,0,2),(0,0,0,0),(0,0,1,0)):
                began=time.monotonic()
                updated=[replace(stem,gain=gain) for stem,gain in zip(stems,weights)]
                expected=flat+20*math.log10(sum(weights)) if sum(weights) else FLOOR_DB
                assert playback.update_mixer(updated)
                wait(lambda:playback.eq_controller.mixer_applied_revision==playback.eq_controller.mixer_revision)
                def settled_mixer():
                    frame=playback.spectrum_frame()
                    return frame if frame and abs(max(frame.levels)-expected)<.2 else None
                frame=wait(settled_mixer)
                result["mixer_updates"].append({"weights":weights,"expected_peak_db":expected,
                    "measured_peak_db":max(frame.levels),"spectrum_settle_seconds":round(time.monotonic()-began,3)})
                assert [p.pid for p in playback]==pids and all(p.poll() is None for p in playback)
                assert not playback.eq_controller.error
            result["same_processes_throughout"]=True
            playback.close()
            assert all(p.poll() is not None for p in playback)
            assert not playback.eq_controller._thread.is_alive()
            result["clean_shutdown"]=True
            result["status"]="passed"
    except Exception as exc:
        result["status"]="failed"
        result["error"]=repr(exc)
    finally:
        if playback:playback.close()
        if original_driver is None:os.environ.pop("SDL_AUDIODRIVER",None)
        else:os.environ["SDL_AUDIODRIVER"]=original_driver
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
