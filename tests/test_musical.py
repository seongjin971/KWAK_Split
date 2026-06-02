import math

from backend.audio_processing.musical import (
    build_rubberband_filter,
    pitch_scale_from_semitones,
)


def test_pitch_scale_octave():
    assert math.isclose(pitch_scale_from_semitones(12), 2.0)
    assert math.isclose(pitch_scale_from_semitones(0), 1.0)


def test_rubberband_neutral_is_none():
    assert build_rubberband_filter(1.0, 0.0) is None


def test_rubberband_pitch_up_octave():
    flt = build_rubberband_filter(1.0, 12)
    assert flt is not None
    assert "rubberband=" in flt
    assert "pitch=2.000000" in flt
