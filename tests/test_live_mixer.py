"""Real multi-input PCM checks with a silent device; no user audio."""
from array import array
from dataclasses import replace
import math
import subprocess
import time

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, require_ffmpeg, start_realtime_mix
from backend.audio_processing.spectrum import FREQUENCIES, FLOOR_DB
from test_spectrum import filtered_levels, wait_for

NAMES=("vocals","drums","bass","other")
TONES=(220,440,1000,3000)


@pytest.fixture
def stems(tmp_path,monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER","dummy")
    paths=AppPaths(tmp_path);paths.ensure();items=[]
    for name,freq in zip(NAMES,TONES):
        source=tmp_path/(name+".wav")
        subprocess.run([str(require_ffmpeg(paths)),"-v","error","-f","lavfi","-i",
            f"aevalsrc=.02*sin(2*PI*{freq}*t)|.01*sin(2*PI*{freq}*t):s=44100:d=20",
            "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        items.append(MixStem(name,source,1))
    return paths,items


def weighted(items,weights):
    return [replace(item,gain=gain) for item,gain in zip(items,weights)]


def expect_mix(playback,paths,items,effects,timeout=4):
    expected=filtered_levels(paths,items,effects)
    factor=2**(effects.pitch_semitones/12)
    indices=[[i for i,hz in enumerate(FREQUENCIES) if freq*factor*.96<hz<freq*factor*1.04]
             for freq in TONES[:len(items)]]
    targets=[max(expected[i] for i in band) for band in indices]
    def ready():
        frame=playback.spectrum_frame()
        if not frame:return None
        measured=[max(frame.levels[i] for i in band) for band in indices]
        if all(abs(a-b)<.35 if b>-65 else a<-65 for a,b in zip(measured,targets)):
            return frame
    return wait_for(ready,timeout)


@pytest.mark.parametrize("initial",[(1,1,1,1),(0,0,0,0),(1,0,0,0)])
def test_mute_solo_gain_and_unmute_match_export_without_restart(stems,initial):
    paths,items=stems;effects=AudioEffects(limiter_enabled=False)
    play=start_realtime_mix(paths,weighted(items,initial),0,20,0,0,effects)
    try:
        expect_mix(play,paths,weighted(items,initial),effects)
        pids=[p.pid for p in play]
        for weights in ((0,1,0,0),(0,0,0,0),(.5,0,2,.0005),(1,1,1,1)):
            updated=weighted(items,weights);clock=play.position_seconds()
            assert play.update_mixer(updated)
            wait_for(lambda:play.eq_controller.mixer_applied_revision==play.eq_controller.mixer_revision)
            expect_mix(play,paths,updated,effects)
            assert play.position_seconds()>=clock
            assert [p.pid for p in play]==pids and all(p.poll() is None for p in play)
            assert not play.eq_controller.error
    finally:play.close()
    assert not play.eq_controller._thread.is_alive() and all(p.poll() is not None for p in play)


def test_atomic_solo_exchange_does_not_drop_or_double_identical_tracks(stems):
    paths,items=stems
    items=[replace(item,path=items[2].path) for item in items]
    effects=AudioEffects(limiter_enabled=False)
    play=start_realtime_mix(paths,weighted(items,(1,0,0,0)),0,20,0,0,effects)
    chunks=[]
    try:
        wait_for(lambda:play.position_seconds()>.7)
        feed=play.spectrum.feed
        def capture(data):chunks.append(data);feed(data)
        play.spectrum.feed=capture
        for index in range(12):
            assert play.update_mixer(weighted(items,tuple(int(i==index%4) for i in range(4))))
            wait_for(lambda:play.eq_controller.mixer_applied_revision==play.eq_controller.mixer_revision)
            time.sleep(.05)
        time.sleep(.4)
        pcm=array("h");pcm.frombytes(b"".join(chunks));left=pcm[::2]
        rms=[math.sqrt(sum(v*v for v in left[i:i+512])/512) for i in range(0,len(left)-512,512)]
        assert min(rms)>440 and max(rms)<485
        assert max(abs(v) for v in left)<=657
        assert max(abs(b-a) for a,b in zip(left,left[1:]))<100
        assert not play.eq_controller.error
    finally:play.close()


@pytest.mark.parametrize("effects",[AudioEffects(),AudioEffects(tempo_ratio=.5,pitch_semitones=3,sample_rate=48000)])
def test_latest_mixer_values_survive_concurrent_eq_bank_switches(stems,effects):
    paths,items=stems;play=start_realtime_mix(paths,items,0,20,0,0,effects)
    try:
        wait_for(lambda:play.position_seconds()>.3)
        for i in range(24):
            updated=weighted(items,(i/24,1-i/24,.5,0))
            eq=replace(effects,low_shape="Low Shelf" if i%2 else "High Pass",
                       low_db=-3 if i%2 else 0,high_pass_hz=0 if i%2 else 90,
                       high_pass_slope=(12,24,36,48)[i%4],mid_db=3)
            assert play.update_mixer(updated) and play.update_eq(eq)
            time.sleep(.012)
        wait_for(lambda:play.eq_controller.applied_revision==play.eq_controller.revision
                 and play.eq_controller.mixer_applied_revision==play.eq_controller.mixer_revision,4)
        expect_mix(play,paths,updated,eq,5)
        assert not play.eq_controller.error and all(p.poll() is None for p in play)
    finally:play.close()


def test_changed_inputs_are_rejected_and_stop_interrupts_pending_mixer(stems):
    paths,items=stems;play=start_realtime_mix(paths,items,0,20,0,0,AudioEffects())
    try:
        assert not play.update_mixer(items[:-1])
        assert not play.update_mixer([replace(items[0],offset_seconds=1),*items[1:]])
        assert not play.update_mixer([items[0],items[0],*items[2:]])
        assert not play.update_mixer(weighted(items,(float("nan"),1,1,1)))
        assert play.update_mixer(list(reversed(weighted(items,(.1,.2,.3,.4)))))
    finally:play.close()
    assert not play.update_mixer(items)
    assert not play.eq_controller._thread.is_alive()


def test_initially_silent_stem_stays_sample_aligned_after_unmute(stems):
    paths,items=stems
    source=paths.root/"chirp.wav";opposite=paths.root/"opposite.wav"
    args=dict(check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run([str(require_ffmpeg(paths)),"-v","error","-f","lavfi","-i",
        "aevalsrc=.03*sin(2*PI*(300*t+61*t*t)):s=44100:d=12","-ac","2","-c:a","pcm_f32le",str(source)],**args)
    subprocess.run([str(require_ffmpeg(paths)),"-v","error","-i",str(source),"-af","volume=-1",
        "-c:a","pcm_f32le",str(opposite)],**args)
    pair=[MixStem("vocals",source,1),MixStem("drums",opposite,0)]
    play=start_realtime_mix(paths,pair,0,12,0,0,AudioEffects(limiter_enabled=False))
    try:
        wait_for(lambda:play.position_seconds()>.6)
        assert max(play.spectrum_frame().levels)>-50
        assert play.update_mixer(weighted(pair,(0,0)))
        wait_for(lambda:max(play.spectrum_frame().levels)==FLOOR_DB)
        clock=play.position_seconds()
        assert play.update_mixer(weighted(pair,(1,1)))
        wait_for(lambda:play.eq_controller.mixer_applied_revision==play.eq_controller.mixer_revision)
        time.sleep(.65)
        # Opposite chirps cancel only if the silent input kept its exact position.
        assert max(play.spectrum_frame().levels)==FLOOR_DB
        assert play.position_seconds()>clock and all(p.poll() is None for p in play)
        assert play.update_mixer(pair)
        wait_for(lambda:max(play.spectrum_frame().levels)>-50)
    finally:play.close()
