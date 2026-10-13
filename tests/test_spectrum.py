"""Measure actual processed PCM and the live player tap using generated audio."""
from array import array
from dataclasses import replace
import math
import queue
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from backend.audio_processing import spectrum
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import (
    AudioEffects, MixStem, _build_mix_filter, analyze_rendered_preview,
    require_ffmpeg, render_mix, start_realtime_mix,
)
from backend.audio_processing.spectrum import (
    FFT_SIZE, FLOOR_DB, FREQUENCIES, SAMPLE_RATE, SpectrumAnalyzer, analyze_pcm,
)


def sine_pcm(amplitude=.1, right=1):
    frequency=round(1000*FFT_SIZE/SAMPLE_RATE)*SAMPLE_RATE/FFT_SIZE
    samples=array("h")
    for i in range(FFT_SIZE):
        value=round(amplitude*32767*math.sin(2*math.pi*frequency*i/SAMPLE_RATE))
        samples.extend((value,round(value*right)))
    return samples.tobytes()


@pytest.mark.parametrize("right,offset",[(1,0),(-1,0),(0,-3.0103)])
def test_calibrated_stereo_spectrum_does_not_cancel_antiphase(right,offset):
    levels=analyze_pcm(sine_pcm(.1,right))
    assert max(levels)==pytest.approx(-20+offset,abs=.02)
    assert FREQUENCIES[levels.index(max(levels))]==pytest.approx(1000,rel=.03)
    boosted=analyze_pcm(sine_pcm(.2,right))
    assert max(boosted)-max(levels)==pytest.approx(6.0206,abs=.02)
    assert analyze_pcm(bytes(FFT_SIZE*4))==(FLOOR_DB,)*len(FREQUENCIES)


def wait_for(predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(.02)
    raise AssertionError("Timed out waiting for analyzed audio")


def test_analysis_is_bounded_and_never_returns_a_future_frame():
    analyzer=SpectrumAnalyzer()
    try:
        analyzer.feed(sine_pcm())
        frame=wait_for(lambda:analyzer.frame_at(1))
        assert analyzer.frame_at(frame.seconds-.001) is None
        assert analyzer.frame_at(frame.seconds)==frame
        for _ in range(100):analyzer.feed(sine_pcm())
        assert len(analyzer._buffer)<=FFT_SIZE*4
        assert analyzer._queue.qsize()<=2 and len(analyzer._frames)<=64
    finally:
        analyzer.close();analyzer.join()
    assert analyzer.frame_at(100) is None
    assert not analyzer._thread.is_alive()


def test_close_wakes_an_idle_analyzer_without_waiting_for_a_poll_timeout(monkeypatch):
    waiting=threading.Event()
    class BlockingQueue(queue.Queue):
        def get(self,block=True,timeout=None):
            waiting.set()
            # Disable timeout polling so only an explicit wake can end the wait.
            return super().get(block=block)
    monkeypatch.setattr(spectrum,"queue",SimpleNamespace(
        Queue=BlockingQueue,Empty=queue.Empty,Full=queue.Full))
    analyzer=SpectrumAnalyzer()
    try:
        assert waiting.wait(2)
        analyzer.close();analyzer.join(timeout=1)
        assert not analyzer._thread.is_alive()
        assert not analyzer.error and analyzer.frame_at(1) is None
    finally:
        analyzer.close()
        if analyzer._thread.is_alive():analyzer._queue.put_nowait(None)
        analyzer.join(timeout=1)


@pytest.fixture
def tone(tmp_path):
    paths=AppPaths(tmp_path);paths.ensure()
    source=tmp_path/"tone.wav"
    subprocess.run([str(require_ffmpeg(paths)),"-v","error","-f","lavfi","-i",
        "aevalsrc=.04*sin(2*PI*1000*t)|.04*sin(2*PI*1000*t):s=44100:d=4",
        "-c:a","pcm_f32le",str(source)],check=True,capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return paths,source


def filtered_pcm(paths,stems,effects,start=0,duration=2,fade_in=0,fade_out=0):
    inputs,filters=_build_mix_filter(stems,start,duration,fade_in,fade_out,effects)
    return subprocess.run([str(require_ffmpeg(paths)),"-v","error",*inputs,
        "-filter_complex",filters,"-map","[outa]","-ar",str(SAMPLE_RATE),"-ac","2",
        "-f","s16le","-"],check=True,capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW).stdout


def filtered_levels(paths,stems,effects,**kwargs):
    raw=filtered_pcm(paths,stems,effects,**kwargs)
    midpoint=(len(raw)//2//4)*4
    return analyze_pcm(raw[midpoint:midpoint+FFT_SIZE*4])


@pytest.mark.parametrize("gain",[-12,12])
def test_spectrum_measures_eq_cut_boost_and_stem_gain_in_final_pcm(tone,gain):
    paths,source=tone;stems=[MixStem("source",source,1)]
    effects=AudioEffects(mid_freq=1000,mid_db=0,sample_rate=44100,limiter_enabled=False)
    flat=filtered_levels(paths,stems,effects)
    adjusted=filtered_levels(paths,stems,replace(effects,mid_db=gain))
    assert max(adjusted)-max(flat)==pytest.approx(gain,abs=.12)
    quiet=filtered_levels(paths,[MixStem("source",source,.5)],effects)
    assert max(quiet)-max(flat)==pytest.approx(-6.0206,abs=.12)


def test_spectrum_measures_pass_filters_pitch_and_limiter(tone):
    paths,source=tone;stems=[MixStem("source",source,1)]
    effects=AudioEffects(sample_rate=44100,limiter_enabled=False)
    flat=filtered_levels(paths,stems,effects)
    filtered=filtered_levels(paths,stems,replace(effects,low_pass_hz=300,low_pass_slope=48))
    assert max(filtered)<max(flat)-60
    pitched=filtered_levels(paths,stems,replace(effects,pitch_semitones=12))
    assert FREQUENCIES[pitched.index(max(pitched))]==pytest.approx(2000,rel=.06)
    limited=filtered_levels(paths,stems,replace(effects,mid_db=24,limiter_enabled=True,limiter_ceiling=.1))
    assert max(limited)<-19


@pytest.mark.parametrize("gain,speed",[(0,1),(-12,.5),(12,2)])
def test_live_tap_uses_player_clock_and_processed_audio(tone,monkeypatch,gain,speed):
    paths,source=tone;monkeypatch.setenv("SDL_AUDIODRIVER","dummy")
    effects=AudioEffects(mid_freq=1000,mid_db=gain,tempo_ratio=speed,limiter_enabled=False)
    raw=filtered_pcm(paths,[MixStem("source",source,1)],effects,start=.2,duration=1.5)
    playback=start_realtime_mix(paths,[MixStem("source",source,1)],.2,1.5,0,0,effects)
    try:
        frame=wait_for(lambda:playback.spectrum_frame())
        offset=round(frame.seconds*SAMPLE_RATE-FFT_SIZE/2)*4
        expected=max(analyze_pcm(raw[offset:offset+FFT_SIZE*4]))
        assert max(frame.levels)==pytest.approx(expected,abs=.25)
        assert frame.seconds<=playback.position_seconds()
        wait_for(lambda:playback._clock is not None)
        assert playback._sent_frames/SAMPLE_RATE-playback.position_seconds()<.45
        assert playback[0].poll() is None
        assert not playback.error and not playback.spectrum.error
    finally:playback.close()
    assert all(process.poll() is not None for process in playback)
    assert all(not thread.is_alive() for thread in playback._threads)
    assert not playback.spectrum._thread.is_alive()


def test_rendered_fallback_analyzes_actual_wav_and_stops(tone):
    paths,source=tone;rendered=paths.output/"rendered.wav"
    effects=AudioEffects(mid_freq=1000,mid_db=-12,limiter_enabled=False,sample_rate=48000,bit_depth=24)
    render_mix(paths,[MixStem("source",source,1)],rendered,0,2,0,0,effects=effects)
    playback=analyze_rendered_preview(paths,rendered)
    try:
        frame=wait_for(lambda:playback.spectrum_frame())
        expected=max(filtered_levels(paths,[MixStem("source",source,1)],effects))
        assert max(frame.levels)==pytest.approx(expected,abs=.25)
    finally:playback.close()
    assert all(process.poll() is not None for process in playback)


def test_analyzer_failure_cannot_break_audio_forwarding(tone,monkeypatch):
    paths,source=tone;monkeypatch.setenv("SDL_AUDIODRIVER","dummy")
    def fail(_pcm):raise RuntimeError("injected analyzer failure")
    playback=start_realtime_mix(paths,[MixStem("source",source,1)],0,.7,0,0)
    playback.spectrum.feed=fail
    try:
        wait_for(lambda:playback[0].poll() is not None)
        assert playback[0].returncode==0
        assert playback.spectrum.error=="injected analyzer failure"
        assert not playback.error
    finally:playback.close()
