"""Actual FFmpeg commands and PCM measurements; silent SDL output only."""
from array import array
from dataclasses import replace
import math
import subprocess
import time

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import (
    AudioEffects, MixStem, _build_mix_filter, _live_eq_plan, require_ffmpeg, start_realtime_mix,
)
from backend.audio_processing.live_eq import LiveEqController
from backend.audio_processing.spectrum import analyze_pcm, FFT_SIZE, SAMPLE_RATE
from test_spectrum import wait_for


@pytest.fixture
def audio(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    paths = AppPaths(tmp_path); paths.ensure()
    source = tmp_path / "generated.wav"
    subprocess.run([str(require_ffmpeg(paths)), "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=.04*sin(2*PI*1000*t)|.04*sin(2*PI*1000*t):s=44100:d=16",
                    "-c:a", "pcm_f32le", str(source)], check=True, capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return paths, [MixStem("source", source, 1)]


def pcm(audio, effects, live=False):
    paths, stems = audio
    inputs, filters = _build_mix_filter(stems, 0, 2, 0, 0, effects,
        live_eq_filters=_live_eq_plan(effects)[0] if live else None)
    return subprocess.run([str(require_ffmpeg(paths)), "-v", "error", *inputs,
        "-filter_complex", filters, "-map", "[outa]", "-ar", "44100", "-ac", "2",
        "-f", "s16le", "-"], check=True, capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW).stdout


def level(audio, effects):
    raw = pcm(audio, effects)
    midpoint = (len(raw)//2//4)*4
    return max(analyze_pcm(raw[midpoint:midpoint+FFT_SIZE*4]))


def expect_level(playback, expected, timeout=2):
    def ready():
        frame = playback.spectrum_frame()
        return frame if frame and abs(max(frame.levels)-expected) < .2 else None
    return wait_for(ready, timeout)


@pytest.mark.parametrize("effects", [
    AudioEffects(limiter_enabled=False),
    AudioEffects(mid_db=12, mid_q=2, low_shape="Low Shelf", low_db=-5, high_db=.02),
    AudioEffects(low_db=5, high_db=-8, high_shape="High Shelf", sample_rate=48000),
    AudioEffects(high_pass_hz=800, high_pass_q=1.1, high_pass_slope=48,
                 low_pass_hz=4000, low_pass_q=.5, low_pass_slope=36),
    AudioEffects(mid_db=6, pitch_semitones=3, tempo_ratio=1.5),
])
def test_live_graph_matches_export_filter_pcm(audio, effects):
    live, exported = array("h"), array("h")
    live.frombytes(pcm(audio, effects, True)); exported.frombytes(pcm(audio, effects))
    assert len(live) == len(exported)
    assert max(abs(a-b) for a,b in zip(live, exported)) <= 2


def test_gain_updates_without_restarts_gaps_or_large_transients(audio):
    effects = AudioEffects(limiter_enabled=False)
    playback = start_realtime_mix(*audio, 0, 16, 0, 0, effects)
    chunks, timings, clocks = [], [], []
    try:
        expect_level(playback, level(audio, effects))
        wait_for(lambda:playback.position_seconds() >= .65)
        processes = tuple(playback)
        feed = playback.spectrum.feed
        def capture(data):
            chunks.append(data); feed(data)
        playback.spectrum.feed = capture
        for gain in (12, -12, 0):
            updated = replace(effects, mid_db=gain)
            expected = level(audio, updated)
            started = time.monotonic()
            assert playback.update_eq(updated)
            expect_level(playback, expected)
            timings.append(round(time.monotonic()-started, 3))
            clocks.append(playback.position_seconds())
            assert tuple(playback) == processes and all(p.poll() is None for p in processes)
            assert not playback.eq_controller.error
        assert clocks == sorted(clocks)
        assert max(timings) < .8, timings
        samples = array("h"); samples.frombytes(b"".join(chunks)); left = samples[::2]
        rms = [math.sqrt(sum(v*v for v in left[i:i+512])/512) for i in range(0,len(left)-512,512)]
        assert min(rms) > 100  # Even the -12 dB section is continuously audible.
        assert max(abs(b-a) for a,b in zip(left,left[1:])) < 1800
        print({"settle_seconds":timings,"minimum_rms":min(rms),
               "maximum_sample_step":max(abs(b-a) for a,b in zip(left,left[1:]))})
    finally:
        playback.close()
    assert not playback.eq_controller._thread.is_alive()
    assert all(p.poll() is not None for p in playback)


@pytest.mark.parametrize("effects,updated", [
    (AudioEffects(mid_db=6), AudioEffects(mid_db=-9,mid_freq=1500,mid_q=2.3)),
    (AudioEffects(low_shape="Low Shelf",low_db=6),
     AudioEffects(low_shape="Low Shelf",low_db=-9,low_freq=1300,low_q=1.3)),
    (AudioEffects(high_shape="High Shelf",high_db=-8),
     AudioEffects(high_shape="High Shelf",high_db=5,high_freq=1200,high_q=1.3)),
    (AudioEffects(high_pass_hz=300,high_pass_slope=48),
     AudioEffects(high_pass_hz=1100,high_pass_q=.5,high_pass_slope=48)),
    (AudioEffects(low_pass_hz=9000,low_pass_slope=36,sample_rate=48000),
     AudioEffects(low_pass_hz=950,low_pass_q=.9,low_pass_slope=36,sample_rate=48000)),
    (AudioEffects(tempo_ratio=.5), AudioEffects(tempo_ratio=.5,mid_db=9)),
    (AudioEffects(tempo_ratio=2,pitch_semitones=3),
     AudioEffects(tempo_ratio=2,pitch_semitones=3,mid_db=-9)),
])
def test_frequency_q_shelves_passes_and_speed_share_export_result(audio, effects, updated):
    playback = start_realtime_mix(*audio, 0, 16, 0, 0, effects)
    try:
        expect_level(playback, level(audio,effects))
        assert playback.update_eq(updated)
        # Rubber Band carries analysis/lookahead state, especially at half speed.
        expect_level(playback, level(audio,updated), timeout=4)
        assert not playback.eq_controller.error
        assert all(p.poll() is None for p in playback)
    finally: playback.close()


def test_fast_drag_keeps_latest_value_and_rejects_non_eq_changes(audio):
    effects = AudioEffects(limiter_enabled=False)
    playback = start_realtime_mix(*audio,0,16,0,0,effects)
    try:
        expect_level(playback, level(audio,effects))
        for i in range(60):
            updated = replace(effects, mid_freq=800+i*8, mid_db=-10+i/3,mid_q=.5+i/60)
            assert playback.update_eq(updated)
            time.sleep(.004)
        expected = level(audio,updated)
        expect_level(playback,expected)
        wait_for(lambda:playback.eq_controller.applied_revision == playback.eq_controller.revision)
        assert playback.update_eq(replace(updated, mid_shape="Low Shelf"))
        assert playback.update_eq(replace(updated, high_pass_hz=50))
        assert not playback.update_eq(replace(updated, tempo_ratio=1.2))
        assert all(p.poll() is None for p in playback)
    finally: playback.close()


@pytest.mark.parametrize("before,after", [
    (AudioEffects(low_shape="Low Shelf",low_db=-9,low_freq=1500),
     AudioEffects(low_shape="High Pass",low_freq=1500,high_pass_hz=1500,high_pass_slope=24)),
    (AudioEffects(high_shape="High Shelf",high_db=-9,high_freq=1500),
     AudioEffects(high_shape="Low Pass",high_freq=1500,low_pass_hz=1500,low_pass_slope=48)),
    (AudioEffects(mid_db=-9), AudioEffects(mid_shape="Low Shelf",mid_db=-9)),
    (AudioEffects(), AudioEffects(high_pass_hz=400,high_pass_slope=36)),
    (AudioEffects(low_pass_hz=1200,low_pass_slope=24),AudioEffects()),
    *[(AudioEffects(high_pass_hz=700,high_pass_slope=a,low_pass_hz=1600,low_pass_slope=a),
       AudioEffects(high_pass_hz=700,high_pass_slope=b,low_pass_hz=1600,low_pass_slope=b))
      for a,b in ((12,48),(48,12),(24,36),(36,24))],
    (AudioEffects(high_shape="High Shelf",high_db=-9,sample_rate=48000,tempo_ratio=.5),
     AudioEffects(high_shape="Low Pass",low_pass_hz=1200,low_pass_slope=36,sample_rate=48000,tempo_ratio=.5)),
])
def test_mode_and_slope_changes_match_export_without_restarting(audio,before,after):
    expected_before,expected_after=level(audio,before),level(audio,after)
    playback=start_realtime_mix(*audio,0,16,0,0,before)
    try:
        expect_level(playback,expected_before)
        pids=[p.pid for p in playback]
        for effects,expected in ((after,expected_after),(before,expected_before)):
            assert playback.update_eq(effects)
            wait_for(lambda:playback.eq_controller.applied_revision==playback.eq_controller.revision,4)
            expect_level(playback,expected,4)
            assert [p.pid for p in playback]==pids and all(p.poll() is None for p in playback)
            assert not playback.eq_controller.error
    finally:playback.close()


@pytest.mark.parametrize("command_delay",[0,.06])
def test_mode_transition_crossfades_without_dry_level_spike(audio,monkeypatch,command_delay):
    before=AudioEffects(low_shape="Low Shelf",low_db=-18,low_freq=2500,limiter_enabled=False)
    after=AudioEffects(low_shape="High Pass",high_pass_hz=800,high_pass_slope=36,
                       high_pass_q=.55,limiter_enabled=False)
    expected_peak=0
    for effects in (before,after):
        samples=array("h");samples.frombytes(pcm(audio,effects))
        expected_peak=max(expected_peak,max(abs(n) for n in samples[FFT_SIZE*2:]))
    playback=start_realtime_mix(*audio,0,16,0,0,before);chunks=[]
    command=playback.eq_controller._command
    def delayed_command(channel,target,parameter,value):
        result=command(channel,target,parameter,value)
        if target=="amix@kw_eq_crossfade" and command_delay:time.sleep(command_delay)
        return result
    monkeypatch.setattr(playback.eq_controller,"_command",delayed_command)
    try:
        wait_for(lambda:playback.position_seconds()>.7)
        feed=playback.spectrum.feed
        def capture(data):chunks.append(data);feed(data)
        playback.spectrum.feed=capture
        for effects in (after,before):
            assert playback.update_eq(effects)
            expect_level(playback,level(audio,effects),4)
        samples=array("h");samples.frombytes(b"".join(chunks))
        assert max(abs(n) for n in samples) <= expected_peak*1.1+2
        assert max(abs(b-a) for a,b in zip(samples[::2],samples[2::2])) < 500
        assert all(p.poll() is None for p in playback) and not playback.eq_controller.error
    finally:playback.close()


def test_frequency_gain_q_edits_follow_each_new_active_bank(audio):
    effects=AudioEffects(limiter_enabled=False)
    playback=start_realtime_mix(*audio,0,16,0,0,effects)
    try:
        expect_level(playback,level(audio,effects))
        pids=[p.pid for p in playback]
        for shape in ("Low Shelf","Bell"):
            effects=replace(effects,mid_shape=shape)
            assert playback.update_eq(effects)
            wait_for(lambda:playback.eq_controller.applied_revision==playback.eq_controller.revision,4)
            effects=replace(effects,mid_db=-9 if shape=="Low Shelf" else 9,
                            mid_freq=1200 if shape=="Low Shelf" else 950,mid_q=1.7)
            assert playback.update_eq(effects)
            expect_level(playback,level(audio,effects),4)
            assert [p.pid for p in playback]==pids and not playback.eq_controller.error
    finally:playback.close()


def test_rapid_mode_slope_switches_apply_last_state_and_release_worker(audio):
    before=AudioEffects()
    playback=start_realtime_mix(*audio,0,16,0,0,before)
    try:
        wait_for(lambda:playback.position_seconds()>.3)
        for i in range(36):
            after=replace(before,low_shape="Low Shelf" if i%2 else "High Pass",
                          low_db=-(i%12) if i%2 else 0,high_pass_hz=0 if i%2 else 300+i*10,
                          high_pass_slope=(12,24,36,48)[i%4])
            assert playback.update_eq(after)
            time.sleep(.012)
        wait_for(lambda:playback.eq_controller.applied_revision==playback.eq_controller.revision,4)
        expect_level(playback,level(audio,after),4)
        assert not playback.eq_controller.error
    finally:playback.close()
    assert not playback.eq_controller._thread.is_alive()
    assert all(p.poll() is not None for p in playback)


def test_command_failure_preserves_audio_and_is_reported_once(audio, monkeypatch):
    effects = AudioEffects()
    playback = start_realtime_mix(*audio,0,16,0,0,effects)
    try:
        expect_level(playback,level(audio,effects))
        def fail(*args): raise TimeoutError("injected command timeout")
        monkeypatch.setattr(playback.eq_controller,"_command",fail)
        assert playback.update_eq(replace(effects,mid_db=8))
        wait_for(lambda:playback.eq_controller.error)
        assert playback.take_eq_error() == "injected command timeout"
        assert playback.take_eq_error() == ""
        assert not playback.update_eq(replace(effects,mid_db=6))
        assert all(p.poll() is None for p in playback)
    finally: playback.close()


def test_stop_interrupts_an_unanswered_command():
    controller = LiveEqController({("equalizer@kw_mid","g"):0})
    controller.start()
    assert controller.submit({("equalizer@kw_mid","g"):12})
    time.sleep(.04)
    controller.close();controller.join()
    assert not controller._thread.is_alive() and not controller.error
