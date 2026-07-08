from pathlib import Path

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import (
    AudioEffects,
    MixStem,
    _build_mix_filter,
    _clamp_db,
    _clamp_frequency,
    _clamp_q,
    _limiter_ceiling,
    safe_name,
)


def test_safe_name_replaces_unsafe_chars():
    assert safe_name("a b/c?.wav") == "a_b_c_.wav"


def test_safe_name_falls_back_when_empty():
    assert safe_name("***") == "audio"


def test_clamp_db_bounds():
    assert _clamp_db(99) == 18.0
    assert _clamp_db(-99) == -18.0


def test_clamp_frequency_bounds():
    assert _clamp_frequency(5) == 20.0
    assert _clamp_frequency(99999) == 20000.0


def test_clamp_q_bounds():
    assert _clamp_q(0.0) == 0.1
    assert _clamp_q(99.0) == 10.0


def test_limiter_ceiling_clamped():
    assert _limiter_ceiling(AudioEffects(limiter_ceiling=2.0)) == 1.0
    assert _limiter_ceiling(AudioEffects(limiter_ceiling=0.0)) == 0.05


def test_build_mix_filter_single_stem():
    args, filter_complex = _build_mix_filter(
        [MixStem("vocals", Path("v.wav"), 1.0)],
        0.0,
        10.0,
        0.0,
        0.0,
        AudioEffects(),
    )
    assert args[:2] == ["-ss", "0.000000"]
    assert "[outa]" in filter_complex


def test_build_mix_filter_adds_rubberband_for_pitch_tempo():
    _, filter_complex = _build_mix_filter(
        [MixStem("vocals", Path("v.wav"), 1.0)],
        0.0,
        10.0,
        0.0,
        0.0,
        AudioEffects(pitch_semitones=12.0, tempo_ratio=2.0),
    )
    assert "rubberband=tempo=2.000000:pitch=2.000000" in filter_complex


def test_build_mix_filter_adds_cut_filter_q_values():
    _, filter_complex = _build_mix_filter(
        [MixStem("vocals", Path("v.wav"), 1.0)],
        0.0,
        10.0,
        0.0,
        0.0,
        AudioEffects(high_pass_hz=120.0, low_pass_hz=8000.0, high_pass_q=1.4, low_pass_q=0.6),
    )
    assert "highpass=f=120.000:t=q:w=1.400" in filter_complex
    assert "lowpass=f=8000.000:t=q:w=0.600" in filter_complex


def test_settings_roundtrip(tmp_path):
    paths = AppPaths(tmp_path)
    paths.write_settings({"output_dir": "X", "delete_temp_after_render": True})
    loaded = paths.read_settings()
    assert loaded["output_dir"] == "X"
    assert loaded["delete_temp_after_render"] is True
