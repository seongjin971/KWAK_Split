"""UI-independent contracts for the approved compact desktop editor."""
import math
from backend.window_bounds import window_limits

MAX_STEM_PERCENT = 100 * 10 ** (12 / 20)
FADER_UNITY = .67
EQ_GAIN_LIMIT = 24.0
TIME_QUANTUM = .01


def selection_step(view_span):
    """About one hundred wheel steps per visible timeline, on readable intervals."""
    target=max(TIME_QUANTUM, float(view_span)/100)
    decade=10 ** math.floor(math.log10(target))
    return max(TIME_QUANTUM, min((1,2,5,10),key=lambda n:abs(math.log(target/(n*decade))))*decade)


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
    return window_limits(work_width,work_height,scale,(round(16*scale),round(48*scale))).initial_size
