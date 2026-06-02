"""Pitch/tempo filter helpers.

Pure functions only (no I/O), so they are easy to unit test and safe to reuse
from the GUI worker threads.
"""

from __future__ import annotations


def pitch_scale_from_semitones(semitones: float) -> float:
    return 2.0 ** (float(semitones) / 12.0)


def build_rubberband_filter(tempo_ratio: float = 1.0, pitch_semitones: float = 0.0) -> str | None:
    """Build an ffmpeg `rubberband` filter string for pitch/tempo changes.

    - tempo_ratio: output speed multiplier (1.0 = unchanged, 2.0 = twice as fast).
    - pitch_semitones: pitch shift in semitones (preserves duration).
    Returns None when both are neutral so callers can skip the filter entirely.
    """
    tempo_ratio = max(min(float(tempo_ratio), 4.0), 0.25)
    pitch_scale = pitch_scale_from_semitones(max(min(float(pitch_semitones), 24.0), -24.0))
    if abs(tempo_ratio - 1.0) < 1e-6 and abs(pitch_scale - 1.0) < 1e-6:
        return None
    return f"rubberband=tempo={tempo_ratio:.6f}:pitch={pitch_scale:.6f}"
