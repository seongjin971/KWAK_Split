"""Real Windows output clocks and continuous generated PCM across retained pause."""
from array import array
from dataclasses import replace
import subprocess
import threading
import time

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, start_realtime_mix
from backend.audio_processing.wave_output import WaveOutputDevice
from backend.audio_processing.warm_transport import PlaybackRequest, WarmTransport
from test_spectrum import filtered_pcm, wait_for


@pytest.fixture
def audio(tmp_path):
    paths=AppPaths(tmp_path);paths.ensure();source=tmp_path/"chirp.wav"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i",
        "aevalsrc=.03*sin(2*PI*(190*t+60*t*t))|.02*sin(2*PI*(310*t+85*t*t)):s=44100:d=2",
        "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return paths,tuple(MixStem(name,source,gain) for name,gain in
                       zip(("vocals","drums","bass","other"),(.5,0,.25,.25)))


@pytest.fixture(scope="module")
def retained_device():
    # Match the app's lifetime: changes of source/speed reuse an open device.
    device=WaveOutputDevice(muted=True)
    try:yield device
    finally:device.close()


@pytest.mark.parametrize("speed,pitch",[(.5,3),(1,0),(2,-3)])
def test_native_pause_retains_exact_pcm_device_decoder_and_source_clock(audio,retained_device,speed,pitch):
    paths,stems=audio;effects=AudioEffects(tempo_ratio=speed,pitch_semitones=pitch,mid_db=-3,limiter_enabled=False)
    expected=filtered_pcm(paths,stems,effects)
    device=retained_device;player=device.begin();chunks=[]
    class RecordedInput:
        def write(self,pcm):
            written=player.write(pcm);chunks.append(bytes(pcm[:written]));return written
        def flush(self):player.flush()
        def close(self):player.close()
    player.stdin=RecordedInput()
    play=start_realtime_mix(paths,stems,0,2,0,0,effects,output_player=player)
    try:
        wait_for(lambda:player.queued_seconds>.08)
        assert play.position_seconds()==0 and player.paused
        handle=device.handle;pid=play.decoder.pid;sent=play._sent_frames
        time.sleep(.15)
        assert play.position_seconds()==0 and play._sent_frames<=sent+2048
        for _ in range(2):
            position=play.position_seconds();queued=player.queued_seconds
            began=time.perf_counter();assert play.resume();command=time.perf_counter()-began
            observed=[]
            def advanced():
                now=play.position_seconds();observed.append((time.perf_counter()-began,now))
                return now>position+.01
            wait_for(advanced)
            assert time.perf_counter()-began<.15,dict(position=position,queued=queued,
                command=command,observed=observed)
            wait_for(lambda:play.position_seconds()>position+.15)
            assert play.pause();paused=play.playback_position();clock=play.position_seconds()
            time.sleep(.12)
            assert play.position_seconds()==clock and play.playback_position()==paused
            assert paused.position_seconds==pytest.approx(clock*speed,abs=1/44100)
            assert play.decoder.pid==pid and device.handle==handle and player.poll() is None
        play.resume();wait_for(lambda:player.poll() is not None,timeout=6)
        actual=array("h");actual.frombytes(b"".join(chunks));reference=array("h");reference.frombytes(expected)
        assert len(actual)==len(reference)
        assert max(abs(a-b) for a,b in zip(actual,reference))<=2
        assert not play.error and not play.eq_controller.error
    finally:play.close()
    assert all(not thread.is_alive() for thread in play._threads)
    assert not play.spectrum._thread.is_alive() and not play.eq_controller._thread.is_alive()


def test_replaced_session_cannot_write_or_reset_new_device_queue():
    device=WaveOutputDevice(muted=True)
    try:
        old=device.begin();old.write(bytes(1024))
        current=device.begin();current.write(bytes(4096));queued=current.queued_seconds
        old.terminate()
        with pytest.raises(BrokenPipeError):old.write(bytes(1024))
        assert current.queued_seconds==queued and current.paused and current.poll() is None
        current.resume();current.close();current.wait(timeout=2)
    finally:device.close()


def test_cancelled_preparation_closes_late_decoder_and_keeps_newest_request(audio):
    paths,stems=audio;entered=threading.Event();release=threading.Event();owners=[]
    def factory(**kwargs):
        if not entered.is_set():entered.set();assert release.wait(3)
        owner=start_realtime_mix(paths,**kwargs);owners.append(owner);return owner
    manager=WarmTransport(factory,lambda:WaveOutputDevice(muted=True))
    first=PlaybackRequest(stems,0,2,0,0,AudioEffects(limiter_enabled=False),(0,2))
    latest=replace(first,start_seconds=.5,duration_seconds=1.5,effects=replace(first.effects,mid_db=-12))
    active=None
    try:
        manager.prepare(first);assert entered.wait(3)
        manager.prepare(replace(first,start_seconds=.2,duration_seconds=1.8))
        manager.prepare(latest);release.set()
        active=wait_for(lambda:manager.take(latest))
        assert len(owners)==2 and all(p.poll() is not None for p in owners[0])
        assert owners[0].player.generation!=active.player.generation
        assert active._settings["start_seconds"]==.5
        assert active.eq_controller._desired[("equalizer@kw_mid","g")]==-12
        active.resume();wait_for(lambda:active.position_seconds()>.1)
    finally:
        release.set()
        if active:active.close()
        manager.close()
    assert not manager._thread.is_alive()
    assert all(not t.is_alive() for owner in owners for t in owner._threads)


def test_cancel_wait_releases_prepared_files_before_deletion(audio):
    paths,stems=audio
    manager=WarmTransport(lambda **kwargs:start_realtime_mix(paths,**kwargs),lambda:WaveOutputDevice(muted=True))
    request=PlaybackRequest(stems,0,2,0,0,AudioEffects(),(0,2))
    try:
        manager.prepare(request);wait_for(lambda:manager._cached)
        owner=manager._cached[1]
        manager.cancel(wait=True)
        assert all(p.poll() is not None for p in owner)
        assert not manager._cached and not manager._pending
        stems[0].path.unlink()  # Windows refuses this if FFmpeg still owns the input.
    finally:manager.close()
