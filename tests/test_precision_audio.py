"""Measured EQ range and source-time fade regressions using synthetic audio."""
from array import array
import json
import math
import shutil
import subprocess
from unittest.mock import patch

import pytest

from backend.audio_processing.equalizer import effect_biquads, response_db
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, ToolMissingError, _effect_filters, render_mix
from backend.project_store import FORMAT, VERSION, read_project, validate_edits
from test_audit_audio import session


def _ffmpeg(args):
    executable = shutil.which("ffmpeg")
    if not executable:
        pytest.skip("FFmpeg required")
    return subprocess.run(
        [executable, "-v", "error", *args], capture_output=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=20,
    ).stdout


def _rms(values):
    return math.sqrt(sum(value * value for value in values) / len(values))


def test_project_roundtrip_keeps_24db_and_existing_subcentisecond_data(tmp_path):
    # The UI uses two decimals; opening a pre-existing project must not erase
    # more precise values stored in the independently validated project schema.
    edits = validate_edits({"eq_low": 24, "eq_mid": -24, "eq_high": 24,
                            "selection_start": 1.234, "selection_end": 3.579,
                            "fade_in": .017, "fade_out": .083})
    path = tmp_path / "precision.kwaksplit"
    path.write_text(json.dumps({"format": FORMAT, "version": VERSION,
                                "source": "source.wav", "edits": edits}), encoding="utf-8")
    reopened = read_project(path)["edits"]
    for name in ("eq_low", "eq_mid", "eq_high", "selection_start", "selection_end", "fade_in", "fade_out"):
        assert reopened[name] == edits[name]


@pytest.mark.parametrize("gain", (-24, 24))
def test_source_effect_builder_honors_24db_for_each_band(session, gain):
    app = session.app
    for band in ("low", "mid", "high"):
        getattr(app, "eq_" + band + "_var").set(gain)
        assert getattr(app._build_audio_effects(), band + "_db") == gain


@pytest.mark.parametrize("gain", (-24, 24))
@pytest.mark.parametrize("band,shape,frequency,probe", (
    ("low", "Low Shelf", 180, 80),
    ("mid", "Bell", 1000, 1000),
    ("high", "High Shelf", 6000, 10000),
))
def test_24db_ffmpeg_audio_matches_display_curve(band, shape, frequency, probe, gain):
    effects = AudioEffects(**{band + "_db": gain, band + "_shape": shape,
                              band + "_freq": frequency, band + "_q": .8},
                           sample_rate=48000, limiter_enabled=False)
    raw = _ffmpeg(["-f", "lavfi", "-i",
                   f"aevalsrc=.001*sin(2*PI*{probe}*t):s=48000:d=2",
                   "-af", ",".join(_effect_filters(effects)), "-f", "f64le", "-"])
    samples = array("d")
    samples.frombytes(raw)
    measured = 20 * math.log10(_rms(samples[-24000:]) / (.001 / math.sqrt(2)))
    expected = response_db(effect_biquads(effects), probe, 48000)
    assert measured == pytest.approx(expected, abs=.07)
    if shape == "Bell":
        assert measured == pytest.approx(gain, abs=.07)


@pytest.mark.parametrize("speed,fade_in,fade_out,duration", (
    (.5, .8, .4, 4), (1, .8, .4, 4), (2, .8, .4, 4),
    (1, 10, 10, 1),
))
def test_exported_fades_follow_displayed_source_time_at_each_speed(session, speed, fade_in, fade_out, duration):
    app = session.app
    selection_start = 1.0
    selection_end = selection_start + duration
    app.selection_start_var.set(selection_start)
    app.selection_end_var.set(selection_end)
    app.tempo_percent_var.set(speed * 100)
    app.fade_in_var.set(fade_in)
    app.fade_out_var.set(fade_out)
    app.limiter_enabled_var.set(False)
    app.render_wav()
    session.wait_idle()
    samples = array("d")
    samples.frombytes(_ffmpeg(["-i", str(app.result_files[0]), "-ac", "1", "-f", "f64le", "-"]))
    rate = app.sample_rate_var.get()
    assert len(samples) / rate == pytest.approx(duration / speed, abs=.12)

    def envelope(source_offset):
        # The waveform is in original-source coordinates. Speed changes elapsed
        # playback time but does not move the displayed fade's source endpoint.
        center = source_offset / speed * rate
        radius = max(1, round(.02 / speed * rate))
        return _rms(samples[round(center) - radius:round(center) + radius])

    reference = envelope(duration / 2)
    effective_in = min(fade_in, duration / 2)
    effective_out = min(fade_out, duration / 2)
    offsets = [effective_in * fraction for fraction in (.25, .5, .75)]
    offsets += [duration - effective_out * fraction for fraction in (.75, .5, .25)]
    for offset in offsets:
        expected = app._fade_display_gain(selection_start + offset, selection_start, selection_end)
        assert envelope(offset) / reference == pytest.approx(expected, abs=.07)


def _decode(path):
    samples = array("d")
    samples.frombytes(_ffmpeg(["-i", str(path), "-ac", "1", "-f", "f64le", "-"]))
    return samples


@pytest.mark.parametrize("start,duration", (
    (1.4, 3.6),  # Resume halfway through the full 0.8-second fade in.
    (2.2, 2.8),  # Seek past fade in: no new fade starts at the cursor.
    (4.8, .2),   # Resume halfway through the full 0.4-second fade out.
    (1, 1.5),    # A shorter fallback excerpt does not acquire an early fade out.
    (1.2, .3),   # A short excerpt entirely within fade in must not reclamp it.
))
def test_seeked_and_partial_audio_equals_corresponding_full_export_segment(session, start, duration):
    stems = [MixStem("source", session.source, 1)]
    # Match the generated source rate so that a resampler's boundary padding
    # does not obscure an otherwise exact source-time envelope comparison.
    effects = AudioEffects(sample_rate=48000, limiter_enabled=False)
    full_path = session.paths.output / "full-fades.wav"
    part_path = session.paths.output / "part-fades.wav"
    render_mix(session.paths, stems, full_path, 1, 4, .8, .4, effects=effects)
    render_mix(session.paths, stems, part_path, start, duration, .8, .4, effects=effects, fade_bounds=(1, 5))
    full = _decode(full_path)
    part = _decode(part_path)
    offset = round((start - 1) * effects.sample_rate)
    expected = full[offset:offset + len(part)]
    assert len(part) == round(duration * effects.sample_rate)
    assert len(part) == len(expected)
    # PCM quantization and the fade's split sample boundary allow tiny rounding
    # differences; the signal/envelope otherwise matches the complete export.
    assert max(abs(actual - wanted) for actual, wanted in zip(part, expected)) < .000002


@pytest.mark.parametrize("speed", (.5, 2))
def test_seeked_fade_envelope_matches_full_export_at_changed_speed(session, speed):
    stems = [MixStem("source", session.source, 1)]
    effects = AudioEffects(sample_rate=48000, tempo_ratio=speed, limiter_enabled=False)
    full_path = session.paths.output / "full-speed-fades.wav"
    part_path = session.paths.output / "part-speed-fades.wav"
    render_mix(session.paths, stems, full_path, 1, 4, .8, .4, effects=effects)
    render_mix(session.paths, stems, part_path, 2.5, 2.5, .8, .4, effects=effects, fade_bounds=(1, 5))
    full = _decode(full_path)
    part = _decode(part_path)
    rate = effects.sample_rate

    def envelope(samples, source_offset):
        center = round(source_offset / speed * rate)
        radius = max(1, round(.02 / speed * rate))
        return _rms(samples[center - radius:center + radius])

    reference = envelope(full, 2)
    # Leave at least 0.25 output seconds for the newly started time stretcher
    # to settle before comparing its steady signal and ending fade envelope.
    for source_offset in (.5, .8, 2.15, 2.3):
        actual = envelope(part, source_offset)
        expected = envelope(full, 1.5 + source_offset)
        # Rubber Band starts on a different input window after seeking, so
        # compare the audible envelope rather than exact waveform phase.
        assert actual / reference == pytest.approx(expected / reference, abs=.07)


def test_shortened_fallback_preview_uses_full_selection_fade_bounds(session):
    app = session.app
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    app.fade_in_var.set(.8)
    app.fade_out_var.set(.4)
    app.limiter_enabled_var.set(False)
    app.loop_var.set(False)
    app.render_wav()
    session.wait_idle()
    full = _decode(app.result_files[0])
    # Exercise the actual fallback worker with a short equivalent of its usual
    # 30-second cap, without sending any sound to the user's audio device.
    app._warm_transport.close()
    app._warm_transport.unavailable="native output unavailable for fallback check"
    with patch("StemSamplePrep.PREVIEW_SECONDS", 1.5), \
            patch("StemSamplePrep.start_realtime_mix", side_effect=ToolMissingError("FFplay unavailable")), \
            patch("StemSamplePrep.winsound.PlaySound"):
        app.toggle_playback()
        session.wait_idle()
        part = _decode(app.current_preview_file)
        app.stop_preview(show_status=False)
    assert len(part) == round(1.5 * app.sample_rate_var.get())
    assert max(abs(actual - wanted) for actual, wanted in zip(part, full)) < .000002
