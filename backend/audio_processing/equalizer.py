"""Digital EQ response shared with FFmpeg's two-pole filters.

RBJ coefficients: https://www.w3.org/TR/audio-eq-cookbook/
FFmpeg filter parameters: https://ffmpeg.org/ffmpeg-filters.html#highpass
Pass slope selects the number of poles; Q independently scales resonance.
"""
from __future__ import annotations

import cmath
import math

PASS_SLOPES = (12, 24, 36, 48)


def pass_section_qs(slope: int, q: float) -> tuple[float, ...]:
    if slope not in PASS_SLOPES:
        raise ValueError("Filter slope must be 12, 24, 36 or 48 dB/oct.")
    order = slope // 6
    # At Q=sqrt(1/2), the complete cascade is Butterworth, including its
    # -3 dB cutoff. Repeating identical Q=.707 filters would move that cutoff.
    scale = max(0.1, min(float(q), 10)) * math.sqrt(2)
    return tuple(round(scale / (2 * math.cos((2*k + 1) * math.pi / (2*order))), 3)
                 for k in range(order // 2))


def biquad(shape: str, frequency: float, q: float, gain: float = 0, rate: int = 48000):
    frequency = max(20, min(float(frequency), 20000, rate * .499))
    w = 2 * math.pi * frequency / rate
    c, alpha = math.cos(w), math.sin(w) / (2 * max(q, .001))
    a = 10 ** (gain / 40)
    if shape == "High Pass":
        b = ((1+c)/2, -(1+c), (1+c)/2)
        d = (1+alpha, -2*c, 1-alpha)
    elif shape == "Low Pass":
        b = ((1-c)/2, 1-c, (1-c)/2)
        d = (1+alpha, -2*c, 1-alpha)
    elif shape in ("Low Shelf", "High Shelf"):
        # FFmpeg's bass/treble variants use sqrt(2*A), unlike the RBJ
        # lowshelf/highshelf variants' 2*sqrt(A). Keep legacy audio unchanged.
        t = math.sqrt(2 * a) * alpha
        if shape == "Low Shelf":
            b = (a*((a+1)-(a-1)*c+t), 2*a*((a-1)-(a+1)*c), a*((a+1)-(a-1)*c-t))
            d = ((a+1)+(a-1)*c+t, -2*((a-1)+(a+1)*c), (a+1)+(a-1)*c-t)
        else:
            b = (a*((a+1)+(a-1)*c+t), -2*a*((a-1)+(a+1)*c), a*((a+1)+(a-1)*c-t))
            d = ((a+1)-(a-1)*c+t, 2*((a-1)-(a+1)*c), (a+1)-(a-1)*c-t)
    else:
        b = (1+alpha*a, -2*c, 1-alpha*a)
        d = (1+alpha/a, -2*c, 1-alpha/a)
    return tuple(v/d[0] for v in b), tuple(v/d[0] for v in d)


def effect_biquads(effects):
    sections = []
    for band in ("low", "mid", "high"):
        gain = getattr(effects, band + "_db")
        if abs(gain) >= .05:
            sections.append(biquad(getattr(effects, band + "_shape"),
                                   getattr(effects, band + "_freq"),
                                   round(getattr(effects, band + "_q"), 3), gain, effects.sample_rate))
    for key, shape in (("high_pass", "High Pass"), ("low_pass", "Low Pass")):
        freq = getattr(effects, key + "_hz")
        if freq > 0:
            for q in pass_section_qs(getattr(effects, key + "_slope"), getattr(effects, key + "_q")):
                sections.append(biquad(shape, freq, q, rate=effects.sample_rate))
    return sections


def response_db(sections, frequency, rate=48000):
    z = cmath.exp(-2j * math.pi * min(frequency, rate * .499999) / rate)
    result = 0.0
    for b, a in sections:
        magnitude = abs((b[0] + b[1]*z + b[2]*z*z) / (a[0] + a[1]*z + a[2]*z*z))
        result += 20 * math.log10(max(magnitude, 1e-15))
    return result
