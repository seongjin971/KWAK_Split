"""UI-independent contracts for the approved compact desktop editor."""
import math

MAX_STEM_PERCENT = 100 * 10 ** (12 / 20)
FADER_UNITY = .67


def volume_to_position(volume):
    if volume <= 0:
        return 0.0
    db = 20 * math.log10(volume / 100)
    return max(0, min(1, FADER_UNITY + db * (FADER_UNITY / 60 if db <= 0 else (1-FADER_UNITY) / 12)))


def position_to_volume(position):
    position = max(0, min(1, position))
    if position == 0:
        return 0.0
    db = (position-FADER_UNITY) * (60/FADER_UNITY if position <= FADER_UNITY else 12/(1-FADER_UNITY))
    return 100 * 10 ** (db/20)


def volume_label(volume):
    if volume <= 0:
        return "−∞ dB"
    db = 20 * math.log10(volume / 100)
    return ("+" if db > .05 else "") + f"{db:.1f} dB"


def initial_window(work_width, work_height, scale=1):
    """All inputs/output are device pixels; allow for window decorations."""
    width = min(round(1000 * scale), max(320, work_width - round(48*scale)))
    height = min(round(700 * scale), max(320, work_height - round(76*scale)))
    return width, height
