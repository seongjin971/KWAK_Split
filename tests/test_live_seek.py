"""Actual PCM and output-clock checks for discontinuous source positions."""
from array import array
from dataclasses import replace
import subprocess
import sys
import threading
import time

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, _build_mix_filter, require_ffmpeg, start_realtime_mix
from backend.audio_processing.spectrum import FREQUENCIES, FLOOR_DB, SAMPLE_RATE, FFT_SIZE, analyze_pcm
from backend.audio_processing.playback_stream import DecoderStage
from test_spectrum import filtered_levels, filtered_pcm, wait_for


@pytest.fixture
def seek_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    paths=AppPaths(tmp_path); paths.ensure()
    source=tmp_path/"sections.wav"
    frequency="if(lt(t,4),220,if(lt(t,8),440,if(lt(t,12),1000,3000)))"
    subprocess.run([str(require_ffmpeg(paths)), "-v", "error", "-f", "lavfi", "-i",
        f"aevalsrc='.04*sin(2*PI*({frequency})*t)|.02*sin(2*PI*({frequency})*t)':s=48000:d=20",
        "-c:a", "pcm_f32le", str(source)], check=True, capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return paths, [MixStem("source",source,1)]


def seek_settled(play, start, duration):
    before=time.monotonic()
    assert play.seek(start,duration)
    revision=play.seek_revision
    state=wait_for(lambda:(s if (s:=play.playback_position()).revision==revision and not s.seeking else None))
    assert state.start_seconds==start
    assert start<=state.position_seconds<start+.25*state.tempo_ratio
    return time.monotonic()-before


@pytest.mark.parametrize("tempo,pitch",[(1,0),(.5,3),(2,-3)])
def test_forward_backward_seeks_keep_player_and_map_audible_time(seek_audio,tempo,pitch):
    paths,stems=seek_audio
    effects=AudioEffects(tempo_ratio=tempo,pitch_semitones=pitch,limiter_enabled=False,sample_rate=48000)
    play=start_realtime_mix(paths,stems,0,20,0,0,effects)
    stages=[]
    try:
        wait_for(lambda:play.position_seconds()>.4)
        player=play.player; clock=play.position_seconds()
        for start,freq in ((8.25,1000),(4.25,440),(12.25,3000),(.25,220)):
            stages.append(play._stage)
            assert seek_settled(play,start,20-start)<1.5
            boundary=play._timeline[0][0]
            raw=filtered_pcm(paths,stems,effects,start=start,duration=20-start)
            band=[i for i,hz in enumerate(FREQUENCIES) if freq*2**(pitch/12)*.95<hz<freq*2**(pitch/12)*1.05]
            wait_for(lambda:play.playback_position().position_seconds>start+.3*tempo)
            def matches_source_window():
                frame=play.spectrum_frame()
                if not frame:return None
                offset=round((frame.seconds-boundary)*SAMPLE_RATE-FFT_SIZE/2)*4
                if offset<.01*SAMPLE_RATE*4 or offset+FFT_SIZE*4>len(raw):return None
                # Pitch-shifted low tones vary across FFT windows. Compare the
                # exact output window, not an unrelated export midpoint.
                expected=analyze_pcm(raw[offset:offset+FFT_SIZE*4])
                assert max(expected[i] for i in band)>-65
                delta=abs(max(frame.levels[i] for i in band)-max(expected[i] for i in band))
                assert delta<.3,(start,tempo,pitch,offset,delta)
                return frame
            frame=wait_for(matches_source_window)
            assert frame.seconds<=play.position_seconds()
            assert play.player is player and player.poll() is None
            assert play.position_seconds()>clock; clock=play.position_seconds()
            assert not play.error and not play.take_seek_error()
            wait_for(lambda:all(s.process.poll() is not None and not s.controller._thread.is_alive() for s in stages))
    finally:
        stages.append(play._stage); play.close()
    assert all(s.process.poll() is not None and not s.controller._thread.is_alive() for s in stages)
    assert all(not t.is_alive() for t in play._threads)


def test_latest_seek_and_edits_win_while_preparation_is_delayed(seek_audio,monkeypatch):
    paths,stems=seek_audio
    effects=AudioEffects(limiter_enabled=False,mid_freq=1000)
    play=start_realtime_mix(paths,stems,0,20,0,0,effects)
    factory=play._factory; entered=threading.Event(); release=threading.Event(); made=[]
    def delayed(**settings):
        entered.set(); release.wait(2)
        stage=factory(**settings); made.append(stage); return stage
    monkeypatch.setattr(play,"_factory",delayed)
    try:
        wait_for(lambda:play.position_seconds()>.4)
        player=play.player; clock=play.position_seconds()
        assert play.seek(4,16); assert entered.wait(1)
        for index in range(40):assert play.seek(index/10,20-index/10)
        assert play.seek(8.25,11.75)
        effects=replace(effects,mid_db=-9,low_shape="Low Shelf",low_db=3)
        updated=[replace(stems[0],gain=.5)]
        assert play.update_eq(effects) and play.update_mixer(updated)
        time.sleep(.15)
        assert play.position_seconds()>clock and play.player is player
        assert play.playback_position().seeking and play.applied_seek_revision==0
        release.set()
        wait_for(lambda:not play.playback_position().seeking)
        assert play.playback_position().revision==play.seek_revision==42
        assert play.playback_position().start_seconds==8.25
        expected=max(filtered_levels(paths,updated,effects,start=8.25,duration=2))
        wait_for(lambda:(f:=play.spectrum_frame()) and abs(max(f.levels)-expected)<.3)
        assert len(made)==2 and not play.take_eq_error() and not play.take_seek_error()
    finally:release.set(); play.close()
    assert all(s.process.poll() is not None for s in made)


def test_crossfade_limits_a_discontinuous_waveform_and_keeps_forwarding(seek_audio):
    paths,_=seek_audio; source=paths.root/"step.wav"
    subprocess.run([str(require_ffmpeg(paths)),"-v","error","-f","lavfi","-i",
        "aevalsrc='if(lt(t,4),.1,-.1)|if(lt(t,4),-.08,.08)':s=44100:d=12",
        "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    play=start_realtime_mix(paths,[MixStem("source",source,1)],0,12,0,0,AudioEffects(limiter_enabled=False))
    chunks=[]; stamps=[]
    try:
        wait_for(lambda:play.position_seconds()>.4)
        feed=play.spectrum.feed
        def capture(pcm):chunks.append(pcm); stamps.append(time.monotonic()); feed(pcm)
        play.spectrum.feed=capture
        seek_settled(play,4.25,7.75); time.sleep(.2)
        pcm=array("h");pcm.frombytes(b"".join(chunks));left=pcm[::2];right=pcm[1::2]
        assert max(left)>3200 and min(left)<-3200
        assert max(right)>2600 and min(right)<-2600
        assert max(abs(b-a) for a,b in zip(left,left[1:]))<20
        assert max(b-a for a,b in zip(stamps,stamps[1:]))<.12
        assert not play.error
    finally:play.close()


def test_seek_failure_keeps_playing_and_a_later_seek_recovers(seek_audio,monkeypatch):
    paths,stems=seek_audio; play=start_realtime_mix(paths,stems,0,20,0,0)
    factory=play._factory
    try:
        wait_for(lambda:play.position_seconds()>.4)
        player=play.player; decoder=play.decoder
        def fail(**settings):raise OSError("injected seek failure")
        monkeypatch.setattr(play,"_factory",fail)
        assert play.seek(5,15)
        assert "injected" in wait_for(play.take_seek_error)
        assert not play.playback_position().seeking and play.decoder is decoder and player.poll() is None
        assert not play.take_seek_error()
        monkeypatch.setattr(play,"_factory",factory)
        seek_settled(play,8,12)
        assert play.player is player
    finally:play.close()


def test_stalled_preparation_times_out_without_stopping_current_audio(seek_audio,monkeypatch):
    paths,stems=seek_audio;play=start_realtime_mix(paths,stems,0,20,0,0)
    made=[]
    def stalled(**settings):
        process=subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        stage=DecoderStage(process);made.append(stage);return stage
    monkeypatch.setattr(play,"_factory",stalled)
    monkeypatch.setattr(play,"PREPARE_TIMEOUT_SECONDS",.15)
    try:
        wait_for(lambda:play.position_seconds()>.3)
        player=play.player;clock=play.position_seconds()
        assert play.seek(4,16)
        assert "too long" in wait_for(play.take_seek_error,2)
        assert not play.playback_position().seeking and play.position_seconds()>clock
        assert play.player is player and player.poll() is None
    finally:play.close()
    assert all(s.process.poll() is not None for s in made)


@pytest.mark.parametrize("wait",[False,True])
def test_stop_cancels_prepared_and_pending_seeks(seek_audio,monkeypatch,wait):
    paths,stems=seek_audio; play=start_realtime_mix(paths,stems,0,20,0,0)
    factory=play._factory; made=[]
    def recorded(**settings):
        stage=factory(**settings); made.append(stage); return stage
    monkeypatch.setattr(play,"_factory",recorded)
    assert play.seek(10,10)
    wait_for(lambda:made)
    play.close(wait=wait)
    assert not play.seek(2,18)
    wait_for(lambda:all(not t.is_alive() for t in play._threads))
    wait_for(lambda:all(s.process.poll() is not None and not s.controller._thread.is_alive() for s in made))
    assert play.player.poll() is not None


def test_near_end_seek_reuses_player_and_new_end_finishes_normally(seek_audio):
    paths,stems=seek_audio;play=start_realtime_mix(paths,stems,0,1,0,0)
    try:
        wait_for(lambda:play.position_seconds()>.8)
        player=play.player
        seek_settled(play,8,1)
        wait_for(lambda:player.poll() is not None)
        state=play.playback_position()
        assert state.start_seconds==8 and state.position_seconds==pytest.approx(9,abs=.01)
        assert player.returncode==0 and not play.error
    finally:play.close()


def test_seek_preserves_partial_stem_offset_and_selection_anchored_fades(seek_audio):
    paths,items=seek_audio;stems=[replace(items[0],offset_seconds=5)]
    effects=AudioEffects(limiter_enabled=False,sample_rate=44100)
    play=start_realtime_mix(paths,stems,5,20,10,4,effects,fade_bounds=(5,25))
    chunks=[]
    try:
        wait_for(lambda:play.position_seconds()>.3)
        feed=play.spectrum.feed
        def capture(pcm):chunks.append((play._sent_frames-len(pcm)//4,pcm));feed(pcm)
        play.spectrum.feed=capture
        assert play.seek(13.25,11.75)
        wait_for(lambda:play.applied_seek_revision==1)
        boundary=round(play._timeline[-1][0]*SAMPLE_RATE)
        wait_for(lambda:play._sent_frames>boundary+10000)
        inputs,filters=_build_mix_filter(stems,13.25,11.75,10,4,effects,fade_bounds=(5,25))
        expected=subprocess.run([str(require_ffmpeg(paths)),"-v","error",*inputs,
            "-filter_complex",filters,"-map","[outa]","-ar","44100","-ac","2","-f","s16le","-"],
            check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW).stdout
        actual=b"".join(pcm for _,pcm in chunks)
        offset=(boundary-chunks[0][0])*4
        a=array("h");b=array("h")
        a.frombytes(actual[offset+2048:offset+32768]);b.frombytes(expected[2048:32768])
        assert len(a)==len(b) and max(abs(x-y) for x,y in zip(a,b))<=1
    finally:play.close()


def test_muted_stems_remain_sample_aligned_after_seek_and_unmute(seek_audio):
    paths,items=seek_audio;opposite=paths.root/"opposite.wav"
    subprocess.run([str(require_ffmpeg(paths)),"-v","error","-i",str(items[0].path),"-af","volume=-1",
        "-c:a","pcm_f32le",str(opposite)],check=True,capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    stems=[replace(items[0],name="vocals",offset_seconds=5),MixStem("drums",opposite,0,5)]
    play=start_realtime_mix(paths,stems,5,20,0,0,AudioEffects(limiter_enabled=False))
    try:
        wait_for(lambda:play.position_seconds()>.3)
        seek_settled(play,13.25,11.75)
        assert play.update_mixer([stems[0],replace(stems[1],gain=1)])
        wait_for(lambda:max(play.spectrum_frame().levels)==FLOOR_DB)
        time.sleep(.3)
        assert max(play.spectrum_frame().levels)==FLOOR_DB
    finally:play.close()
