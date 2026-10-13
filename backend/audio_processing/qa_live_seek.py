"""Opt-in frozen seek verification with generated multisection audio and SDL dummy."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, _build_mix_filter, start_realtime_mix
from backend.audio_processing.spectrum import analyze_pcm, FFT_SIZE, SAMPLE_RATE


def check(output, native=False):
    output=Path(output).resolve()
    result={"frozen":bool(getattr(sys,"frozen",False)),"audio_device":"SDL dummy",
            "native_listening_tested":False,"seeks":[]}
    original=os.environ.get("SDL_AUDIODRIVER");os.environ["SDL_AUDIODRIVER"]="dummy"
    assets=AppPaths.from_runtime();play=device=None
    def wait(predicate,timeout=4):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=predicate()
            if value:return value
            time.sleep(.005)
        raise AssertionError("Live seek check timed out")
    try:
        if native:
            from backend.audio_processing.wave_output import WaveOutputDevice
            device=WaveOutputDevice(muted=True);result["audio_device"]="muted WinMM device"
        with tempfile.TemporaryDirectory(prefix="kwak-live-seek-qa-") as folder:
            class QAPaths(AppPaths):
                @property
                def bin(self):return assets.bin
            paths=QAPaths(Path(folder));source=paths.root/"sections.wav"
            frequency="if(lt(t,4),220,if(lt(t,8),440,if(lt(t,12),1000,3000)))"
            subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error","-f","lavfi","-i",
                f"aevalsrc='.04*sin(2*PI*({frequency})*t)|.02*sin(2*PI*({frequency})*t)':s=48000:d=24",
                "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
            stems=[MixStem(n,source,g) for n,g in zip(("vocals","drums","bass","other"),(.5,0,.25,0))]
            for tempo,pitch in ((1,0),(.5,3),(2,-3)):
                effects=AudioEffects(mid_db=-6,tempo_ratio=tempo,pitch_semitones=pitch,limiter_enabled=False)
                kwargs={"output_player":device.begin()} if device else {}
                play=start_realtime_mix(paths,stems,0,24,0,0,effects,**kwargs)
                if device:play.resume()
                stages=[play._stage];player=play.player
                try:
                    wait(lambda:play.position_seconds()>.35)
                    clock=play.position_seconds();wall=time.monotonic()
                    stamps=[];feed=play.spectrum.feed
                    def capture(pcm):stamps.append(time.monotonic());feed(pcm)
                    play.spectrum.feed=capture
                    for start in (8.25,4.25,12.25,1.25):
                        began=time.monotonic();assert play.seek(start,24-start)
                        revision=play.seek_revision
                        state=wait(lambda:(s if (s:=play.playback_position()).revision==revision and not s.seeking else None))
                        latency=time.monotonic()-began
                        boundary=play._timeline[0][0]
                        stages.append(play._stage)
                        assert latency<1.5 and start<=state.position_seconds<start+.2*tempo
                        inputs,filters=_build_mix_filter(stems,start,24-start,0,0,effects)
                        raw=subprocess.run([str(paths.bin/"ffmpeg.exe"),"-v","error",*inputs,
                            "-filter_complex",filters,"-map","[outa]","-ar","44100","-ac","2","-f","s16le","-"],
                            check=True,capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW).stdout
                        wait(lambda:play.playback_position().position_seconds>start+.25*tempo)
                        def matched_window():
                            frame=play.spectrum_frame()
                            if not frame:return None
                            offset=round((frame.seconds-boundary)*SAMPLE_RATE-FFT_SIZE/2)*4
                            if offset<.01*SAMPLE_RATE*4 or offset+FFT_SIZE*4>len(raw):return None
                            expected=analyze_pcm(raw[offset:offset+FFT_SIZE*4])
                            peak=expected.index(max(expected))
                            delta=frame.levels[peak]-expected[peak]
                            assert abs(delta)<.3,delta
                            return delta,frame
                        delta,frame=wait(matched_window)
                        assert player is play.player and player.poll() is None
                        assert not play.error and not play.take_seek_error() and not play.take_eq_error()
                        result["seeks"].append({"source_seconds":start,"tempo_ratio":tempo,"pitch_semitones":pitch,
                            "request_to_output_clock_seconds":round(latency,4),
                            "export_error_db":round(delta,4),"same_player":True})
                    ratio=(play.position_seconds()-clock)/(time.monotonic()-wall)
                    assert .88<ratio<1.1,ratio
                    result.setdefault("clock_ratios",[]).append(ratio)
                    assert max(b-a for a,b in zip(stamps,stamps[1:]))<.15
                    result.setdefault("maximum_pcm_feed_gaps_seconds",[]).append(max(b-a for a,b in zip(stamps,stamps[1:])))
                    # A burst coalesces to one next position while live EQ/mixer edits survive.
                    for index in range(40):assert play.seek(1+index/10,23-index/10)
                    assert play.seek(8.25,15.75)
                    effects=replace(effects,mid_db=3)
                    updated=[replace(stems[0],gain=.25),*stems[1:]]
                    assert play.update_eq(effects) and play.update_mixer(updated)
                    wait(lambda:not play.playback_position().seeking)
                    assert play.playback_position().start_seconds==8.25 and play.player is player
                    wait(lambda:play.eq_controller.applied_revision==play.eq_controller.revision and
                         play.eq_controller.mixer_applied_revision==play.eq_controller.mixer_revision)
                    assert play.eq_controller._desired[("equalizer@kw_mid","g")]==3
                    assert play.eq_controller._mixer_desired==(.25,0,.25,0)
                    assert not play.take_eq_error() and not play.take_seek_error()
                finally:
                    stages.append(play._stage);play.close()
                assert all(p.poll() is not None for p in play)
                assert all(not t.is_alive() for t in play._threads)
                assert all(s.process.poll() is not None and not s.controller._thread.is_alive() for s in stages)
            result["status"]="passed";result["clean_shutdown"]=True
    except Exception as exc:
        result["status"]="failed";result["error"]=repr(exc)
    finally:
        if play:play.close()
        if device:device.close()
        if original is None:os.environ.pop("SDL_AUDIODRIVER",None)
        else:os.environ["SDL_AUDIODRIVER"]=original
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["status"]=="passed" else 1
