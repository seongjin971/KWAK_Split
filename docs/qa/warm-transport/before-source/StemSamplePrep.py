from __future__ import annotations

import logging
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import winsound
import ctypes
from ctypes import wintypes
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from backend.app_paths import AppPaths
from backend.ui_helpers import ScrollableFrame, ToolTip
from backend.workspace_features import StemRangeError, WorkspaceFeatures
from backend.compact_ui import CompactInterface
from backend.compact_widgets import enable_dpi_awareness
from backend.compact_model import EQ_GAIN_LIMIT
from backend.audio_processing import STEMS
from backend.audio_processing.ffmpeg_tools import (
    AudioEffects,
    AudioProcessingError,
    MixStem,
    OperationCancelled,
    ToolMissingError,
    convert_to_work_wav,
    extract_audio_range,
    read_duration,
    render_mix,
    safe_name,
    start_realtime_mix,
    analyze_rendered_preview,
    waveform_peaks,
    stereo_waveform_peaks,
    audio_channels,
)
from backend.audio_processing.separation import StemSeparator

PREVIEW_SECONDS = 30.0
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}
STEM_PRESETS = [
    ("Full Mix", set(STEMS)),
    ("Vocal Only", {"vocals"}),
    ("Instrumental", {"drums", "bass", "other"}),
    ("No Drums", {"vocals", "bass", "other"}),
    ("No Bass", {"vocals", "drums", "other"}),
]
EQ_SHAPES = ("Bell", "Low Shelf", "High Shelf")
CTRL_MASK = 0x0004
STEM_LABELS = {
    "vocals": "Vocal",
    "drums": "Drums",
    "bass": "Bass",
    "other": "Other",
}
STEM_COLORS = {
    "vocals": "#5aa7ff",
    "drums": "#9b6cff",
    "bass": "#42d6d0",
    "other": "#bdefff",
}
LOADING_MESSAGES = (
    "You stretch, I’ll unmix.",
    "Separating the band. They’re not happy.",
    "Finding the drummer. Please wait.",
    "Vocals are trying to escape...",
    "Bass refuses to leave the track.",
    "Negotiating with the waveform...",
    "Tiny robots are arguing about stems.",
    "This mix has trust issues.",
    "Asking the snare to calm down...",
    "Your song is in surgery.",
    "Please don’t feed the AI.",
    "The AI is pretending to know music theory.",
    "Almost there. Probably.",
    "Stretch your neck. I’ll split the track.",
    "Grab some water. The bass is still hiding.",
    "Unmixing. Please clap quietly.",
    "Extracting musical DNA...",
    "Kick and bass are fighting again.",
    "The waveform is overthinking it.",
    "Teaching the AI what a hi-hat is...",
    "The vocals asked for privacy.",
    "Drums are being difficult today.",
    "Bass detected. Confidence: maybe.",
    "The AI is listening very dramatically.",
    "Separating sounds with questionable confidence.",
    "Still working. Still pretending this is easy.",
)
LOADING_MESSAGE_MIN_MS = 4000
LOADING_MESSAGE_MAX_MS = 6000


def draw_round_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs: object,
) -> int:
    radius = max(0.0, min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2))
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class EqCurveEditor(tk.Canvas):
    MIN_WIDTH = 320
    MIN_HEIGHT = 220
    MIN_FREQ = 20.0
    MAX_FREQ = 20000.0
    MIN_DB = -12.0
    MAX_DB = 12.0
    LOW_FREQ = 100.0
    MID_FREQ = 1000.0
    HIGH_FREQ = 8000.0
    COLORS = {
        "hp": "#f3d13b",
        "low": "#f59e42",
        "mid": "#b86cff",
        "high": "#34d399",
        "lp": "#60a5fa",
    }

    def __init__(
        self,
        parent: tk.Widget,
        low_var: tk.DoubleVar,
        mid_var: tk.DoubleVar,
        high_var: tk.DoubleVar,
        low_freq_var: tk.DoubleVar,
        mid_freq_var: tk.DoubleVar,
        high_freq_var: tk.DoubleVar,
        low_q_var: tk.DoubleVar,
        mid_q_var: tk.DoubleVar,
        high_q_var: tk.DoubleVar,
        low_shape_var: tk.StringVar,
        mid_shape_var: tk.StringVar,
        high_shape_var: tk.StringVar,
        high_pass_var: tk.DoubleVar,
        low_pass_var: tk.DoubleVar,
        high_pass_q_var: tk.DoubleVar,
        low_pass_q_var: tk.DoubleVar,
    ) -> None:
        super().__init__(
            parent,
            height=self.MIN_HEIGHT,
            background="#101219",
            highlightthickness=1,
            highlightbackground="#2b3040",
        )
        self.vars = {
            "low": low_var,
            "mid": mid_var,
            "high": high_var,
            "hp": high_pass_var,
            "lp": low_pass_var,
        }
        self.freq_vars = {
            "low": low_freq_var,
            "mid": mid_freq_var,
            "high": high_freq_var,
        }
        self.q_vars = {
            "low": low_q_var,
            "mid": mid_q_var,
            "high": high_q_var,
            "hp": high_pass_q_var,
            "lp": low_pass_q_var,
        }
        self.shape_vars = {
            "low": low_shape_var,
            "mid": mid_shape_var,
            "high": high_shape_var,
        }
        self.enabled = True
        self._drag_band: str | None = None
        self._draw_pending = False
        for variable in (*self.vars.values(), *self.freq_vars.values(), *self.q_vars.values(), *self.shape_vars.values()):
            variable.trace_add("write", self._schedule_draw)
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Button-1>", self._mouse_down)
        self.bind("<B1-Motion>", self._mouse_drag)
        self.bind("<ButtonRelease-1>", self._mouse_up)
        self.bind("<Double-Button-1>", self._double_click)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.draw()

    def _schedule_draw(self, *_args: object) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self.after_idle(self._draw_after_idle)

    def _draw_after_idle(self) -> None:
        self._draw_pending = False
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), self.MIN_WIDTH)
        height = max(self.winfo_height(), self.MIN_HEIGHT)
        left, top, right, bottom = self._plot_bounds(width, height)

        self.create_rectangle(0, 0, width, height, fill="#101219", outline="")
        self.create_rectangle(left, top, right, bottom, fill="#141821", outline="#252b36")
        self._draw_grid(left, top, right, bottom)
        self._draw_band_fills(left, top, right, bottom)
        self._draw_response_curve(left, top, right, bottom)
        self._draw_handles(left, top, right, bottom)
        if not self.enabled:
            self.create_text(
                width / 2,
                height / 2,
                text="Load audio to edit EQ",
                fill="#8e9aab",
                font=("Segoe UI", 9, "bold"),
            )

    def _plot_bounds(self, width: int, height: int) -> tuple[int, int, int, int]:
        return 42, 20, width - 38, height - 34

    def _draw_grid(self, left: int, top: int, right: int, bottom: int) -> None:
        freq_labels = [
            (20, "20"),
            (50, "50"),
            (100, "100"),
            (200, "200"),
            (500, "500"),
            (1000, "1k"),
            (2000, "2k"),
            (5000, "5k"),
            (10000, "10k"),
            (20000, "20k"),
        ]
        for freq, label in freq_labels:
            x = self._freq_to_x(freq, left, right)
            self.create_line(x, top, x, bottom, fill="#222938")
            self.create_text(x, bottom + 14, text=label, fill="#7b8495", font=("Segoe UI", 7))
        for db in (-12, -6, 0, 6, 12):
            y = self._db_to_y(db, top, bottom)
            color = "#3b4254" if db == 0 else "#222938"
            self.create_line(left, y, right, y, fill=color)
            self.create_text(right + 7, y, text=f"{db:+d}", anchor="w", fill="#7b8495", font=("Segoe UI", 7))
        self.create_text(left, 10, text="Graphic EQ", anchor="w", fill="#f4c95d", font=("Segoe UI", 9, "bold"))

    def _draw_band_fills(self, left: int, top: int, right: int, bottom: int) -> None:
        for band in ("low", "mid", "high", "hp", "lp"):
            values = [
                self._band_contribution(band, self._sample_freq(index, 95))
                for index in range(96)
            ]
            if max(abs(value) for value in values) < 0.05:
                continue
            points: list[float] = []
            baseline = self._db_to_y(0, top, bottom)
            points.extend([left, baseline])
            for index, db in enumerate(values):
                freq = self._sample_freq(index, 95)
                points.extend([self._freq_to_x(freq, left, right), self._db_to_y(db, top, bottom)])
            points.extend([right, baseline])
            self.create_polygon(points, fill=self.COLORS[band], stipple="gray25", outline="")

    def _draw_response_curve(self, left: int, top: int, right: int, bottom: int) -> None:
        points: list[float] = []
        for index in range(150):
            freq = self._sample_freq(index, 149)
            db = self._response_db(freq)
            points.extend([self._freq_to_x(freq, left, right), self._db_to_y(db, top, bottom)])
        self.create_line(points, fill="#f7dc4f", width=4, smooth=True)
        self.create_line(points, fill="#fff7b0", width=1, smooth=True)

    def _draw_handles(self, left: int, top: int, right: int, bottom: int) -> None:
        for band, x, y, label, disabled in self._handle_specs(left, top, right, bottom):
            radius = 7 if band == self._drag_band else 6
            fill = "#1a1f2b" if disabled else self.COLORS[band]
            outline = "#6b7280" if disabled else "#f8fafc"
            self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline=outline, width=2)
            self.create_text(x, y - 16, text=label, fill="#d1d5db", font=("Segoe UI", 7, "bold"))

    def _mouse_down(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        self._drag_band = self._nearest_handle(event.x, event.y)
        if self._drag_band and event.state & CTRL_MASK:
            self._reset_band(self._drag_band)
            self._drag_band = None
            return
        if self._drag_band:
            self._apply_drag(event.x, event.y)

    def _mouse_drag(self, event: tk.Event) -> None:
        if self.enabled and self._drag_band:
            self._apply_drag(event.x, event.y)

    def _mouse_up(self, _event: tk.Event) -> None:
        self._drag_band = None
        self.draw()

    def _double_click(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        band = self._nearest_handle(event.x, event.y)
        if band:
            self._reset_band(band)

    def _reset_band(self, band: str) -> None:
        self.vars[band].set(0.0)
        if band in self.freq_vars:
            defaults = {"low": self.LOW_FREQ, "mid": self.MID_FREQ, "high": self.HIGH_FREQ}
            self.freq_vars[band].set(defaults[band])
            self.q_vars[band].set({"low": 0.8, "mid": 1.0, "high": 0.8}[band])
            self.shape_vars[band].set("Bell")
        elif band in self.q_vars:
            self.q_vars[band].set(0.7)

    def _nearest_handle(self, x: int, y: int) -> str | None:
        left, top, right, bottom = self._plot_bounds(
            max(self.winfo_width(), self.MIN_WIDTH),
            max(self.winfo_height(), self.MIN_HEIGHT),
        )
        nearest_band = None
        nearest_distance = 16.0
        for band, handle_x, handle_y, _label, _disabled in self._handle_specs(left, top, right, bottom):
            distance = math.hypot(x - handle_x, y - handle_y)
            if distance < nearest_distance:
                nearest_band = band
                nearest_distance = distance
        return nearest_band

    def _apply_drag(self, x: int, y: int) -> None:
        assert self._drag_band is not None
        left, top, right, bottom = self._plot_bounds(
            max(self.winfo_width(), self.MIN_WIDTH),
            max(self.winfo_height(), self.MIN_HEIGHT),
        )
        band = self._drag_band
        if band in {"low", "mid", "high"}:
            freq = self._x_to_freq(x, left, right)
            db = round(self._y_to_db(y, top, bottom) * 2.0) / 2.0
            self.vars[band].set(max(min(db, self.MAX_DB), self.MIN_DB))
            self.freq_vars[band].set(self._round_freq(freq))
            return

        freq = self._x_to_freq(x, left, right)
        if band == "hp":
            limit = self._safe_float(self.vars["lp"].get())
            if limit > 0:
                freq = min(freq, max(limit - 10.0, self.MIN_FREQ))
            self.vars[band].set(0.0 if freq <= 28.0 else self._round_freq(freq))
        elif band == "lp":
            limit = self._safe_float(self.vars["hp"].get())
            if limit > 0:
                freq = max(freq, min(limit + 10.0, self.MAX_FREQ))
            self.vars[band].set(0.0 if freq >= 19000.0 else self._round_freq(freq))

    def _handle_specs(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> list[tuple[str, float, float, str, bool]]:
        hp = self._safe_float(self.vars["hp"].get())
        lp = self._safe_float(self.vars["lp"].get())
        return [
            ("hp", self._freq_to_x(hp or self.MIN_FREQ, left, right), self._db_to_y(0, top, bottom), "HP", hp <= 0),
            ("low", self._freq_to_x(self._center_freq("low"), left, right), self._db_to_y(self._db_value("low"), top, bottom), "LOW", False),
            ("mid", self._freq_to_x(self._center_freq("mid"), left, right), self._db_to_y(self._db_value("mid"), top, bottom), "MID", False),
            ("high", self._freq_to_x(self._center_freq("high"), left, right), self._db_to_y(self._db_value("high"), top, bottom), "HIGH", False),
            ("lp", self._freq_to_x(lp or self.MAX_FREQ, left, right), self._db_to_y(0, top, bottom), "LP", lp <= 0),
        ]

    def _response_db(self, freq: float) -> float:
        db = sum(self._band_contribution(band, freq) for band in ("low", "mid", "high", "hp", "lp"))
        return max(min(db, self.MAX_DB), self.MIN_DB)

    def _band_contribution(self, band: str, freq: float) -> float:
        if band in {"low", "mid", "high"}:
            gain = self._db_value(band)
            center = self._center_freq(band)
            q = self._q_value(band)
            shape = self._shape_value(band)
            distance = math.log2(freq / center)
            if shape == "Low Shelf":
                return gain / (1.0 + math.exp(distance * q * 3.0))
            if shape == "High Shelf":
                return gain / (1.0 + math.exp(-distance * q * 3.0))
            width = self._bell_width(q)
            return gain * math.exp(-(distance ** 2) / (2.0 * width * width))
        if band == "hp":
            cutoff = self._safe_float(self.vars["hp"].get())
            if cutoff <= self.MIN_FREQ:
                return 0.0
            return max(min(self._cut_filter_db("hp", freq, cutoff, self._q_value("hp")), self.MAX_DB), self.MIN_DB)
        if band == "lp":
            cutoff = self._safe_float(self.vars["lp"].get())
            if cutoff <= 0:
                return 0.0
            return max(min(self._cut_filter_db("lp", freq, cutoff, self._q_value("lp")), self.MAX_DB), self.MIN_DB)
        return 0.0

    def _db_value(self, band: str) -> float:
        return max(min(self._safe_float(self.vars[band].get()), self.MAX_DB), self.MIN_DB)

    def _center_freq(self, band: str) -> float:
        defaults = {"low": self.LOW_FREQ, "mid": self.MID_FREQ, "high": self.HIGH_FREQ}
        return max(min(self._safe_float(self.freq_vars[band].get()) or defaults[band], self.MAX_FREQ), self.MIN_FREQ)

    def _q_value(self, band: str) -> float:
        return max(min(self._safe_float(self.q_vars[band].get()) or 1.0, 10.0), 0.1)

    @staticmethod
    def _bell_width(q: float) -> float:
        return max(0.04, 0.58 / q)

    @staticmethod
    def _cut_filter_db(kind: str, freq: float, cutoff: float, q: float) -> float:
        ratio = max(freq / max(cutoff, 0.000001), 0.000001)
        denominator = math.sqrt((1.0 - ratio * ratio) ** 2 + (ratio / max(q, 0.000001)) ** 2)
        if denominator <= 0:
            return 0.0
        magnitude = ratio * ratio / denominator if kind == "hp" else 1.0 / denominator
        return 20.0 * math.log10(max(magnitude, 0.000001))

    def _shape_value(self, band: str) -> str:
        value = str(self.shape_vars[band].get())
        return value if value in EQ_SHAPES else "Bell"

    def _sample_freq(self, index: int, last_index: int) -> float:
        ratio = index / max(last_index, 1)
        return 10 ** (math.log10(self.MIN_FREQ) + ratio * (math.log10(self.MAX_FREQ) - math.log10(self.MIN_FREQ)))

    def _freq_to_x(self, freq: float, left: int, right: int) -> float:
        freq = max(min(freq, self.MAX_FREQ), self.MIN_FREQ)
        ratio = (math.log10(freq) - math.log10(self.MIN_FREQ)) / (math.log10(self.MAX_FREQ) - math.log10(self.MIN_FREQ))
        return left + ratio * (right - left)

    def _x_to_freq(self, x: int, left: int, right: int) -> float:
        ratio = max(min((x - left) / max(right - left, 1), 1.0), 0.0)
        return 10 ** (math.log10(self.MIN_FREQ) + ratio * (math.log10(self.MAX_FREQ) - math.log10(self.MIN_FREQ)))

    def _db_to_y(self, db: float, top: int, bottom: int) -> float:
        db = max(min(db, self.MAX_DB), self.MIN_DB)
        ratio = (db - self.MIN_DB) / (self.MAX_DB - self.MIN_DB)
        return bottom - ratio * (bottom - top)

    def _y_to_db(self, y: int, top: int, bottom: int) -> float:
        ratio = max(min((bottom - y) / max(bottom - top, 1), 1.0), 0.0)
        return self.MIN_DB + ratio * (self.MAX_DB - self.MIN_DB)

    def _round_freq(self, freq: float) -> float:
        if freq < 100:
            return round(freq / 5.0) * 5.0
        if freq < 1000:
            return round(freq / 10.0) * 10.0
        return round(freq / 100.0) * 100.0

    def _safe_float(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError, tk.TclError):
            return 0.0


class PillButton(tk.Canvas):
    PALETTES = {
        "default": {
            "fill": "#222b38",
            "hover": "#2a3545",
            "pressed": "#1a2230",
            "outline": "#354254",
            "fg": "#e7edf7",
            "disabled_fill": "#151b25",
            "disabled_fg": "#5f6b7a",
        },
        "primary": {
            "fill": "#5aa7ff",
            "hover": "#77b8ff",
            "pressed": "#3d8df0",
            "outline": "#77b8ff",
            "fg": "#07111f",
            "disabled_fill": "#17304d",
            "disabled_fg": "#66809d",
        },
        "ghost": {
            "fill": "#151c28",
            "hover": "#202a3a",
            "pressed": "#111722",
            "outline": "#2a3546",
            "fg": "#cbd5e1",
            "disabled_fill": "#121722",
            "disabled_fg": "#556171",
        },
        "danger": {
            "fill": "#8f3d51",
            "hover": "#a84a60",
            "pressed": "#713040",
            "outline": "#b75a70",
            "fg": "#fff3f6",
            "disabled_fill": "#271b23",
            "disabled_fg": "#7b6470",
        },
    }

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        *,
        variant: str = "default",
        width: int | None = None,
        height: int = 32,
        bg: str = "#10141c",
    ) -> None:
        self.text = text
        self.command = command
        self.variant = variant
        self.enabled = True
        self.hover = False
        self.pressed = False
        self.fixed_width = width
        width = width or max(72, 16 + len(text) * 8)
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _custom_config(self) -> dict[str, tuple[str, str, str, str, object]]:
        state = "normal" if self.enabled else "disabled"
        return {
            "text": ("text", "text", "Text", "", self.text),
            "state": ("state", "state", "State", "normal", state),
        }

    def configure(self, cnf: object | None = None, **kwargs: object) -> object | None:  # type: ignore[override]
        if cnf is None and not kwargs:
            options = dict(super().configure())
            options.update(self._custom_config())
            return options
        if isinstance(cnf, str) and not kwargs:
            custom = self._custom_config()
            if cnf in custom:
                return custom[cnf]
            return super().configure(cnf)
        if isinstance(cnf, dict):
            merged = dict(cnf)
            merged.update(kwargs)
            kwargs = merged
        elif cnf is not None:
            super().configure(cnf)
        redraw = False
        if "text" in kwargs:
            self.text = str(kwargs.pop("text"))
            if self.fixed_width is None:
                super().configure(width=max(72, 16 + len(self.text) * 8))
            redraw = True
        if "state" in kwargs:
            self.set_enabled(str(kwargs.pop("state")) != "disabled")
            redraw = True
        if kwargs:
            super().configure(**kwargs)
        if redraw:
            self._draw()

    config = configure

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.hover = False
        self.pressed = False
        self._draw()

    def _palette(self) -> dict[str, str]:
        return self.PALETTES.get(self.variant, self.PALETTES["default"])

    def _draw(self) -> None:
        self.delete("all")
        width = max(int(self.winfo_width()), 1)
        height = max(int(self.winfo_height()), 1)
        palette = self._palette()
        if not self.enabled:
            fill = palette["disabled_fill"]
            fg = palette["disabled_fg"]
            outline = "#222b36"
        elif self.pressed:
            fill = palette["pressed"]
            fg = palette["fg"]
            outline = palette["outline"]
        elif self.hover:
            fill = palette["hover"]
            fg = palette["fg"]
            outline = palette["outline"]
        else:
            fill = palette["fill"]
            fg = palette["fg"]
            outline = palette["outline"]
        draw_round_rect(self, 1, 1, width - 1, height - 1, height / 2 - 1, fill=fill, outline=outline)
        self.create_text(width / 2, height / 2, text=self.text, fill=fg, font=("Segoe UI", 9, "bold"))

    def _on_enter(self, _event: tk.Event) -> None:
        self.hover = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self.hover = False
        self.pressed = False
        self._draw()

    def _on_press(self, _event: tk.Event) -> None:
        if not self.enabled:
            return
        self.pressed = True
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        was_pressed = self.pressed
        self.pressed = False
        self._draw()
        if was_pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()


class FlatSlider(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        from_: float,
        to: float,
        variable: tk.DoubleVar,
        command: Callable[[str], None] | None = None,
        drag_start_command: Callable[[], None] | None = None,
        drag_end_command: Callable[[], None] | None = None,
        height: int = 24,
        bg: str = "#101722",
        accent: str = "#5aa7ff",
    ) -> None:
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.from_ = float(from_)
        self.to = float(to)
        self.variable = variable
        self.command = command
        self.drag_start_command = drag_start_command
        self.drag_end_command = drag_end_command
        self.accent = accent
        self.enabled = True
        self._draw_pending = False
        self.variable.trace_add("write", self._schedule_draw)
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._set_from_event, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.draw()

    def _custom_config(self) -> dict[str, tuple[str, str, str, str, object]]:
        state = "normal" if self.enabled else "disabled"
        return {
            "from": ("from", "from", "From", self.from_, self.from_),
            "from_": ("from_", "from_", "From", self.from_, self.from_),
            "to": ("to", "to", "To", self.to, self.to),
            "state": ("state", "state", "State", "normal", state),
        }

    def configure(self, cnf: object | None = None, **kwargs: object) -> object | None:  # type: ignore[override]
        if cnf is None and not kwargs:
            options = dict(super().configure())
            options.update(self._custom_config())
            return options
        if isinstance(cnf, str) and not kwargs:
            custom = self._custom_config()
            if cnf in custom:
                return custom[cnf]
            return super().configure(cnf)
        if isinstance(cnf, dict):
            merged = dict(cnf)
            merged.update(kwargs)
            kwargs = merged
        elif cnf is not None:
            super().configure(cnf)
        if "from_" in kwargs:
            self.from_ = float(kwargs.pop("from_"))
        if "from" in kwargs:
            self.from_ = float(kwargs.pop("from"))
        if "to" in kwargs:
            self.to = float(kwargs.pop("to"))
        if "state" in kwargs:
            self.set_enabled(str(kwargs.pop("state")) != "disabled")
        if kwargs:
            super().configure(**kwargs)
        self.draw()

    config = configure

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.draw()

    def _schedule_draw(self, *_args: object) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self.after_idle(self._draw_after_idle)

    def _draw_after_idle(self) -> None:
        self._draw_pending = False
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = max(int(self.winfo_width()), 80)
        height = max(int(self.winfo_height()), 24)
        left, right = 8, width - 8
        center_y = height / 2
        track_h = 6
        draw_round_rect(
            self,
            left,
            center_y - track_h / 2,
            right,
            center_y + track_h / 2,
            track_h / 2,
            fill="#1c2635" if self.enabled else "#131a25",
            outline="#2b3748",
        )
        value = max(min(float(self.variable.get()), max(self.from_, self.to)), min(self.from_, self.to))
        span = self.to - self.from_
        ratio = 0.0 if abs(span) < 1e-9 else (value - self.from_) / span
        ratio = max(0.0, min(ratio, 1.0))
        x = left + ratio * (right - left)
        if x > left:
            draw_round_rect(
                self,
                left,
                center_y - track_h / 2,
                x,
                center_y + track_h / 2,
                track_h / 2,
                fill=self.accent if self.enabled else "#3b4657",
                outline="",
            )
        handle_fill = "#dbe7f7" if self.enabled else "#657286"
        self.create_oval(x - 6, center_y - 6, x + 6, center_y + 6, fill=handle_fill, outline="#ffffff")

    def _set_from_event(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        width = max(int(self.winfo_width()), 80)
        left, right = 8, width - 8
        ratio = (max(left, min(event.x, right)) - left) / max(right - left, 1)
        value = self.from_ + ratio * (self.to - self.from_)
        self.variable.set(value)
        if self.command:
            self.command(str(value))

    def _on_press(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        if self.drag_start_command:
            self.drag_start_command()
        self._set_from_event(event)

    def _on_release(self, _event: tk.Event) -> None:
        if self.drag_end_command:
            self.drag_end_command()


class RangeSlider(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        from_: float,
        to: float,
        start_variable: tk.DoubleVar,
        end_variable: tk.DoubleVar,
        command: Callable[[], None] | None = None,
        height: int = 28,
        bg: str = "#101722",
        accent: str = "#5aa7ff",
    ) -> None:
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.from_ = float(from_)
        self.to = float(to)
        self.start_variable = start_variable
        self.end_variable = end_variable
        self.command = command
        self.accent = accent
        self.enabled = True
        self._active_handle: str | None = None
        self._draw_pending = False
        self._draw_after_id: str | None = None
        self.start_variable.trace_add("write", self._schedule_draw)
        self.end_variable.trace_add("write", self._schedule_draw)
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.draw()

    def _custom_config(self) -> dict[str, tuple[str, str, str, object, object]]:
        state = "normal" if self.enabled else "disabled"
        return {
            "from": ("from", "from", "From", self.from_, self.from_),
            "from_": ("from_", "from_", "From", self.from_, self.from_),
            "to": ("to", "to", "To", self.to, self.to),
            "state": ("state", "state", "State", "normal", state),
        }

    def configure(self, cnf: object | None = None, **kwargs: object) -> object | None:  # type: ignore[override]
        if cnf is None and not kwargs:
            options = dict(super().configure())
            options.update(self._custom_config())
            return options
        if isinstance(cnf, str) and not kwargs:
            custom = self._custom_config()
            if cnf in custom:
                return custom[cnf]
            return super().configure(cnf)
        if isinstance(cnf, dict):
            merged = dict(cnf)
            merged.update(kwargs)
            kwargs = merged
        elif cnf is not None:
            super().configure(cnf)
        if "from_" in kwargs:
            self.from_ = float(kwargs.pop("from_"))
        if "from" in kwargs:
            self.from_ = float(kwargs.pop("from"))
        if "to" in kwargs:
            self.to = float(kwargs.pop("to"))
        if "state" in kwargs:
            self.set_enabled(str(kwargs.pop("state")) != "disabled")
        if kwargs:
            super().configure(**kwargs)
        self._clamp_variables()
        self.draw()
        return None

    config = configure

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.draw()

    def _schedule_draw(self, *_args: object) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self._draw_after_id = self.after_idle(self._draw_after_idle)

    def _draw_after_idle(self) -> None:
        self._draw_pending = False
        self._draw_after_id = None
        self.draw()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self or not self._draw_after_id:
            return
        try:
            self.after_cancel(self._draw_after_id)
        except tk.TclError:
            pass
        self._draw_after_id = None

    def draw(self) -> None:
        self.delete("all")
        width = max(int(self.winfo_width()), 120)
        height = max(int(self.winfo_height()), 28)
        left, right = 10, width - 10
        center_y = height / 2
        track_h = 7
        start, end = self._ordered_values()
        start_x = self._value_to_x(start, left, right)
        end_x = self._value_to_x(end, left, right)
        draw_round_rect(self, left, center_y - track_h / 2, right, center_y + track_h / 2, track_h / 2, fill="#1c2635", outline="#2b3748")
        draw_round_rect(self, start_x, center_y - track_h / 2, end_x, center_y + track_h / 2, track_h / 2, fill=self.accent if self.enabled else "#3b4657", outline="")
        handle_fill = "#e6edf7" if self.enabled else "#657286"
        for x in (start_x, end_x):
            self.create_oval(x - 7, center_y - 7, x + 7, center_y + 7, fill=handle_fill, outline="#ffffff")

    def _ordered_values(self) -> tuple[float, float]:
        start = float(self.start_variable.get())
        end = float(self.end_variable.get())
        low, high = sorted((start, end))
        low = self._clamp_value(low)
        high = self._clamp_value(high)
        return low, high

    def _clamp_value(self, value: float) -> float:
        return max(min(value, max(self.from_, self.to)), min(self.from_, self.to))

    def _clamp_variables(self) -> None:
        for variable in (self.start_variable, self.end_variable):
            try:
                value = float(variable.get())
            except (TypeError, ValueError, tk.TclError):
                value = self.from_
            clamped = self._clamp_value(value)
            if abs(value - clamped) > 1e-9:
                variable.set(clamped)

    def _value_to_x(self, value: float, left: int, right: int) -> float:
        span = self.to - self.from_
        ratio = 0.0 if abs(span) < 1e-9 else (value - self.from_) / span
        return left + max(0.0, min(ratio, 1.0)) * (right - left)

    def _event_to_value(self, event: tk.Event) -> float:
        width = max(int(self.winfo_width()), 120)
        left, right = 10, width - 10
        ratio = (max(left, min(event.x, right)) - left) / max(right - left, 1)
        return self.from_ + ratio * (self.to - self.from_)

    def _on_press(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        width = max(int(self.winfo_width()), 120)
        left, right = 10, width - 10
        start, end = self._ordered_values()
        start_x = self._value_to_x(start, left, right)
        end_x = self._value_to_x(end, left, right)
        self._active_handle = "start" if abs(event.x - start_x) <= abs(event.x - end_x) else "end"
        self._set_from_event(event)

    def _on_drag(self, event: tk.Event) -> None:
        if self.enabled and self._active_handle:
            self._set_from_event(event)

    def _on_release(self, _event: tk.Event) -> None:
        self._active_handle = None

    def _set_from_event(self, event: tk.Event) -> None:
        value = self._event_to_value(event)
        start, end = self._ordered_values()
        if self._active_handle == "start":
            self.start_variable.set(min(value, end))
        elif self._active_handle == "end":
            self.end_variable.set(max(value, start))
        if self.command:
            self.command()


class KnobControl(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        variable: tk.DoubleVar,
        label: str,
        *,
        from_: float,
        to: float,
        increment: float,
        color: str,
        value_format: Callable[[float], str],
        extra_variables: tuple[tk.Variable, ...] = (),
        reset_value: float = 0.0,
        reset_command: Callable[[], None] | None = None,
        value_to_ratio: Callable[[float], float] | None = None,
        ratio_to_value: Callable[[float], float] | None = None,
        drag_pixels: float = 260.0,
        bg: str = "#101722",
    ) -> None:
        super().__init__(parent, width=112, height=92, bg=bg, highlightthickness=0, bd=0)
        self.variable = variable
        self.label = label
        self.from_ = float(from_)
        self.to = float(to)
        self.increment = float(increment)
        self.color = color
        self.value_format = value_format
        self.extra_variables = extra_variables
        self.reset_value = float(reset_value)
        self.reset_command = reset_command
        self.value_to_ratio = value_to_ratio
        self.ratio_to_value = ratio_to_value
        self.drag_pixels = max(float(drag_pixels), 1.0)
        self.enabled = True
        self._drag_y = 0
        self._drag_value = 0.0
        self._drag_ratio = 0.0
        self._draw_pending = False
        self._draw_after_id: str | None = None
        self.variable.trace_add("write", self._schedule_draw)
        for extra_variable in self.extra_variables:
            extra_variable.trace_add("write", self._schedule_draw)
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Double-Button-1>", self._reset)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.draw()

    def _schedule_draw(self, *_args: object) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self._draw_after_id = self.after_idle(self._draw_after_idle)

    def _draw_after_idle(self) -> None:
        self._draw_pending = False
        self._draw_after_id = None
        self.draw()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self or not self._draw_after_id:
            return
        try:
            self.after_cancel(self._draw_after_id)
        except tk.TclError:
            pass
        self._draw_after_id = None

    def draw(self) -> None:
        self.delete("all")
        width = max(int(self.winfo_width()), 92)
        value = max(min(float(self.variable.get()), self.to), self.from_)
        ratio = self._value_to_ratio(value)
        cx, cy, radius = width / 2, 42, 22
        fill = "#182130" if self.enabled else "#131a25"
        outline = "#344052" if self.enabled else "#222b36"
        self.create_text(cx, 10, text=self.label, fill="#cbd5e1", font=("Segoe UI", 8, "bold"))
        self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=fill, outline=outline, width=2)
        self.create_arc(
            cx - radius - 4,
            cy - radius - 4,
            cx + radius + 4,
            cy + radius + 4,
            start=225,
            extent=-270 * ratio,
            style="arc",
            outline=self.color if self.enabled else "#4a5565",
            width=3,
        )
        angle = math.radians(225 - 270 * ratio)
        pointer = radius - 6
        self.create_line(cx, cy, cx + math.cos(angle) * pointer, cy - math.sin(angle) * pointer, fill="#f8fafc", width=2)
        self.create_text(cx, 78, text=self.value_format(value), fill=self.color if self.enabled else "#6b7280", font=("Segoe UI", 8, "bold"))

    def _on_press(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        if event.state & CTRL_MASK:
            self._reset_to_default()
            return
        self._drag_y = event.y
        self._drag_value = float(self.variable.get())
        self._drag_ratio = self._value_to_ratio(self._drag_value)

    def _on_drag(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        delta = self._drag_y - event.y
        if self.ratio_to_value:
            self._set_value(self.ratio_to_value(self._drag_ratio + delta / self.drag_pixels))
            return
        self._set_value(self._drag_value + delta * self.increment / 8.0)

    def _on_wheel(self, event: tk.Event) -> None:
        if self.enabled:
            if self.ratio_to_value:
                direction = 1 if event.delta > 0 else -1
                self._set_value(self.ratio_to_value(self._value_to_ratio(float(self.variable.get())) + direction * 0.025))
                return
            self._set_value(float(self.variable.get()) + (self.increment if event.delta > 0 else -self.increment))

    def _reset(self, _event: tk.Event) -> None:
        if self.enabled:
            self._reset_to_default()

    def _reset_to_default(self) -> None:
        if self.reset_command:
            self.reset_command()
            return
        self.variable.set(self.reset_value)

    def _value_to_ratio(self, value: float) -> float:
        if self.value_to_ratio:
            return max(min(self.value_to_ratio(value), 1.0), 0.0)
        if abs(self.to - self.from_) < 1e-9:
            return 0.0
        return max(min((value - self.from_) / (self.to - self.from_), 1.0), 0.0)

    def _set_value(self, value: float) -> None:
        self.variable.set(round(max(min(value, self.to), self.from_), 4))


class StemFader(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        variable: tk.DoubleVar,
        color: str,
        *,
        bg: str = "#151c28",
    ) -> None:
        super().__init__(parent, width=64, height=214, bg=bg, highlightthickness=0, bd=0)
        self.variable = variable
        self.color = color
        self.enabled = True
        self._draw_pending = False
        self.variable.trace_add("write", self._schedule_draw)
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Button-1>", self._set_from_event)
        self.bind("<B1-Motion>", self._set_from_event)
        self.draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.draw()

    def _schedule_draw(self, *_args: object) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self.after_idle(self._draw_after_idle)

    def _draw_after_idle(self) -> None:
        self._draw_pending = False
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = int(self.winfo_width())
        height = int(self.winfo_height())
        if width <= 1 or height <= 1:
            return
        top, bottom = 16, height - 18
        center = width / 2
        track_width = 16
        value = max(0.0, min(float(self.variable.get()), 200.0))
        y = bottom - value / 200.0 * (bottom - top)

        draw_round_rect(
            self,
            center - track_width / 2 - 5,
            top - 5,
            center + track_width / 2 + 5,
            bottom + 5,
            12,
            fill="#0d121a",
            outline="#263143",
        )
        draw_round_rect(
            self,
            center - track_width / 2,
            top,
            center + track_width / 2,
            bottom,
            track_width / 2,
            fill="#263141",
            outline="",
        )
        if y < bottom:
            draw_round_rect(
                self,
                center - track_width / 2,
                y,
                center + track_width / 2,
                bottom,
                track_width / 2,
                fill=self.color if self.enabled else "#4a5565",
                outline="",
            )

        for tick_value in (200, 100, 50, 25, 0):
            tick_y = bottom - tick_value / 200.0 * (bottom - top)
            self.create_line(center + 16, tick_y, center + 21, tick_y, fill="#4d596a")

        handle_fill = "#dce4ee" if self.enabled else "#687386"
        handle_outline = "#a5afbf" if self.enabled else "#8791a0"
        x1, y1, x2, y2 = center - 21, y - 9, center + 21, y + 9
        inset = 4
        self.create_polygon(
            x1 + inset,
            y1,
            x2 - inset,
            y1,
            x2,
            y1 + inset,
            x2,
            y2 - inset,
            x2 - inset,
            y2,
            x1 + inset,
            y2,
            x1,
            y2 - inset,
            x1,
            y1 + inset,
            fill=handle_fill,
            outline=handle_outline,
            width=1,
        )
        self.create_line(center - 8, y, center + 8, y, fill="#4c5666", width=2)
    def _set_from_event(self, event: tk.Event) -> None:
        if not self.enabled:
            return
        if event.state & CTRL_MASK:
            self.variable.set(100.0)
            return
        height = int(self.winfo_height())
        if height <= 1:
            return
        top, bottom = 16, height - 18
        ratio = (bottom - max(top, min(event.y, bottom))) / max(bottom - top, 1)
        self.variable.set(round(ratio * 200.0))


class StemSamplePrepApp(CompactInterface, WorkspaceFeatures, tk.Tk):
    def __init__(self, *, ui_scale=None) -> None:
        self._ui_scale_override = ui_scale
        enable_dpi_awareness()
        super().__init__()
        self.paths = AppPaths.from_runtime()
        self.paths.ensure()
        self.settings = self.paths.read_settings()
        self.output_dir = self._load_output_dir()
        self.output_dir_label_var = tk.StringVar(value=self._format_output_dir_label())
        self._configure_logging()

        self.current_input: Path | None = None
        self.source_wav: Path | None = None
        self.session_name = ""
        self.duration_seconds = 0.0
        self.peaks: list[float] = []
        self.stem_paths: dict[str, Path] = {}
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.busy_title = ""
        self.busy_status_base = ""
        self.busy_started_at: float | None = None
        self.busy_animation_after_id: str | None = None
        self.busy_animation_step = 0
        self.busy_progress_percent: float | None = None
        self.loading_message_after_id: str | None = None
        self.loading_message_text = ""
        self.cancel_event: threading.Event | None = None
        self.current_process: subprocess.Popen | None = None
        self.drop_queue: queue.Queue[Path] = queue.Queue()
        self.drag_start_seconds: float | None = None
        self.preview_playing = False
        self.current_preview_file: Path | None = None
        self.playback_started_at: float | None = None
        self.playback_start_seconds = 0.0
        self.playback_duration_seconds = 0.0
        self.playback_tempo_ratio = 1.0
        self.playback_output_duration_seconds = 0.0
        self.playback_cursor_manual = False
        self.playback_seek_dragging = False
        self.fade_control_dragging = False
        self.updating_playback_position = False
        self.last_preview_stems: list[MixStem] | None = None
        self.last_preview_label = ""
        self.last_preview_mode = ""
        self.last_preview_stem: str | None = None
        self.pending_preview_mode: tuple[str, str | None] | None = None
        self.live_restart_after_id: str | None = None
        self.realtime_processes: list[subprocess.Popen] = []
        self._file_spectrum = None
        self.log_messages: list[str] = []
        self.log_visible = False
        self._drop_wndproc: object | None = None
        self._drop_old_wndproc: int | None = None
        self._drop_old_wndprocs: dict[int, int] = {}
        self._drop_hwnds: list[int] = []
        self._drop_hwnd: int | None = None
        self.closing = False
        self.worker_queue_after_id: str | None = None
        self.drop_queue_after_id: str | None = None
        self.playback_progress_after_id: str | None = None
        self.waveform_resize_after_id: str | None = None
        self.waveform_fade_after_id: str | None = None

        self.status_var = tk.StringVar(value="Drop an audio file or click Open Audio.")
        self.step_var = tk.StringVar(value="")
        self.file_label_var = tk.StringVar(value="No file")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.selection_start_var = tk.DoubleVar(value=0.0)
        self.selection_end_var = tk.DoubleVar(value=0.0)
        self.playback_position_var = tk.DoubleVar(value=0.0)
        self.playback_label_var = tk.StringVar(value="--")
        self.fade_in_var = tk.DoubleVar(value=0.02)
        self.fade_out_var = tk.DoubleVar(value=0.02)
        self.eq_low_var = tk.DoubleVar(value=0.0)
        self.eq_mid_var = tk.DoubleVar(value=0.0)
        self.eq_high_var = tk.DoubleVar(value=0.0)
        self.eq_low_freq_var = tk.DoubleVar(value=120.0)
        self.eq_mid_freq_var = tk.DoubleVar(value=EqCurveEditor.MID_FREQ)
        self.eq_high_freq_var = tk.DoubleVar(value=EqCurveEditor.HIGH_FREQ)
        self.eq_low_q_var = tk.DoubleVar(value=0.8)
        self.eq_mid_q_var = tk.DoubleVar(value=1.0)
        self.eq_high_q_var = tk.DoubleVar(value=0.8)
        self.eq_low_shape_var = tk.StringVar(value="Low Shelf")
        self.eq_mid_shape_var = tk.StringVar(value="Bell")
        self.eq_high_shape_var = tk.StringVar(value="High Shelf")
        self.high_pass_var = tk.DoubleVar(value=0.0)
        self.low_pass_var = tk.DoubleVar(value=0.0)
        self.high_pass_q_var = tk.DoubleVar(value=0.7)
        self.low_pass_q_var = tk.DoubleVar(value=0.7)
        self.high_pass_slope_var = tk.IntVar(value=24)
        self.low_pass_slope_var = tk.IntVar(value=24)
        self.pitch_semitones_var = tk.DoubleVar(value=0.0)
        self.tempo_percent_var = tk.DoubleVar(value=100.0)
        self.peak_normalize_var = tk.BooleanVar(value=False)
        self.limiter_enabled_var = tk.BooleanVar(value=True)
        self.stem_bypass_var = tk.BooleanVar(value=False)
        self.limiter_ceiling_var = tk.DoubleVar(value=0.98)
        self.delete_temp_var = tk.BooleanVar(
            value=bool(self.settings.get("delete_temp_after_render", False))
        )
        self.stem_vars: dict[str, dict[str, tk.Variable]] = {}
        self.stem_volume_label_vars: dict[str, tk.StringVar] = {}
        self.stem_widgets: dict[str, list[tk.Widget]] = {}
        self.effect_widgets: list[tk.Widget] = []
        self.preset_widgets: list[tk.Widget] = []
        self.render_settings_window: tk.Toplevel | None = None
        self._init_workspace()

        self.title("KWAK Split")
        self.geometry(f"{min(1280, self.winfo_screenwidth() - 80)}x{min(900, self.winfo_screenheight() - 120)}")
        self.minsize(640, 480)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._configure_theme()
        self._build_ui()
        self.after(0, self._set_dark_title_bar)
        self._bind_space_shortcut(self)
        self.bind_all("<KeyPress-space>", self._space_toggle_playback)
        self.bind_all("<KeyRelease-space>", self._space_key_released)
        self.bind("<FocusOut>", self._space_key_released, add="+")
        self._enable_file_drop()
        self._enable_window_constraints()
        self._refresh_action_states()
        self.worker_queue_after_id = self.after(100, self._process_worker_queue)
        self.drop_queue_after_id = self.after(100, self._process_drop_queue)
        self.playback_progress_after_id = self.after(100, self._process_playback_progress)
        self._finish_workspace()

    def _configure_logging(self) -> None:
        log_file = self.paths.logs / "app.log"
        handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
        if getattr(sys, "stderr", None):
            handlers.append(logging.StreamHandler())
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=handlers,
        )

    def _set_dark_title_bar(self) -> None:
        if os.name != "nt":
            return
        try:
            hwnd = wintypes.HWND(self.winfo_id())
            value = ctypes.c_int(1)
            dwmapi = ctypes.windll.dwmapi
            for attribute in (20, 19):
                result = dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
        except Exception:
            logging.debug("Dark title bar is not available.", exc_info=True)

    def _legacy_configure_theme(self) -> None:
        self.configure(bg="#090d14")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#090d14"
        panel = "#101722"
        card = "#151c28"
        field = "#0b1018"
        fg = "#e6edf7"
        muted = "#8e9aab"
        accent = "#5aa7ff"

        self.option_add("*TCombobox*Listbox.background", field)
        self.option_add("*TCombobox*Listbox.foreground", fg)
        self.option_add("*TCombobox*Listbox.selectBackground", accent)
        self.option_add("*TCombobox*Listbox.selectForeground", "#08111f")

        style.configure(".", background=bg, foreground=fg, fieldbackground=field, font=("Segoe UI", 9))
        style.configure("TFrame", background=bg)
        style.configure("Root.TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("Card.TFrame", background=card)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("Title.TLabel", background=bg, foreground="#f4f8ff", font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", background=bg, foreground="#aeb8c8", font=("Segoe UI", 9))
        style.configure("StemName.TLabel", background=card, font=("Segoe UI", 10, "bold"))
        style.configure("StemValue.TLabel", background=card, foreground="#f0f5ff", font=("Segoe UI", 10, "bold"))
        style.configure("StemMuted.TLabel", background=card, foreground=muted, font=("Segoe UI", 8))
        style.configure("Card.TCheckbutton", background=card, foreground=fg)
        style.configure("Panel.TLabelframe", background=panel, foreground=fg, bordercolor="#263242", relief="flat")
        style.configure("Panel.TLabelframe.Label", background=bg, foreground="#f0f5ff", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelFrame", background=panel, foreground=fg, bordercolor="#263242")
        style.configure("TLabelFrame.Label", background=bg, foreground="#f0f5ff", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", background="#2a3442", foreground=fg, bordercolor="#3a4656", padding=(10, 5))
        style.configure("Accent.TButton", background=accent, foreground="#08111f", bordercolor=accent, padding=(12, 5))
        style.configure("Danger.TButton", background="#7f3342", foreground="#fff2f4", bordercolor="#9f4656", padding=(10, 5))
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=card, foreground=muted, padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#223449"), ("active", "#1a293b")],
                  foreground=[("selected", "#ffffff"), ("active", fg)])
        style.configure("TCombobox", fieldbackground=field, foreground=fg, background=card,
                        arrowcolor=fg, bordercolor="#344052")
        style.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", fg)],
                  selectbackground=[("readonly", field)], selectforeground=[("readonly", fg)])
        for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(name, background="#344052", troughcolor=field, arrowcolor=muted, bordercolor=bg)
            style.map(name, background=[("active", "#55708f")])
        style.configure("TScale", background=bg, troughcolor="#303948")
        style.configure("TSpinbox", fieldbackground=field, foreground=fg, arrowcolor=fg, bordercolor="#344052")
        style.configure(
            "EQ.TCombobox",
            fieldbackground=field,
            background="#151c28",
            foreground=fg,
            arrowcolor=fg,
            bordercolor="#344052",
            padding=(4, 2),
        )
        style.configure(
            "EQ.TSpinbox",
            fieldbackground=field,
            foreground=fg,
            arrowcolor=fg,
            bordercolor="#344052",
            padding=(3, 2),
        )
        style.configure("Horizontal.TProgressbar", troughcolor="#0d121a", background=accent, bordercolor="#263040")
        style.map(
            "TSpinbox",
            fieldbackground=[("disabled", "#111722"), ("readonly", "#111722")],
            foreground=[("disabled", "#5f6b7a")],
        )
        style.map(
            "EQ.TCombobox",
            fieldbackground=[("disabled", "#111722"), ("readonly", field)],
            foreground=[("disabled", "#5f6b7a"), ("readonly", fg)],
            background=[("active", "#202a3a"), ("disabled", "#111722"), ("readonly", "#151c28")],
            arrowcolor=[("disabled", "#5f6b7a"), ("readonly", fg)],
        )
        style.map(
            "EQ.TSpinbox",
            fieldbackground=[("disabled", "#111722"), ("readonly", "#111722")],
            foreground=[("disabled", "#5f6b7a")],
            arrowcolor=[("disabled", "#5f6b7a")],
        )
        style.map("TCheckbutton", foreground=[("disabled", "#5f6b7a")])
        style.map(
            "TButton",
            background=[("active", "#354153"), ("disabled", "#1b222d")],
            foreground=[("disabled", "#667080")],
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#6bb0ff"), ("disabled", "#1b3657")],
            foreground=[("disabled", "#6d819c")],
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#9a4052"), ("disabled", "#2b2228")],
            foreground=[("disabled", "#806b72")],
        )

    def _legacy_build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.workspace_scroll = ScrollableFrame(self)
        self.workspace_scroll.grid(row=0, column=0, sticky="nsew")
        body = self.workspace_scroll.content
        body.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(body, padding=(12, 10, 12, 8), style="Root.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        toolbar.columnconfigure(1, weight=0)

        title_area = ttk.Frame(toolbar, style="Root.TFrame")
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="KWAK Split", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, textvariable=self.file_label_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        ttk.Label(toolbar, textvariable=self.status_var, style="Status.TLabel", wraplength=680).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        primary_actions = ttk.Frame(toolbar, style="Root.TFrame")
        primary_actions.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.load_button = PillButton(primary_actions, "Open Audio", self.load_file, variant="primary", width=88, bg="#090d14")
        self.load_button.grid(row=0, column=0, padx=(0, 6))
        self.separate_button = PillButton(primary_actions, "Split Stems", self.separate_stems, width=104, bg="#090d14")
        self.separate_button.grid(row=0, column=1, padx=6)
        self.render_button = PillButton(primary_actions, "Export WAV", self.render_wav, variant="primary", width=112, bg="#090d14")
        self.render_button.grid(row=0, column=2, padx=6)
        self.render_mp3_button = PillButton(primary_actions, "Export MP3", self.render_mp3, variant="primary", width=112, bg="#090d14")
        self.render_mp3_button.grid(row=0, column=3, padx=6)

        utility_actions = ttk.Frame(toolbar, style="Root.TFrame")
        utility_actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.cleanup_button = PillButton(utility_actions, "New Project", self.cleanup_current_temp, variant="ghost", width=112, bg="#090d14")
        self.cleanup_button.grid(row=0, column=0, padx=6)
        self.cancel_button = PillButton(utility_actions, "Cancel", self.cancel_current_operation, variant="danger", width=82, bg="#090d14")
        self.cancel_button.grid(row=0, column=1, padx=6)

        self._build_workspace_toolbar(utility_actions, toolbar)
        waveform_frame = ttk.LabelFrame(body, text="Waveform · Left-click to seek / Right-drag to select", padding=8, style="Panel.TLabelframe")
        waveform_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        waveform_frame.columnconfigure(0, weight=1)
        waveform_frame.rowconfigure(0, weight=1)
        self.wave_canvas = tk.Canvas(waveform_frame, height=140, background="#0b1018", highlightthickness=0)
        self.wave_canvas.grid(row=0, column=0, sticky="nsew")
        self.wave_canvas.bind("<Configure>", self._schedule_waveform_resize_draw)
        self.wave_canvas.bind("<Button-1>", self._wave_seek_begin)
        self.wave_canvas.bind("<B1-Motion>", self._wave_seek_to_event)
        self.wave_canvas.bind("<ButtonRelease-1>", self._wave_seek_end)
        self.wave_canvas.bind("<Button-3>", self._wave_mouse_down)
        self.wave_canvas.bind("<B3-Motion>", self._wave_mouse_drag)
        self.wave_canvas.bind("<ButtonRelease-3>", self._wave_mouse_up)

        selection_controls = ttk.Frame(waveform_frame, padding=(0, 8, 0, 0))
        selection_controls.grid(row=1, column=0, sticky="ew")
        selection_controls.columnconfigure(0, minsize=42)
        selection_controls.columnconfigure(1, weight=1)
        selection_controls.columnconfigure(2, minsize=124)
        selection_controls.columnconfigure(3, minsize=112)

        ttk.Label(selection_controls, text="Now").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.playback_scale = FlatSlider(
            selection_controls,
            from_=0,
            to=1,
            variable=self.playback_position_var,
            command=self._playback_position_changed,
            drag_start_command=self._playback_seek_begin,
            drag_end_command=self._playback_seek_end,
        )
        self.playback_scale.grid(row=0, column=1, sticky="ew")
        self.playback_scale.configure(state="disabled")
        self.playback_label = ttk.Label(selection_controls, textvariable=self.playback_label_var, width=22, anchor="e")
        self.playback_label.grid(row=0, column=2, sticky="e", padx=(8, 8))
        self.play_button = PillButton(
            selection_controls,
            "Play (Space)",
            self.toggle_playback,
            width=112,
            height=30,
            bg="#101722",
        )
        self.play_button.grid(row=0, column=3, sticky="e")
        self.select_all_button = PillButton(
            selection_controls,
            "All",
            self.select_all_audio,
            variant="ghost",
            width=112,
            height=30,
            bg="#101722",
        )

        ttk.Label(selection_controls, text="Range").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.range_scale = RangeSlider(
            selection_controls,
            from_=0,
            to=1,
            start_variable=self.selection_start_var,
            end_variable=self.selection_end_var,
            command=self._selection_changed,
        )
        self.range_scale.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.selection_label = ttk.Label(selection_controls, text="0:00 - 0:00", width=34, anchor="e")
        self.selection_label.grid(row=1, column=2, sticky="e", padx=(8, 8), pady=(8, 0))
        self.select_all_button.grid(row=1, column=3, sticky="e", pady=(8, 0))

        range_values = ttk.Frame(selection_controls)
        range_values.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        range_values.columnconfigure(4, weight=1)
        ttk.Label(range_values, text="Start").grid(row=0, column=0, sticky="w")
        self.start_spinbox = ttk.Spinbox(
            range_values,
            from_=0,
            to=1,
            increment=0.01,
            textvariable=self.selection_start_var,
            width=9,
            format="%.2f",
            command=self._selection_changed,
        )
        self.start_spinbox.grid(row=0, column=1, sticky="w", padx=(6, 14))
        ttk.Label(range_values, text="End").grid(row=0, column=2, sticky="w")
        self.end_spinbox = ttk.Spinbox(
            range_values,
            from_=0,
            to=1,
            increment=0.01,
            textvariable=self.selection_end_var,
            width=9,
            format="%.2f",
            command=self._selection_changed,
        )
        self.end_spinbox.grid(row=0, column=3, sticky="w", padx=(6, 14))
        for widget in (self.start_spinbox, self.end_spinbox):
            widget.bind("<Return>", lambda _event: self._selection_changed())
            widget.bind("<FocusOut>", lambda _event: self._selection_changed())

        self._build_range_tools(waveform_frame)
        controls = ttk.Notebook(body)
        self.editor_tabs = controls
        controls.grid(row=2, column=0, sticky="nsew")

        mixer = ttk.Frame(controls, padding=8, style="Panel.TFrame")
        controls.add(mixer, text="  Stem Mixer  ")
        self._build_mixer(mixer)

        quick_box = ttk.LabelFrame(controls, text="Preset / Monitor", padding=8, style="Panel.TLabelframe")
        controls.add(quick_box, text="  Presets · Pitch · Fades  ")
        self._build_quick_actions(quick_box)

        render_box = ttk.Frame(controls, padding=8, style="Panel.TFrame")
        controls.add(render_box, text="  EQ · Filters  ")
        self._build_render_options(render_box)

        progress_frame = ttk.Frame(body, padding=(10, 8))
        progress_frame.grid(row=3, column=0, sticky="nsew")
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(2, weight=1)
        self.progressbar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progressbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        log_toolbar = ttk.Frame(progress_frame)
        log_toolbar.grid(row=1, column=0, sticky="ew")
        log_toolbar.columnconfigure(0, weight=1)
        ttk.Label(log_toolbar, text="Check processing status and exported files below.", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.settings_button = PillButton(
            log_toolbar,
            "Settings",
            self.open_render_settings,
            variant="ghost",
            width=92,
            height=30,
            bg="#090d14",
        )
        self.settings_button.grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.log_toggle_button = PillButton(
            log_toolbar,
            "Show Log",
            self.toggle_log_visibility,
            variant="ghost",
            width=92,
            height=30,
            bg="#090d14",
        )
        self.log_toggle_button.grid(row=0, column=2, sticky="e")
        self.log_text = tk.Text(
            progress_frame,
            height=8,
            wrap="word",
            state="disabled",
            background="#0d121a",
            foreground="#d7dee8",
            insertbackground="#d7dee8",
            relief="flat",
        )
        self.log_text.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.log_text.grid_remove()
        self._build_result_area(body)

        self.action_buttons = [
            self.load_button,
            self.separate_button,
            self.play_button,
            self.render_button,
            self.render_mp3_button,
            self.export_stems_button,
            self.cleanup_button,
            self.cancel_button,
            self.select_all_button,
        ]
        self._update_selection_label()

    def _build_mixer(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        for column in range(len(STEMS)):
            parent.columnconfigure(column, weight=1, uniform="stems")

        self.stem_bypass_button = PillButton(
            parent,
            "Stem Bypass OFF",
            self.toggle_stem_bypass,
            variant="ghost",
            width=156,
            height=28,
            bg="#101722",
        )
        self.stem_bypass_button.grid(row=0, column=0, columnspan=len(STEMS), sticky="e", pady=(0, 8))

        for column, stem in enumerate(STEMS):
            volume_var = tk.DoubleVar(value=100.0)
            mute_var = tk.BooleanVar(value=False)
            solo_var = tk.BooleanVar(value=False)
            volume_label_var = tk.StringVar(value="0.0 dB")
            self.stem_vars[stem] = {
                "volume": volume_var,
                "mute": mute_var,
                "solo": solo_var,
            }
            self.stem_volume_label_vars[stem] = volume_label_var

            card_bg = "#151c28"
            color = STEM_COLORS.get(stem, "#5aa7ff")
            card = tk.Frame(
                parent,
                background=card_bg,
                bd=0,
                highlightbackground="#263242",
                highlightcolor="#34445a",
                highlightthickness=1,
                padx=5,
                pady=7,
            )
            card.grid(row=1, column=column, sticky="nsew", padx=3)
            card.columnconfigure(0, weight=1)
            card.columnconfigure(1, weight=1)
            card.columnconfigure(2, weight=1)
            card.rowconfigure(2, weight=1, minsize=210)

            tk.Label(
                card,
                text=STEM_LABELS.get(stem, stem.title()),
                bg=card_bg,
                fg=color,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=0, columnspan=3, sticky="w")
            tk.Frame(card, background=color, height=2).grid(
                row=1, column=0, columnspan=3, sticky="ew", pady=(6, 8)
            )
            scale = StemFader(card, volume_var, color, bg=card_bg)
            scale.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 8))
            percent_label = tk.Label(
                card,
                textvariable=volume_label_var,
                bg=card_bg,
                fg="#f3f7ff",
                font=("Segoe UI", 10, "bold"),
            )
            percent_label.grid(row=3, column=0, columnspan=3, pady=(0, 6))
            reset_button = PillButton(
                card,
                "0 dB",
                lambda stem=stem: self.reset_stem_volume(stem),
                variant="ghost",
                width=46,
                height=26,
                bg=card_bg,
            )
            reset_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 6))
            toggle_frame = tk.Frame(card, bg=card_bg)
            toggle_frame.grid(row=5, column=0, columnspan=3)
            toggle_frame.columnconfigure(0, weight=1)
            toggle_frame.columnconfigure(1, weight=1)
            mute_check = tk.Checkbutton(
                toggle_frame,
                text="M",
                variable=mute_var,
                indicatoron=False,
                width=2,
                bg="#202938",
                fg="#cbd5e1",
                activebackground="#2a3545",
                activeforeground="#ffffff",
                selectcolor="#4a2a34",
                disabledforeground="#606b7a",
                relief="flat",
                bd=0,
                highlightthickness=0,
            )
            mute_check.grid(row=0, column=0, padx=(0, 4))
            solo_check = tk.Checkbutton(
                toggle_frame,
                text="S",
                variable=solo_var,
                indicatoron=False,
                width=2,
                bg="#202938",
                fg="#cbd5e1",
                activebackground="#2a3545",
                activeforeground="#ffffff",
                selectcolor="#223e5f",
                disabledforeground="#606b7a",
                relief="flat",
                bd=0,
                highlightthickness=0,
            )
            solo_check.grid(row=0, column=1, padx=(4, 0))

            volume_var.trace_add("write", lambda *_args, stem=stem: self._on_stem_volume_changed(stem))
            mute_var.trace_add("write", lambda *_args: self._schedule_live_preview_restart())
            solo_var.trace_add("write", lambda *_args: self._schedule_live_preview_restart())
            self.stem_widgets[stem] = [
                scale,
                reset_button,
                mute_check,
                solo_check,
            ]
            self._update_volume_label(stem)

    def _build_render_options(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.eq_editor = EqCurveEditor(
            parent,
            self.eq_low_var,
            self.eq_mid_var,
            self.eq_high_var,
            self.eq_low_freq_var,
            self.eq_mid_freq_var,
            self.eq_high_freq_var,
            self.eq_low_q_var,
            self.eq_mid_q_var,
            self.eq_high_q_var,
            self.eq_low_shape_var,
            self.eq_mid_shape_var,
            self.eq_high_shape_var,
            self.high_pass_var,
            self.low_pass_var,
            self.high_pass_q_var,
            self.low_pass_q_var,
        )
        self.eq_editor.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        knob_grid = ttk.Frame(parent)
        knob_grid.grid(row=1, column=0, sticky="ew")
        for column in range(5):
            knob_grid.columnconfigure(column, weight=1, uniform="eq_knobs")

        db_label = lambda value: f"{value:+.1f} dB" if abs(value) >= 0.05 else "0.0 dB"
        freq_label = lambda value: "off" if value <= 0 else f"{int(round(value))} Hz"

        def compact_freq_label(value: float) -> str:
            if value <= 0:
                return "off"
            if value >= 1000:
                return f"{value / 1000:.1f}k"
            return f"{value:.0f}Hz"

        def eq_band_label(freq_var: tk.DoubleVar) -> Callable[[float], str]:
            return lambda value: f"{compact_freq_label(float(freq_var.get()))}\n{db_label(value).replace(' ', '')}"

        def freq_value_to_ratio(value: float) -> float:
            if value <= 0:
                return 0.0
            value = max(min(value, EqCurveEditor.MAX_FREQ), EqCurveEditor.MIN_FREQ)
            span = math.log10(EqCurveEditor.MAX_FREQ) - math.log10(EqCurveEditor.MIN_FREQ)
            return (math.log10(value) - math.log10(EqCurveEditor.MIN_FREQ)) / span

        def freq_ratio_to_value(ratio: float) -> float:
            ratio = max(min(ratio, 1.0), 0.0)
            if ratio <= 0:
                return 0.0
            span = math.log10(EqCurveEditor.MAX_FREQ) - math.log10(EqCurveEditor.MIN_FREQ)
            value = 10 ** (math.log10(EqCurveEditor.MIN_FREQ) + ratio * span)
            if value < 100:
                return round(value)
            if value < 1000:
                return round(value / 5.0) * 5.0
            return round(value / 100.0) * 100.0

        def low_pass_value_to_ratio(value: float) -> float:
            if value <= 0:
                return 0.0
            value = max(min(value, EqCurveEditor.MAX_FREQ), EqCurveEditor.MIN_FREQ)
            span = math.log10(EqCurveEditor.MAX_FREQ) - math.log10(EqCurveEditor.MIN_FREQ)
            return (math.log10(EqCurveEditor.MAX_FREQ) - math.log10(value)) / span

        def low_pass_ratio_to_value(ratio: float) -> float:
            ratio = max(min(ratio, 1.0), 0.0)
            if ratio <= 0:
                return 0.0
            span = math.log10(EqCurveEditor.MAX_FREQ) - math.log10(EqCurveEditor.MIN_FREQ)
            value = 10 ** (math.log10(EqCurveEditor.MAX_FREQ) - ratio * span)
            if value < 100:
                return round(value)
            if value < 1000:
                return round(value / 5.0) * 5.0
            return round(value / 100.0) * 100.0

        self.eq_low_spinbox = KnobControl(
            knob_grid,
            self.eq_low_var,
            "Low",
            from_=-12,
            to=12,
            increment=0.5,
            color=EqCurveEditor.COLORS["low"],
            value_format=eq_band_label(self.eq_low_freq_var),
            extra_variables=(self.eq_low_freq_var,),
            reset_command=lambda: self._reset_eq_band("low"),
        )
        self.eq_low_spinbox.grid(row=0, column=1, sticky="ew")

        self.eq_mid_spinbox = KnobControl(
            knob_grid,
            self.eq_mid_var,
            "Mid",
            from_=-12,
            to=12,
            increment=0.5,
            color=EqCurveEditor.COLORS["mid"],
            value_format=eq_band_label(self.eq_mid_freq_var),
            extra_variables=(self.eq_mid_freq_var,),
            reset_command=lambda: self._reset_eq_band("mid"),
        )
        self.eq_mid_spinbox.grid(row=0, column=2, sticky="ew")

        self.eq_high_spinbox = KnobControl(
            knob_grid,
            self.eq_high_var,
            "High",
            from_=-12,
            to=12,
            increment=0.5,
            color=EqCurveEditor.COLORS["high"],
            value_format=eq_band_label(self.eq_high_freq_var),
            extra_variables=(self.eq_high_freq_var,),
            reset_command=lambda: self._reset_eq_band("high"),
        )
        self.eq_high_spinbox.grid(row=0, column=3, sticky="ew")

        self.high_pass_spinbox = KnobControl(
            knob_grid,
            self.high_pass_var,
            "HP",
            from_=0,
            to=20000,
            increment=10,
            color=EqCurveEditor.COLORS["hp"],
            value_format=freq_label,
            value_to_ratio=freq_value_to_ratio,
            ratio_to_value=freq_ratio_to_value,
            reset_command=lambda: self._reset_eq_cut("hp"),
        )
        self.high_pass_spinbox.grid(row=0, column=0, sticky="ew")

        self.low_pass_spinbox = KnobControl(
            knob_grid,
            self.low_pass_var,
            "LP",
            from_=0,
            to=20000,
            increment=100,
            color=EqCurveEditor.COLORS["lp"],
            value_format=freq_label,
            value_to_ratio=low_pass_value_to_ratio,
            ratio_to_value=low_pass_ratio_to_value,
            reset_command=lambda: self._reset_eq_cut("lp"),
        )
        self.low_pass_spinbox.grid(row=0, column=4, sticky="ew")

        eq_shape_grid = ttk.Frame(parent, style="Panel.TFrame")
        self.eq_detail_frame = eq_shape_grid
        eq_shape_grid.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for column in range(5):
            eq_shape_grid.columnconfigure(column, weight=1, uniform="eq_shape")

        self.eq_shape_widgets: list[tk.Widget] = []
        self._add_filter_q_control(eq_shape_grid, 0, "HP", EqCurveEditor.COLORS["hp"], self.high_pass_q_var)
        self._add_eq_band_controls(eq_shape_grid, 1, "Low", EqCurveEditor.COLORS["low"], self.eq_low_shape_var, self.eq_low_q_var)
        self._add_eq_band_controls(eq_shape_grid, 2, "Mid", EqCurveEditor.COLORS["mid"], self.eq_mid_shape_var, self.eq_mid_q_var)
        self._add_eq_band_controls(eq_shape_grid, 3, "High", EqCurveEditor.COLORS["high"], self.eq_high_shape_var, self.eq_high_q_var)
        self._add_filter_q_control(eq_shape_grid, 4, "LP", EqCurveEditor.COLORS["lp"], self.low_pass_q_var)
        eq_shape_grid.bind("<Configure>", self._layout_eq_details)

        eq_footer = ttk.Frame(parent, style="Panel.TFrame")
        eq_footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        eq_footer.columnconfigure(0, weight=1)
        ttk.Label(eq_footer, text="EQ response curve · Not an audio spectrum analyzer", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.eq_reset_button = PillButton(
            eq_footer,
            "Reset EQ",
            self.reset_eq,
            variant="ghost",
            width=92,
            height=30,
            bg="#101722",
        )
        self.eq_reset_button.grid(row=0, column=1, sticky="e")

        self.effect_widgets = [
            self.eq_reset_button,
            self.eq_low_spinbox,
            self.eq_mid_spinbox,
            self.eq_high_spinbox,
            self.high_pass_spinbox,
            self.low_pass_spinbox,
            self.pitch_spinbox,
            self.tempo_spinbox,
            self.fade_in_spinbox,
            self.fade_out_spinbox,
            *self.eq_shape_widgets,
        ]
        for variable in (self.fade_in_var, self.fade_out_var):
            variable.trace_add("write", lambda *_args: self._schedule_fade_live_preview_restart())
            variable.trace_add("write", lambda *_args: self._schedule_fade_waveform_draw())
        for variable in (
            self.eq_low_var,
            self.eq_mid_var,
            self.eq_high_var,
            self.eq_low_freq_var,
            self.eq_mid_freq_var,
            self.eq_high_freq_var,
            self.eq_low_q_var,
            self.eq_mid_q_var,
            self.eq_high_q_var,
            self.high_pass_q_var,
            self.low_pass_q_var,
            self.eq_low_shape_var,
            self.eq_mid_shape_var,
            self.eq_high_shape_var,
            self.high_pass_var,
            self.low_pass_var,
            self.pitch_semitones_var,
            self.tempo_percent_var,
            self.peak_normalize_var,
            self.limiter_enabled_var,
            self.limiter_ceiling_var,
        ):
            variable.trace_add("write", lambda *_args: self._schedule_live_preview_restart())
    def _layout_eq_details(self, event) -> None:
        columns = 5 if self.workspace_scroll.canvas.winfo_width() >= 1100 else 3
        frame = self.eq_detail_frame
        if getattr(frame, "_layout_columns", None) == columns:
            return
        frame._layout_columns = columns
        for column in range(5):
            frame.columnconfigure(column, weight=1 if column < columns else 0,
                                  uniform="eq_detail" if column < columns else "", minsize=0)
        for index, cell in enumerate(frame.winfo_children()):
            cell.grid(row=index // columns, column=index % columns, sticky="ew", padx=4, pady=4)

    def _add_eq_band_controls(
        self,
        parent: ttk.Frame,
        column: int,
        label: str,
        color: str,
        shape_var: tk.StringVar,
        q_var: tk.DoubleVar,
    ) -> None:
        frame = self._build_eq_detail_cell(parent, column, label, color)
        frame.columnconfigure(0, weight=1)
        shape_box = ttk.Combobox(
            frame,
            textvariable=shape_var,
            values=EQ_SHAPES,
            state="readonly",
            width=11,
            justify="center",
            font=("Segoe UI", 9, "bold"),
            style="EQ.TCombobox",
        )
        shape_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        tk.Label(frame, text="Q", bg="#0b1018", fg="#aeb8c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="e", padx=(0, 3))
        q_spinbox = ttk.Spinbox(
            frame,
            from_=0.1,
            to=10.0,
            increment=0.1,
            textvariable=q_var,
            width=5,
            format="%.1f",
            justify="center",
            font=("Segoe UI", 9, "bold"),
            style="EQ.TSpinbox",
        )
        q_spinbox.grid(row=0, column=2, sticky="e")
        self._bind_eq_q_drag(q_spinbox, q_var)
        self.eq_shape_widgets.extend([shape_box, q_spinbox])

    def _add_filter_q_control(
        self,
        parent: ttk.Frame,
        column: int,
        label: str,
        color: str,
        q_var: tk.DoubleVar,
    ) -> None:
        frame = self._build_eq_detail_cell(parent, column, label, color)
        frame.columnconfigure(0, weight=1)
        tk.Label(frame, text="Q", bg="#0b1018", fg="#aeb8c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 3))
        q_spinbox = ttk.Spinbox(
            frame,
            from_=0.1,
            to=10.0,
            increment=0.1,
            textvariable=q_var,
            width=5,
            format="%.1f",
            justify="center",
            font=("Segoe UI", 9, "bold"),
            style="EQ.TSpinbox",
        )
        q_spinbox.grid(row=0, column=1, sticky="e")
        self._bind_eq_q_drag(q_spinbox, q_var)
        self.eq_shape_widgets.append(q_spinbox)

    def _build_eq_detail_cell(
        self,
        parent: ttk.Frame,
        column: int,
        label: str,
        color: str,
    ) -> tk.Frame:
        cell = tk.Frame(
            parent,
            bg="#0b1018",
            highlightthickness=1,
            highlightbackground="#243043",
            highlightcolor="#344052",
        )
        cell.grid(row=0, column=column, sticky="ew", padx=4)
        cell.columnconfigure(0, weight=1)

        header = tk.Frame(cell, bg="#0b1018")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(7, 4))
        tk.Frame(header, bg=color, width=26, height=3).pack(side="left", padx=(0, 6), pady=(8, 0))
        tk.Label(
            header,
            text=label,
            bg="#0b1018",
            fg="#f0f5ff",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left")

        controls = tk.Frame(cell, bg="#0b1018")
        controls.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        return controls

    def _bind_eq_q_drag(self, widget: ttk.Spinbox, variable: tk.DoubleVar) -> None:
        drag_state = {"active": False, "y": 0, "value": 1.0}

        def enabled() -> bool:
            return str(widget.cget("state")) != "disabled"

        def current_value() -> float:
            try:
                return float(variable.get())
            except (TypeError, ValueError, tk.TclError):
                return 1.0

        def set_value(value: float) -> None:
            variable.set(round(max(min(value, 10.0), 0.1), 1))

        def begin_drag(event: tk.Event) -> None:
            if not enabled():
                return
            drag_state["active"] = True
            drag_state["y"] = int(getattr(event, "y_root", event.y))
            drag_state["value"] = current_value()

        def drag(event: tk.Event) -> str | None:
            if not drag_state["active"] or not enabled():
                return None
            delta = drag_state["y"] - int(getattr(event, "y_root", event.y))
            set_value(drag_state["value"] + delta * 0.02)
            return "break"

        def end_drag(_event: tk.Event) -> None:
            drag_state["active"] = False

        def wheel(event: tk.Event) -> str | None:
            if not enabled():
                return None
            step = 0.1 if event.delta > 0 else -0.1
            set_value(current_value() + step)
            return "break"

        widget.bind("<ButtonPress-1>", begin_drag, add="+")
        widget.bind("<B1-Motion>", drag, add="+")
        widget.bind("<ButtonRelease-1>", end_drag, add="+")
        widget.bind("<MouseWheel>", wheel, add="+")

    def _bind_fade_drag(self, widget: ttk.Spinbox, variable: tk.DoubleVar) -> None:
        drag_state = {"active": False, "y": 0, "value": 0.0, "changed": False}

        def enabled() -> bool:
            return str(widget.cget("state")) != "disabled"

        def current_value() -> float:
            try:
                return float(variable.get())
            except (TypeError, ValueError, tk.TclError):
                return 0.0

        def set_value(value: float) -> None:
            new_value = round(max(value, 0.0), 2)
            if new_value == current_value():
                return
            variable.set(new_value)
            drag_state["changed"] = True

        def begin_drag(event: tk.Event) -> None:
            if not enabled():
                return
            drag_state["active"] = True
            drag_state["changed"] = False
            drag_state["y"] = int(getattr(event, "y_root", event.y))
            drag_state["value"] = current_value()
            self.fade_control_dragging = True

        def drag(event: tk.Event) -> str | None:
            if not drag_state["active"] or not enabled():
                return None
            delta = drag_state["y"] - int(getattr(event, "y_root", event.y))
            set_value(drag_state["value"] + delta * 0.01)
            return "break"

        def end_drag(_event: tk.Event) -> None:
            was_active = drag_state["active"]
            changed = drag_state["changed"] or current_value() != drag_state["value"]
            drag_state["active"] = False
            self.fade_control_dragging = False
            if was_active and changed:
                self._schedule_fade_waveform_draw(force_full=True)
                self._schedule_live_preview_restart()

        def wheel(event: tk.Event) -> str | None:
            if not enabled():
                return None
            step = 1.00 if event.delta > 0 else -1.00
            set_value(current_value() + step)
            return "break"

        widget.bind("<ButtonPress-1>", begin_drag, add="+")
        widget.bind("<B1-Motion>", drag, add="+")
        widget.bind("<ButtonRelease-1>", end_drag, add="+")
        widget.bind("<MouseWheel>", wheel, add="+")

    def _bind_spinbox_drag(
        self,
        widget: ttk.Spinbox,
        variable: tk.DoubleVar,
        *,
        minimum: float,
        maximum: float,
        sensitivity: float,
        wheel_step: float,
        decimals: int,
    ) -> None:
        drag_state = {"active": False, "y": 0, "value": 0.0}

        def enabled() -> bool:
            return str(widget.cget("state")) != "disabled"

        def current_value() -> float:
            try:
                return float(variable.get())
            except (TypeError, ValueError, tk.TclError):
                return 0.0

        def set_value(value: float) -> None:
            new_value = round(min(max(value, minimum), maximum), decimals)
            if new_value != current_value():
                variable.set(new_value)

        def begin_drag(event: tk.Event) -> None:
            if not enabled():
                return
            drag_state["active"] = True
            drag_state["y"] = int(getattr(event, "y_root", event.y))
            drag_state["value"] = current_value()

        def drag(event: tk.Event) -> str | None:
            if not drag_state["active"] or not enabled():
                return None
            delta = drag_state["y"] - int(getattr(event, "y_root", event.y))
            set_value(drag_state["value"] + delta * sensitivity)
            return "break"

        def end_drag(_event: tk.Event) -> None:
            drag_state["active"] = False

        def wheel(event: tk.Event) -> str | None:
            if not enabled():
                return None
            step = wheel_step if event.delta > 0 else -wheel_step
            set_value(current_value() + step)
            return "break"

        widget.bind("<ButtonPress-1>", begin_drag, add="+")
        widget.bind("<B1-Motion>", drag, add="+")
        widget.bind("<ButtonRelease-1>", end_drag, add="+")
        widget.bind("<MouseWheel>", wheel, add="+")

    def _build_quick_actions(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Stem Presets").grid(row=0, column=0, sticky="w")
        preset_frame = ttk.Frame(parent)
        preset_frame.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.columnconfigure(1, weight=1)
        for index, (label, selected) in enumerate(STEM_PRESETS):
            button = PillButton(
                preset_frame,
                label,
                lambda label=label, selected=selected: self.apply_stem_preset(label, selected),
                variant="ghost",
                width=116,
                height=30,
                bg="#101722",
            )
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 4, 4), pady=2)
            self.preset_widgets.append(button)

        self.preview_source_button = PillButton(
            parent,
            "Original",
            self.toggle_stem_bypass,
            variant="ghost",
            width=244,
            height=31,
            bg="#101722",
        )
        self.preview_source_button.grid_remove()
        self._update_stem_bypass_button()
        self.export_stems_button = PillButton(
            parent,
            "Export Stems",
            self.export_individual_stems,
            variant="ghost",
            width=244,
            height=31,
            bg="#101722",
        )
        self.export_stems_button.grid(row=4, column=0, sticky="ew", pady=(14, 0))

        effect_label_width = 68
        effect_unit_width = 28

        fade_frame = ttk.Frame(parent)
        fade_frame.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        fade_frame.columnconfigure(0, minsize=effect_label_width)
        fade_frame.columnconfigure(1, weight=1)
        fade_frame.columnconfigure(2, minsize=effect_unit_width)

        ttk.Label(fade_frame, text="Fade In").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.fade_in_spinbox = ttk.Spinbox(
            fade_frame,
            from_=0.0,
            to=float("inf"),
            increment=0.01,
            textvariable=self.fade_in_var,
            width=7,
            format="%.2f",
            justify="center",
        )
        self.fade_in_spinbox.grid(row=0, column=1, sticky="ew", padx=(10, 6), pady=(0, 6))
        self._bind_fade_drag(self.fade_in_spinbox, self.fade_in_var)
        self._bind_ctrl_click_reset(self.fade_in_spinbox, self.fade_in_var, 0.02)
        ttk.Label(fade_frame, text="sec", style="Muted.TLabel").grid(row=0, column=2, sticky="w", pady=(0, 6))

        ttk.Label(fade_frame, text="Fade Out").grid(row=1, column=0, sticky="w")
        self.fade_out_spinbox = ttk.Spinbox(
            fade_frame,
            from_=0.0,
            to=float("inf"),
            increment=0.01,
            textvariable=self.fade_out_var,
            width=7,
            format="%.2f",
            justify="center",
        )
        self.fade_out_spinbox.grid(row=1, column=1, sticky="ew", padx=(10, 6))
        self._bind_fade_drag(self.fade_out_spinbox, self.fade_out_var)
        self._bind_ctrl_click_reset(self.fade_out_spinbox, self.fade_out_var, 0.02)
        ttk.Label(fade_frame, text="sec", style="Muted.TLabel").grid(row=1, column=2, sticky="w")

        pitch_tempo_frame = ttk.Frame(parent)
        pitch_tempo_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        pitch_tempo_frame.columnconfigure(0, minsize=effect_label_width)
        pitch_tempo_frame.columnconfigure(1, weight=1)
        pitch_tempo_frame.columnconfigure(2, minsize=effect_unit_width)

        ttk.Label(pitch_tempo_frame, text="Pitch").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.pitch_spinbox = ttk.Spinbox(
            pitch_tempo_frame,
            from_=-12.0,
            to=12.0,
            increment=1.0,
            textvariable=self.pitch_semitones_var,
            width=7,
            format="%.0f",
            justify="center",
        )
        self.pitch_spinbox.grid(row=0, column=1, sticky="ew", padx=(10, 6), pady=(0, 6))
        self._bind_spinbox_drag(
            self.pitch_spinbox,
            self.pitch_semitones_var,
            minimum=-12.0,
            maximum=12.0,
            sensitivity=0.1,
            wheel_step=1.0,
            decimals=0,
        )
        self._bind_ctrl_click_reset(self.pitch_spinbox, self.pitch_semitones_var, 0.0)
        ttk.Label(pitch_tempo_frame, text="st", style="Muted.TLabel").grid(row=0, column=2, sticky="w", pady=(0, 6))

        ttk.Label(pitch_tempo_frame, text="Speed").grid(row=1, column=0, sticky="w")
        self.tempo_spinbox = ttk.Spinbox(
            pitch_tempo_frame,
            from_=50.0,
            to=200.0,
            increment=0.5,
            textvariable=self.tempo_percent_var,
            width=7,
            format="%.1f",
            justify="center",
        )
        self.tempo_spinbox.grid(row=1, column=1, sticky="ew", padx=(10, 6))
        self._bind_spinbox_drag(
            self.tempo_spinbox,
            self.tempo_percent_var,
            minimum=50.0,
            maximum=200.0,
            sensitivity=0.5,
            wheel_step=0.5,
            decimals=1,
        )
        self._bind_ctrl_click_reset(self.tempo_spinbox, self.tempo_percent_var, 100.0)
        ttk.Label(pitch_tempo_frame, text="%", style="Muted.TLabel").grid(row=1, column=2, sticky="w")


    def _bind_ctrl_click_reset(self, widget: tk.Widget, variable: tk.Variable, value: float) -> None:
        def reset(_event: tk.Event) -> str:
            if str(widget.cget("state")) == "disabled":
                return "break"
            variable.set(value)
            return "break"

        widget.bind("<Control-Button-1>", reset, add="+")

    def _enable_file_drop(self) -> None:
        if os.name != "nt":
            return
        try:
            self.update_idletasks()
            shell32 = ctypes.windll.shell32
            user32 = ctypes.windll.user32
            wm_dropfiles = 0x0233
            wm_copyglobaldata = 0x0049
            wm_copydata = 0x004A
            msgflt_allow = 1
            gwlp_wndproc = -4
            wndproc_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )

            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
            shell32.DragQueryFileW.restype = wintypes.UINT
            shell32.DragFinish.argtypes = [wintypes.HANDLE]
            change_filter = getattr(user32, "ChangeWindowMessageFilterEx", None)
            if change_filter:
                change_filter.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p]
                change_filter.restype = wintypes.BOOL

            set_window_long = user32.SetWindowLongPtrW
            set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            set_window_long.restype = ctypes.c_void_p
            user32.CallWindowProcW.argtypes = [
                ctypes.c_void_p,
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.CallWindowProcW.restype = ctypes.c_ssize_t

            def wndproc(window: int, message: int, wparam: int, lparam: int) -> int:
                if message == wm_dropfiles:
                    try:
                        file_count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                        if file_count:
                            length = shell32.DragQueryFileW(wparam, 0, None, 0)
                            buffer = ctypes.create_unicode_buffer(length + 1)
                            shell32.DragQueryFileW(wparam, 0, buffer, length + 1)
                            self.append_log(f"Drop event: {buffer.value}")
                            self.drop_queue.put(Path(buffer.value))
                    finally:
                        shell32.DragFinish(wparam)
                    return 0
                old_wndproc = self._drop_old_wndprocs.get(int(window)) or self._drop_old_wndproc
                if old_wndproc:
                    return user32.CallWindowProcW(old_wndproc, window, message, wparam, lparam)
                return 0

            self._drop_wndproc = wndproc_type(wndproc)
            callback_ptr = ctypes.cast(self._drop_wndproc, ctypes.c_void_p)

            hwnds: list[int] = []

            def collect_hwnds(widget: tk.Widget) -> None:
                try:
                    widget.update_idletasks()
                    hwnd = int(widget.winfo_id())
                except tk.TclError:
                    hwnd = 0
                if hwnd and hwnd not in hwnds:
                    hwnds.append(hwnd)
                for child in widget.winfo_children():
                    collect_hwnds(child)

            collect_hwnds(self)
            if not hwnds:
                raise ctypes.WinError()

            for hwnd in hwnds:
                if change_filter:
                    for message in (wm_dropfiles, wm_copyglobaldata, wm_copydata):
                        change_filter(wintypes.HWND(hwnd), message, msgflt_allow, None)
                shell32.DragAcceptFiles(wintypes.HWND(hwnd), True)
                old_wndproc = set_window_long(wintypes.HWND(hwnd), gwlp_wndproc, callback_ptr)
                if not old_wndproc:
                    shell32.DragAcceptFiles(wintypes.HWND(hwnd), False)
                    if hwnd == int(self.winfo_id()):
                        raise ctypes.WinError()
                    continue
                self._drop_old_wndprocs[hwnd] = int(old_wndproc)
                self._drop_hwnds.append(hwnd)

            if not self._drop_hwnds:
                raise ctypes.WinError()
            self._drop_hwnd = int(self.winfo_id())
            self._drop_old_wndproc = self._drop_old_wndprocs.get(self._drop_hwnd)
            self.append_log(f"Drag and drop is ready on {len(self._drop_hwnds)} windows.")
        except Exception as exc:
            self._disable_file_drop()
            logging.exception("Failed to enable drag and drop")
            self.append_log(f"Drag and drop setup failed: {exc}")

    def _disable_file_drop(self) -> None:
        if os.name != "nt" or not self._drop_hwnds:
            return
        try:
            shell32 = ctypes.windll.shell32
            user32 = ctypes.windll.user32
            gwlp_wndproc = -4
            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            for hwnd in reversed(self._drop_hwnds):
                shell32.DragAcceptFiles(wintypes.HWND(hwnd), False)
                old_wndproc = self._drop_old_wndprocs.get(hwnd)
                if old_wndproc:
                    user32.SetWindowLongPtrW(wintypes.HWND(hwnd), gwlp_wndproc, ctypes.c_void_p(old_wndproc))
        except Exception:
            logging.exception("Failed to disable drag and drop")
        finally:
            self._drop_hwnds.clear()
            self._drop_old_wndprocs.clear()
            self._drop_old_wndproc = None
            self._drop_hwnd = None
            self._drop_wndproc = None

    def _process_drop_queue(self) -> None:
        self.drop_queue_after_id = None
        try:
            while True:
                dropped_path = self.drop_queue.get_nowait()
                self.append_log(f"Dropped file: {dropped_path}")
                self.load_audio_path(dropped_path)
        except queue.Empty:
            pass
        if not self.closing:
            self.drop_queue_after_id = self.after(100, self._process_drop_queue)

    def _process_playback_progress(self) -> None:
        self.playback_progress_after_id = None
        if self.preview_playing and not self.playback_seek_dragging:
            self._update_playback_position()
        if not self.closing:
            self.playback_progress_after_id = self.after(100, self._process_playback_progress)

    def load_file(self) -> None:
        if self.busy:
            return
        file_path = filedialog.askopenfilename(
            title="Open Audio",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.flac *.m4a"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("FLAC", "*.flac"),
                ("M4A", "*.m4a"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return
        self.load_audio_path(Path(file_path))

    def load_audio_path(self, input_path: Path) -> bool:
        """Return whether a load started, so rejected project relinks cannot linger."""
        if self.busy:
            self.status_var.set("Wait for the current task to finish.")
            return False
        input_path = input_path.resolve()
        if not input_path.exists() or not input_path.is_file():
            messagebox.showwarning("Open Audio", "This is not a loadable audio file.")
            return False
        if input_path.suffix.lower() not in AUDIO_EXTENSIONS:
            messagebox.showwarning("Open Audio", "Only WAV, MP3, FLAC, and M4A files are supported.")
            return False
        if not self._opening_project and not self._guard_project(lambda: self.load_audio_path(input_path)):
            return False
        self.stop_preview(show_status=False)
        session_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{safe_name(input_path.stem)}"

        def worker() -> None:
            self._queue_status("Converting working audio")
            source_dir = self.paths.temp / "sessions" / session_name
            source_wav = source_dir / "source.wav"
            convert_to_work_wav(
                self.paths,
                input_path,
                source_wav,
                self._queue_log,
                self.cancel_event,
                self._register_process,
            )
            duration = read_duration(self.paths, source_wav)
            self._queue_status("Preparing waveform")
            peaks = stereo_waveform_peaks(
                self.paths,
                source_wav,
                cancel_event=self.cancel_event,
                process_callback=self._register_process,
            )
            self.worker_queue.put(
                (
                    "source_ready",
                    {
                        "input": str(input_path),
                        "source_wav": str(source_wav),
                        "session": session_name,
                        "duration": duration,
                        "peaks": peaks,
                        "channels": audio_channels(self.paths, input_path, self.cancel_event, self._register_process),
                    },
                )
            )

        self._run_worker("Open Audio", worker)
        return True

    def separate_stems(self) -> None:
        if self.busy:
            return
        if not self.source_wav:
            messagebox.showwarning("Audio required", "Load an audio file first.")
            return
        if not StemSeparator(self.paths).available_command():
            self.environment_details()
            return
        try:
            split_start, split_end = self._selection_bounds() if self.split_scope_var.get() == "Selection" else (0.0, self.duration_seconds)
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            messagebox.showerror("Split Range", str(exc))
            return
        existing_stems = self._ready_stem_paths()
        if existing_stems and self.stem_range[0] <= split_start and self.stem_range[1] >= split_end:
            self.stem_paths = existing_stems
            self.status_var.set("Stem Split already ready.")
            self.append_log("Stem Split skipped: using existing stem files.")
            self._refresh_action_states()
            return
        self.stop_preview(show_status=False)
        if not self.paths.models_have_payload():
            proceed = messagebox.askyesno(
                "Model Download",
                "The first split needs to download model weights.\n\n"
                f"Check your internet connection and free space on the app drive.\nModel folder: {self.paths.models}",
            )
            if not proceed:
                return

        source_wav = self.source_wav
        source_duration = self.duration_seconds
        job_id = uuid.uuid4().hex[:12]
        session_name = f"{self.session_name}/{job_id}"
        crop_path = self.paths.temp / "sessions" / self.session_name / f"split_{job_id}.wav"

        def worker() -> None:
            input_wav = source_wav
            if split_start > 0 or split_end < source_duration:
                self._queue_status("Preparing selection audio")
                extract_audio_range(self.paths, source_wav, crop_path, split_start, split_end - split_start,
                                    self.cancel_event, self._register_process, self._queue_log)
                input_wav = crop_path
            self._queue_status("Preparing model / Separating stems")
            separator = StemSeparator(self.paths)
            stems = separator.separate(
                input_wav,
                session_name,
                log=self._queue_log,
                progress=self._queue_progress,
                cancel_event=self.cancel_event,
                process_callback=self._register_process,
            )
            self.worker_queue.put(("stems_ready", {"paths": {name: str(path) for name, path in stems.items()},
                                                   "range": [split_start, split_end]}))

        self._run_worker("Stem Split", worker)

    def _ready_stem_paths(self) -> dict[str, Path]:
        stems = {
            stem: path
            for stem, path in self.stem_paths.items()
            if stem in STEMS and path.exists()
        }
        if all(stem in stems for stem in STEMS):
            return stems
        return {}

    def render_wav(self) -> None:
        self.render_audio("wav", "WAV", [("WAV", "*.wav"), ("All files", "*.*")])

    def render_mp3(self) -> None:
        self.render_audio("mp3", "MP3", [("MP3", "*.mp3"), ("All files", "*.*")])

    def _unique_output_path(self, output_path: Path) -> Path:
        if not output_path.exists():
            return output_path
        index = 1
        while True:
            candidate = output_path.with_name(f"{output_path.stem}({index}){output_path.suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def export_individual_stems(self) -> None:
        if self.busy:
            return
        ready_stems = self._ready_stem_paths()
        if not ready_stems:
            self.status_var.set("All four stems are required. Click Split Stems first.")
            self._refresh_action_states()
            return
        try:
            output_format = self.stem_export_format_var.get()
            if output_format not in ("WAV", "MP3"):
                raise ValueError("Choose WAV or MP3 in Settings > Stem format.")
            start, end = self._selection_bounds()
            duration = end - start
            fade_in = float(self.fade_in_var.get())
            fade_out = float(self.fade_out_var.get())
            effects = self._build_audio_effects()
            self._validate_stem_range(start, end)
            stems = [MixStem(stem, ready_stems[stem], max(float(self.stem_vars[stem]["volume"].get()) / 100.0, 0.0),
                             self.stem_range[0]) for stem in STEMS]
        except StemRangeError as exc:
            self.status_var.set(str(exc))
            return
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            messagebox.showerror("Export settings", str(exc))
            return

        if not self._confirm_render(individual=True):
            return
        output_dir = self.output_dir
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status_var.set(f"Cannot save to this folder: {exc}")
            return
        self.stop_preview(show_status=False)
        input_label = self.current_input.stem if self.current_input else "audio"
        extension = output_format.lower()
        delete_temp = self.delete_temp_var.get()

        def worker() -> None:
            outputs: list[Path] = []
            # Render the whole batch before exposing final files. Failed or
            # cancelled jobs remove only files created by this export.
            with tempfile.TemporaryDirectory(prefix=".kwak-stems-", dir=output_dir) as staging_dir:
                staged = []
                for index, stem in enumerate(stems, start=1):
                    if self.cancel_event.is_set():
                        raise OperationCancelled("Task cancelled.")
                    self._queue_status(f"Exporting {stem.name} ({index}/4) · {output_format}")
                    path = Path(staging_dir) / f"{input_label}_{start:.2f}-{end:.2f}_{stem.name}.{extension}"
                    render_mix(
                        self.paths, [stem], path,
                        start_seconds=start, duration_seconds=duration,
                        fade_in=fade_in, fade_out=fade_out, log=self._queue_log,
                        cancel_event=self.cancel_event, process_callback=self._register_process,
                        effects=effects, include_silent=True,
                    )
                    staged.append(path)
                try:
                    for path in staged:
                        if self.cancel_event.is_set():
                            raise OperationCancelled("Task cancelled.")
                        destination = self._unique_output_path(output_dir / path.name)
                        # Windows rename fails on a collision, preserving existing files.
                        path.rename(destination)
                        outputs.append(destination)
                except Exception:
                    for path in outputs:
                        path.unlink(missing_ok=True)
                    raise
            if delete_temp:
                self._cleanup_session_files(clear_state=False)
            self.worker_queue.put(("stems_exported", [str(path) for path in outputs]))
            if delete_temp:
                self.worker_queue.put(("temp_cleaned", None))

        self._run_worker(f"Export Stems · {output_format}", worker)

    def render_audio(self, extension: str, label: str, filetypes: list[tuple[str, str]]) -> None:
        if self.busy:
            return
        if not self.source_wav:
            messagebox.showwarning("Audio required", "Load an audio file first.")
            return
        try:
            stems = self._build_mix_stems()
            start, end = self._selection_bounds()
            duration = end - start
            fade_in = float(self.fade_in_var.get())
            fade_out = float(self.fade_out_var.get())
            effects = self._build_audio_effects()
        except StemRangeError as exc:
            self.status_var.set(str(exc))
            return
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            self.pending_preview_mode = None
            messagebox.showerror("Render settings", str(exc))
            return

        if not self._confirm_render():
            return
        input_label = safe_name(self.current_input.stem if self.current_input else "render")
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            input_label = self.current_input.stem if self.current_input else "audio"
            filename = f"{input_label}_{start:.2f}-{end:.2f}.{extension}"
            default_output_path = self._unique_output_path(self.output_dir / filename)
        except OSError as exc:
            self.status_var.set(f"Cannot save to this folder: {exc}")
            return
        output_path_text = str(default_output_path)
        self.stop_preview(show_status=False)
        output_path = Path(output_path_text)
        if output_path.suffix.lower() != f".{extension}":
            output_path = output_path.with_suffix(f".{extension}")
        output_path = self._unique_output_path(output_path)
        self.output_dir = output_path.parent
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings["output_dir"] = str(self.output_dir)
        self.paths.write_settings(self.settings)
        if hasattr(self, "output_dir_label_var"):
            self.output_dir_label_var.set(self._format_output_dir_label())
        delete_temp = self.delete_temp_var.get()

        def worker() -> None:
            self._queue_status(f"Rendering {label}")
            render_mix(
                self.paths,
                stems,
                output_path,
                start_seconds=start,
                duration_seconds=duration,
                fade_in=fade_in,
                fade_out=fade_out,
                log=self._queue_log,
                cancel_event=self.cancel_event,
                process_callback=self._register_process,
                effects=effects,
            )
            if delete_temp:
                self._cleanup_session_files(clear_state=False)
            self.worker_queue.put(("render_ready", str(output_path)))
            if delete_temp:
                self.worker_queue.put(("temp_cleaned", None))

        self._run_worker(f"Render {label}", worker)

    def preview_source_selection(self) -> None:
        if not self.source_wav or self.busy:
            return
        try:
            self.pending_preview_mode = ("source", None)
            self._start_preview([MixStem("source", self.source_wav, 1.0)], "Source")
        except AudioProcessingError as exc:
            messagebox.showerror("Preview settings", str(exc))

    def preview_current_mix(self) -> None:
        if not self.source_wav or self.busy:
            return
        try:
            self.pending_preview_mode = ("mix", None)
            self._start_preview(self._build_mix_stems(), "Current Mix")
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            messagebox.showerror("Preview settings", str(exc))

    def toggle_stem_bypass(self) -> None:
        if self.busy:
            return
        self.stem_bypass_var.set(not bool(self.stem_bypass_var.get()))
        self._update_stem_bypass_button()
        if self.preview_playing:
            self._restart_context_preview_from_cursor()
            return
        state = "on" if self.stem_bypass_var.get() else "off"
        self.status_var.set(f"Stem Bypass {state}.")

    def toggle_playback(self) -> None:
        if self.busy:
            return
        if self.preview_playing:
            self.stop_preview()
            return
        if not self.source_wav:
            self.status_var.set("Load audio first.")
            return
        try:
            self._start_context_preview()
        except StemRangeError as exc:
            self.status_var.set(str(exc))
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            messagebox.showerror("Preview settings", str(exc))

    def _start_context_preview(self) -> None:
        stems, label, mode = self._context_preview_request()
        self.pending_preview_mode = mode
        self._start_preview(stems, label)

    def _context_preview_request(self) -> tuple[list[MixStem], str, tuple[str, str | None]]:
        if not self.source_wav:
            raise AudioProcessingError("No loaded audio file.")
        if not self.stem_paths:
            label = "Source"
            return [MixStem("source", self.source_wav, 1.0)], label, ("source", None)
        return self._build_mix_stems(include_silent=True), "Current Mix", ("mix", None)

    def _restart_context_preview_from_cursor(self) -> None:
        self.stop_preview(show_status=False)
        cursor = float(self.playback_position_var.get())
        self._set_playback_position(cursor)
        self.playback_cursor_manual = True
        try:
            self._start_context_preview()
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            self.status_var.set(f"Preview settings need attention: {exc}")

    def _update_stem_bypass_button(self) -> None:
        if not hasattr(self, "stem_bypass_button"):
            return
        active = bool(self.stem_bypass_var.get())
        self.stem_bypass_button.variant = "primary" if active else "ghost"
        state = "ON" if active else "OFF"
        self.stem_bypass_button.configure(text=f"Stem Bypass {state}")

    def _legacy_space_toggle_playback(self, _event: tk.Event) -> str:
        self.toggle_playback()
        return "break"

    def _legacy_bind_space_shortcut(self, widget: tk.Widget) -> None:
        widget.bind("<KeyPress-space>", self._space_toggle_playback)
        for child in widget.winfo_children():
            self._bind_space_shortcut(child)

    def _start_preview(self, stems: list[MixStem], label: str) -> None:
        start, end = self._playback_bounds()
        duration = end - start
        if duration <= 0:
            raise AudioProcessingError("Select a range longer than 0 seconds.")

        self.last_preview_stems = list(stems)
        self.last_preview_label = label
        self.last_preview_mode, self.last_preview_stem = self._infer_preview_mode(stems)
        fade_in = float(self.fade_in_var.get())
        fade_out = float(self.fade_out_var.get())
        fade_bounds = self._selection_bounds()
        effects = self._build_audio_effects()
        try:
            self.stop_preview(show_status=False)
            self.realtime_processes = start_realtime_mix(
                self.paths,
                stems,
                start_seconds=start,
                duration_seconds=duration,
                fade_in=fade_in,
                fade_out=fade_out,
                effects=effects,
                fade_bounds=fade_bounds,
            )
        except ToolMissingError:
            self._start_rendered_preview(stems, label, start, duration, fade_in, fade_out, effects)
            return

        if effects.peak_normalize:
            self.append_log("Peak normalize is skipped during realtime preview and applied to final renders.")
        self.current_preview_file = None
        self.preview_playing = True
        self.playback_started_at = time.monotonic()
        self.playback_start_seconds = start
        self.playback_duration_seconds = duration
        self.playback_tempo_ratio = effects.tempo_ratio
        self.playback_output_duration_seconds = duration / effects.tempo_ratio
        self._set_playback_position(start)
        self.status_var.set(f"Realtime preview: {label}")
        self._refresh_action_states(transport_only=True)

    def _start_rendered_preview(
        self,
        stems: list[MixStem],
        label: str,
        start: float,
        duration: float,
        fade_in: float,
        fade_out: float,
        effects: AudioEffects,
    ) -> None:
        duration = min(duration, PREVIEW_SECONDS)
        preview_dir = self.paths.temp / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        self._delete_old_previews()
        output_path = preview_dir / f"preview_{safe_name(label)}_{time.strftime('%H%M%S')}.wav"
        fade_bounds = self._selection_bounds()

        def worker() -> None:
            self._queue_status(f"Preparing {label} preview. FFplay is missing, so a temporary WAV will play.")
            render_mix(
                self.paths,
                stems,
                output_path,
                start_seconds=start,
                duration_seconds=duration,
                fade_in=fade_in,
                fade_out=fade_out,
                log=None,
                cancel_event=self.cancel_event,
                process_callback=self._register_process,
                effects=effects,
                fade_bounds=fade_bounds,
                include_silent=True,
            )
            output_duration = read_duration(self.paths, output_path)
            self.worker_queue.put(
                (
                    "preview_ready",
                    {
                        "path": str(output_path),
                        "start": start,
                        "duration": duration,
                        "output_duration": output_duration,
                        "tempo_ratio": effects.tempo_ratio,
                        "label": label,
                    },
                )
            )

        self._run_worker("Prepare Preview", worker)

    def stop_preview(self, show_status: bool = True) -> None:
        if getattr(self, "_loop_after", None):
            self.after_cancel(self._loop_after)
            self._loop_after = None
        self._cancel_live_preview_restart()
        was_playing = self.preview_playing
        if was_playing:
            self._update_playback_position()
            self.playback_cursor_manual = True
        self._stop_realtime_playback()
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except RuntimeError:
            winsound.PlaySound(None, 0)
        self.preview_playing = False
        self.playback_started_at = None
        self.playback_seek_dragging = False
        if getattr(self, "_loop_after", None):
            self.after_cancel(self._loop_after)
            self._loop_after = None
        if show_status:
            self.status_var.set("Playback stopped.")
        self._refresh_action_states(transport_only=True)

    def _cancel_live_preview_restart(self) -> None:
        for name in ("_live_eq_after_id", "_live_mixer_after_id"):
            pending = getattr(self, name, None)
            if pending:
                self.after_cancel(pending)
                setattr(self, name, None)
        if not self.live_restart_after_id:
            return
        try:
            self.after_cancel(self.live_restart_after_id)
        except tk.TclError:
            pass
        self.live_restart_after_id = None

    def _schedule_live_eq_update(self) -> None:
        if not self.preview_playing or self.busy or self.playback_seek_dragging or self.current_preview_file:
            return
        if not getattr(self, "_live_eq_after_id", None):
            # A leading throttle keeps applying while a drag continues.
            self._live_eq_after_id = self.after(16, self._apply_live_eq_update)

    def _apply_live_eq_update(self) -> None:
        self._live_eq_after_id = None
        if not self.preview_playing or self.busy or self.playback_seek_dragging or self.current_preview_file:
            return
        try:
            effects = self._build_audio_effects()
        except (ValueError, tk.TclError, AudioProcessingError):
            return  # Incomplete text entries must not interrupt playing audio.
        update = getattr(self.realtime_processes, "update_eq", None)
        if update and update(effects):
            return
        self._schedule_live_preview_restart()

    def _schedule_live_preview_restart(self) -> None:
        if not self.preview_playing or self.busy or self.playback_seek_dragging:
            return
        if self.current_preview_file:
            return
        self._cancel_live_preview_restart()
        self.live_restart_after_id = self.after(180, self._restart_live_preview)

    def _schedule_live_mixer_update(self) -> None:
        if not self.preview_playing or self.busy or self.playback_seek_dragging or self.current_preview_file:
            return
        if not getattr(self, "_live_mixer_after_id", None):
            self._live_mixer_after_id = self.after(16, self._apply_live_mixer_update)

    def _apply_live_mixer_update(self) -> None:
        self._live_mixer_after_id = None
        if not self.preview_playing or self.busy or self.playback_seek_dragging or self.current_preview_file:
            return
        try:
            stems, _label = self._build_last_preview_request()
        except (ValueError, tk.TclError, AudioProcessingError):
            return
        update = getattr(self.realtime_processes, "update_mixer", None)
        if update and update(stems):
            self.last_preview_stems = list(stems)
            return
        self._schedule_live_preview_restart()

    def _schedule_fade_live_preview_restart(self) -> None:
        if self.fade_control_dragging:
            return
        self._schedule_live_preview_restart()

    def _restart_live_preview(self) -> None:
        self.live_restart_after_id = None
        if not self.preview_playing or self.busy:
            return
        self._restart_preview_silent()

    def _restart_preview_silent(self) -> None:
        try:
            stems, label = self._build_last_preview_request()
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            self.status_var.set(f"Preview settings need attention: {exc}")
            return

        preview_mode = self.last_preview_mode
        preview_stem = self.last_preview_stem
        self.stop_preview(show_status=False)
        cursor = float(self.playback_position_var.get())
        self._set_playback_position(cursor)
        self.playback_cursor_manual = True
        try:
            self.pending_preview_mode = (preview_mode, preview_stem)
            self._start_preview(stems, label)
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            self.status_var.set(f"Preview settings need attention: {exc}")

    def _stop_realtime_playback(self) -> None:
        close = getattr(self.realtime_processes, "close", None)
        if close:
            close()
        for process in self.realtime_processes:
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self.realtime_processes = []
        file_spectrum = getattr(self, "_file_spectrum", None)
        if file_spectrum is not None:
            file_spectrum.close()
            self._file_spectrum = None
        editor = getattr(self, "eq_editor", None)
        if editor is not None and hasattr(editor, "clear_spectrum"):
            editor.clear_spectrum()

    def select_all_audio(self) -> None:
        if self.duration_seconds <= 0:
            return
        self.playback_cursor_manual = False
        self.selection_start_var.set(0.0)
        self.selection_end_var.set(self.duration_seconds)
        self._selection_changed()

    def reset_stem_volume(self, stem: str) -> None:
        self.stem_vars[stem]["volume"].set(100.0)
        self._update_volume_label(stem)

    def _on_stem_volume_changed(self, stem: str) -> None:
        self._update_volume_label(stem)
        self._schedule_live_mixer_update()

    def _legacy_update_volume_label(self, stem: str) -> None:
        value = max(float(self.stem_vars[stem]["volume"].get()), 0.0)
        if value <= 0.0:
            label = "-inf dB"
        else:
            db = 20.0 * math.log10(value / 100.0)
            label = f"{db:+.1f} dB" if abs(db) >= 0.05 else "0.0 dB"
        self.stem_volume_label_vars[stem].set(label)

    def reset_eq(self) -> None:
        if self.busy:
            return
        self._reset_eq_band("low")
        self._reset_eq_band("mid")
        self._reset_eq_band("high")
        self._reset_eq_cut("hp")
        self._reset_eq_cut("lp")
        self.status_var.set("EQ reset.")

    def _reset_eq_band(self, band: str) -> None:
        defaults = {
            "low": (self.eq_low_var, self.eq_low_freq_var, self.eq_low_q_var, self.eq_low_shape_var, EqCurveEditor.LOW_FREQ, 0.8),
            "mid": (self.eq_mid_var, self.eq_mid_freq_var, self.eq_mid_q_var, self.eq_mid_shape_var, EqCurveEditor.MID_FREQ, 1.0),
            "high": (self.eq_high_var, self.eq_high_freq_var, self.eq_high_q_var, self.eq_high_shape_var, EqCurveEditor.HIGH_FREQ, 0.8),
        }
        gain_var, freq_var, q_var, shape_var, freq, q = defaults[band]
        gain_var.set(0.0)
        freq_var.set(freq)
        q_var.set(q)
        shape_var.set("Bell")

    def _reset_eq_cut(self, band: str) -> None:
        if band == "hp":
            self.high_pass_var.set(0.0)
            self.high_pass_q_var.set(0.7)
            return
        self.low_pass_var.set(0.0)
        self.low_pass_q_var.set(0.7)

    def apply_stem_preset(self, label: str, selected: set[str]) -> None:
        if self.busy:
            return
        if not self.stem_paths:
            messagebox.showwarning("Stem required", "Presets unlock after Stem Split.")
            return
        for stem in STEMS:
            self.stem_vars[stem]["solo"].set(False)
            self.stem_vars[stem]["mute"].set(stem not in selected)
        self.status_var.set(f"Preset applied: {label}")
        self.append_log(f"Preset applied: {label}")
        self._refresh_action_states()

    def _infer_preview_mode(self, stems: list[MixStem]) -> tuple[str, str | None]:
        if self.pending_preview_mode:
            preview_mode = self.pending_preview_mode
            self.pending_preview_mode = None
            return preview_mode
        if len(stems) == 1 and stems[0].name == "source":
            return "source", None
        if len(stems) == 1 and stems[0].name in STEMS:
            return "stem", stems[0].name
        return "mix", None

    def _build_last_preview_request(self) -> tuple[list[MixStem], str]:
        if self.last_preview_mode == "source":
            if not self.source_wav:
                raise AudioProcessingError("No loaded audio file.")
            return [MixStem("source", self.source_wav, 1.0)], self.last_preview_label or "Source"

        if self.last_preview_mode == "stem" and self.last_preview_stem:
            stem = self.last_preview_stem
            path = self.stem_paths.get(stem)
            if not path or not path.exists():
                raise AudioProcessingError("Stem file is missing. Run Stem Split again.")
            gain = max(float(self.stem_vars[stem]["volume"].get()) / 100.0, 0.0)
            return [MixStem(stem, path, gain, self.stem_range[0])], stem

        if self.last_preview_mode == "mix":
            return self._build_mix_stems(include_silent=True), self.last_preview_label or "Current Mix"

        if self.last_preview_stems:
            return list(self.last_preview_stems), self.last_preview_label or "Preview"
        raise AudioProcessingError("No preview state to restart.")

    def _build_mix_stems(self, include_silent: bool = False) -> list[MixStem]:
        if not self.stem_paths:
            assert self.source_wav is not None
            return [MixStem("source", self.source_wav, 1.0)]

        soloed = {stem for stem in STEMS if bool(self.stem_vars[stem]["solo"].get())}
        self._validate_stem_range(*self._selection_bounds())
        selected = {stem for stem in STEMS if not bool(self.stem_vars[stem]["mute"].get())
                    and (not soloed or stem in soloed)}

        mix_stems: list[MixStem] = []
        missing_files: list[str] = []
        for stem in STEMS:
            path = self.stem_paths.get(stem)
            if not path or (not include_silent and stem not in selected):
                continue
            if not path.exists():
                missing_files.append(stem)
                continue
            gain = max(float(self.stem_vars[stem]["volume"].get()) / 100.0, 0.0)
            if stem not in selected:
                gain = 0.0
            mix_stems.append(MixStem(stem, path, gain, self.stem_range[0]))
        if missing_files:
            self._clear_stem_state("Waiting")
            raise AudioProcessingError(
                "Stem temp files are missing. The split may have been cancelled or temp may have been cleaned. "
                "Run Stem Split again: "
                + ", ".join(missing_files)
            )
        return mix_stems

    def _build_audio_effects(self) -> AudioEffects:
        self._edit_snapshot()  # Reject incomplete/non-finite entries before starting audio work.
        low_db = max(min(float(self.eq_low_var.get()), EQ_GAIN_LIMIT), -EQ_GAIN_LIMIT)
        mid_db = max(min(float(self.eq_mid_var.get()), EQ_GAIN_LIMIT), -EQ_GAIN_LIMIT)
        high_db = max(min(float(self.eq_high_var.get()), EQ_GAIN_LIMIT), -EQ_GAIN_LIMIT)
        low_freq = max(min(float(self.eq_low_freq_var.get()), 20000.0), 20.0)
        mid_freq = max(min(float(self.eq_mid_freq_var.get()), 20000.0), 20.0)
        high_freq = max(min(float(self.eq_high_freq_var.get()), 20000.0), 20.0)
        low_q = max(min(float(self.eq_low_q_var.get()), 10.0), 0.1)
        mid_q = max(min(float(self.eq_mid_q_var.get()), 10.0), 0.1)
        high_q = max(min(float(self.eq_high_q_var.get()), 10.0), 0.1)
        high_pass_hz = max(float(self.high_pass_var.get()), 0.0)
        low_pass_hz = max(float(self.low_pass_var.get()), 0.0)
        high_pass_q = max(min(float(self.high_pass_q_var.get()), 10.0), 0.1)
        low_pass_q = max(min(float(self.low_pass_q_var.get()), 10.0), 0.1)
        if self.eq_low_shape_var.get() == "High Pass":
            low_db, high_pass_hz = 0.0, low_freq
        if self.eq_high_shape_var.get() == "Low Pass":
            high_db, low_pass_hz = 0.0, high_freq
        if high_pass_hz > 0 and low_pass_hz > 0 and high_pass_hz >= low_pass_hz:
            raise AudioProcessingError("High-pass Hz must be lower than Low-pass Hz.")
        return AudioEffects(
            low_db=low_db,
            mid_db=mid_db,
            high_db=high_db,
            low_freq=low_freq,
            mid_freq=mid_freq,
            high_freq=high_freq,
            low_q=low_q,
            mid_q=mid_q,
            high_q=high_q,
            low_shape=self._eq_shape(self.eq_low_shape_var),
            mid_shape=self._eq_shape(self.eq_mid_shape_var),
            high_shape=self._eq_shape(self.eq_high_shape_var),
            high_pass_hz=high_pass_hz,
            low_pass_hz=low_pass_hz,
            high_pass_q=high_pass_q,
            low_pass_q=low_pass_q,
            high_pass_slope=int(self.high_pass_slope_var.get()),
            low_pass_slope=int(self.low_pass_slope_var.get()),
            pitch_semitones=max(min(float(self.pitch_semitones_var.get()), 12.0), -12.0),
            tempo_ratio=max(min(float(self.tempo_percent_var.get()) / 100.0, 2.0), 0.5),
            peak_normalize=bool(self.peak_normalize_var.get()),
            limiter_enabled=bool(self.limiter_enabled_var.get()),
            limiter_ceiling=max(min(float(self.limiter_ceiling_var.get()), 1.0), 0.05),
            sample_rate=int(self.sample_rate_var.get()),
            bit_depth=int(self.bit_depth_var.get()),
            mp3_bitrate=int(self.mp3_bitrate_var.get()),
        )

    def _eq_shape(self, variable: tk.StringVar) -> str:
        value = str(variable.get())
        return value if value in EQ_SHAPES else "Bell"

    def _selection_bounds(self) -> tuple[float, float]:
        start = max(min(float(self.selection_start_var.get()), float(self.selection_end_var.get())), 0.0)
        end = min(max(float(self.selection_start_var.get()), float(self.selection_end_var.get())), self.duration_seconds)
        if end <= start:
            raise AudioProcessingError("Select a range longer than 0 seconds.")
        return start, end

    def _playback_bounds(self) -> tuple[float, float]:
        selection_start, selection_end = self._selection_bounds()
        if not self.playback_cursor_manual:
            return selection_start, selection_end

        cursor = max(0.0, min(float(self.playback_position_var.get()), self.duration_seconds))
        if cursor >= self.duration_seconds:
            cursor = selection_start
            self._set_playback_position(cursor)
        if not selection_start <= cursor < selection_end:
            cursor = selection_start
            self._set_playback_position(cursor)
        return cursor, selection_end

    def open_output_folder(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_dir)

    def _format_output_dir_label(self) -> str:
        path_text = str(self.output_dir)
        if len(path_text) <= 48:
            return path_text
        return "..." + path_text[-45:]

    def choose_output_folder(self) -> None:
        if self.busy:
            return
        initial_dir = self.output_dir if self.output_dir.exists() else self.paths.output
        selected = filedialog.askdirectory(
            title="Choose render folder",
            initialdir=str(initial_dir),
        )
        if not selected:
            return
        self.output_dir = Path(selected)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings["output_dir"] = str(self.output_dir)
        self.paths.write_settings(self.settings)
        if hasattr(self, "output_dir_label_var"):
            self.output_dir_label_var.set(self._format_output_dir_label())
        self.status_var.set(f"Save folder: {self.output_dir}")

    def _legacy_open_render_settings(self) -> None:
        if self.render_settings_window and self.render_settings_window.winfo_exists():
            self.render_settings_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.render_settings_window = window
        window.title("Export and Project Settings")
        window.configure(background="#10141c")
        window.resizable(True, True)
        window.geometry(f"700x{min(650, self.winfo_screenheight() - 120)}")
        window.minsize(480, 360)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_render_settings)

        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        scroll = ScrollableFrame(window, minimum_width=580)
        scroll.grid(row=0, column=0, sticky="nsew")
        frame = scroll.content
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Save To").grid(row=0, column=0, sticky="w", pady=(0, 10))
        output_dir_label = ttk.Label(
            frame,
            textvariable=self.output_dir_label_var,
            style="Muted.TLabel",
            width=38,
            anchor="w",
        )
        output_dir_label.grid(row=0, column=1, sticky="ew", padx=(10, 8), pady=(0, 10))
        output_dir_button = PillButton(
            frame,
            "Change",
            self.choose_output_folder,
            variant="ghost",
            width=84,
            height=30,
            bg="#101722",
        )
        output_dir_button.grid(row=0, column=2, sticky="e", pady=(0, 10))

        normalize_check = ttk.Checkbutton(
            frame,
            text="Normalize",
            variable=self.peak_normalize_var,
            style="TCheckbutton",
        )
        normalize_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))

        limiter_check = ttk.Checkbutton(
            frame,
            text="Limiter",
            variable=self.limiter_enabled_var,
            style="TCheckbutton",
        )
        limiter_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 6))

        delete_temp_check = ttk.Checkbutton(
            frame,
            text="Delete working audio after export (save your project first)",
            variable=self.delete_temp_var,
            style="TCheckbutton",
        )
        delete_temp_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._build_extra_render_settings(frame)

        close_button = PillButton(
            frame,
            "Close",
            self._close_render_settings,
            variant="ghost",
            width=84,
            height=30,
            bg="#101722",
        )
        close_button.grid(row=11, column=0, columnspan=3, sticky="e", pady=12)

    def _legacy_close_render_settings(self) -> None:
        if self.render_settings_window and self.render_settings_window.winfo_exists():
            self.render_settings_window.destroy()
        self.render_settings_window = None

    def _load_output_dir(self) -> Path:
        configured = str(self.settings.get("output_dir") or "").strip()
        if configured:
            return Path(configured)
        return self.paths.output

    def cleanup_current_temp(self) -> None:
        if self.busy:
            return
        if not self.session_name:
            messagebox.showinfo("New Project", "There is no current project.")
            return
        if not self._guard_project(self.cleanup_current_temp):
            return
        self.stop_preview(show_status=False)
        self._cleanup_session_files(clear_state=True)
        if not self.keep_adjustments_var.get():
            self._reset_edits()
        self.project_file = None
        self._saved_edits = None
        self.project_dirty = False
        from backend.project_store import EditHistory
        self.history = EditHistory(self._edit_snapshot())
        self._update_project_label()
        self._update_workspace_summary()
        self.status_var.set("New project ready" + (" · Adjustments kept" if self.keep_adjustments_var.get() else " · Adjustments reset"))
        self.append_log("New project started.")
        self._refresh_action_states()

    def cancel_current_operation(self) -> None:
        if not self.busy:
            return
        if self.cancel_event:
            self.cancel_event.set()
        process = self.current_process
        if process and process.poll() is None:
            self._terminate_owned_process(process)
        self._set_busy_status("Cancel requested. Cleaning up")
        self.append_log("User requested cancellation.")
        self.cancel_button.configure(state="disabled")

    def _cleanup_session_files(self, clear_state: bool) -> None:
        targets = [
            self.paths.temp / "sessions" / self.session_name,
            self.paths.temp / "stems" / self.session_name,
        ]
        for target in targets:
            self._safe_remove_tree(target)
        self._delete_old_previews()
        if clear_state:
            self.current_input = None
            self.source_wav = None
            self.session_name = ""
            self.file_label_var.set("No file")
            self.duration_seconds = 0.0
            self.peaks = []
            self._clear_stem_state("Waiting")
            self._reset_playback_tracking()
            self.selection_start_var.set(0.0)
            self.selection_end_var.set(0.0)
            self._configure_selection_limits(1.0)
            self.draw_waveform()

    def _delete_old_previews(self) -> None:
        preview_dir = self.paths.temp / "previews"
        if not preview_dir.exists():
            return
        resolved_preview = preview_dir.resolve()
        resolved_temp = self.paths.temp.resolve()
        if resolved_preview == resolved_temp or resolved_temp not in resolved_preview.parents:
            raise AudioProcessingError("Unsafe preview cleanup path detected.")
        for preview in preview_dir.glob("preview_*.wav"):
            try:
                preview.unlink()
            except OSError:
                pass

    def _safe_remove_tree(self, target: Path) -> None:
        if not target.exists():
            return
        resolved_target = target.resolve()
        resolved_temp = self.paths.temp.resolve()
        if resolved_target == resolved_temp or resolved_temp not in resolved_target.parents:
            raise AudioProcessingError("Unsafe temp cleanup path detected.")
        shutil.rmtree(resolved_target)

    def _run_worker(self, title: str, worker: Callable[[], None]) -> None:
        self.cancel_event = threading.Event()
        self.current_process = None
        self._set_busy(True, title)

        def wrapped() -> None:
            try:
                logging.info("START %s", title)
                worker()
                logging.info("DONE %s", title)
            except OperationCancelled as exc:
                logging.info("CANCELLED %s", title)
                self.worker_queue.put(("cancelled", str(exc)))
            except Exception as exc:
                logging.exception("Worker failed: %s", title)
                self.worker_queue.put(("error", f"{exc}"))
                self.worker_queue.put(("log", traceback.format_exc()))
            finally:
                self.worker_queue.put(("done", title))

        threading.Thread(target=wrapped, daemon=True).start()

    def _register_process(self, process: subprocess.Popen | None) -> None:
        # Publish first: Cancel/Close either sees this child, or its signal is
        # already set when we check below. Neither ordering leaves an orphan.
        self.current_process = process
        if process is not None and (self.closing or (self.cancel_event and self.cancel_event.is_set())):
            self._terminate_owned_process(process)

    def _terminate_owned_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                # Detached cleanup also terminates Demucs multiprocessing children.
                # Do not wait for it on the UI thread or touch unrelated processes.
                subprocess.Popen(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process.terminate()
        except OSError:
            logging.exception("Could not stop owned audio process %s", process.pid)

    def _set_busy(self, busy: bool, title: str = "") -> None:
        self.busy = busy
        self.busy_title = title if busy else ""
        if busy:
            self.busy_status_base = f"{title} in progress"
            self.busy_started_at = time.monotonic()
            self.busy_progress_percent = None
            self.busy_animation_step = 0
            self.progressbar.configure(mode="indeterminate")
            self.progressbar.start(12)
            self._start_busy_animation()
        else:
            self._stop_loading_messages()
            self._stop_busy_animation()
            self.progressbar.stop()
            self.progressbar.configure(mode="determinate")
            self.progress_var.set(0.0)
            self.busy_status_base = ""
            self.busy_started_at = None
            self.busy_progress_percent = None
            self.cancel_event = None
            self.current_process = None
        self._refresh_action_states()

    def _set_busy_status(self, message: str) -> None:
        if not self.busy:
            self.status_var.set(message)
            return
        self.busy_status_base = message
        self._apply_busy_status()

    def _start_busy_animation(self) -> None:
        self._stop_busy_animation()
        self._animate_busy_status()

    def _stop_busy_animation(self) -> None:
        if not self.busy_animation_after_id:
            return
        try:
            self.after_cancel(self.busy_animation_after_id)
        except tk.TclError:
            pass
        self.busy_animation_after_id = None

    def _start_loading_messages(self) -> None:
        self._stop_loading_messages()
        self._pick_loading_message()
        self._apply_busy_status()
        self._schedule_loading_message()

    def _stop_loading_messages(self) -> None:
        if self.loading_message_after_id:
            try:
                self.after_cancel(self.loading_message_after_id)
            except tk.TclError:
                pass
            self.loading_message_after_id = None
        self.loading_message_text = ""

    def _schedule_loading_message(self) -> None:
        if not self.busy or self.busy_title != "Stem Split":
            self.loading_message_after_id = None
            return
        delay_ms = random.randint(LOADING_MESSAGE_MIN_MS, LOADING_MESSAGE_MAX_MS)
        self.loading_message_after_id = self.after(delay_ms, self._advance_loading_message)

    def _advance_loading_message(self) -> None:
        self.loading_message_after_id = None
        if not self.busy or self.busy_title != "Stem Split":
            return
        self._pick_loading_message()
        self._apply_busy_status()
        self._schedule_loading_message()

    def _pick_loading_message(self) -> None:
        messages = [message for message in LOADING_MESSAGES if message != self.loading_message_text]
        self.loading_message_text = random.choice(messages or list(LOADING_MESSAGES))

    def _animate_busy_status(self) -> None:
        if not self.busy:
            self.busy_animation_after_id = None
            return
        self._apply_busy_status()
        self.busy_animation_step += 1
        self.busy_animation_after_id = self.after(450, self._animate_busy_status)

    def _apply_busy_status(self) -> None:
        dots = "." * ((self.busy_animation_step % 3) + 1)
        spinner = ("|", "/", "-", "\\")[self.busy_animation_step % 4]
        elapsed = self._busy_elapsed_label()
        percent = ""
        if self.busy_progress_percent is not None:
            percent = f" {self.busy_progress_percent:.0f}%"
        base = self.busy_status_base or f"{self.busy_title} in progress"
        self.status_var.set(f"{base}{dots} {spinner} {elapsed}{percent}")

    def _busy_elapsed_label(self) -> str:
        if self.busy_started_at is None:
            return "00:00"
        elapsed = max(int(time.monotonic() - self.busy_started_at), 0)
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _legacy_refresh_action_states(self) -> None:
        if not hasattr(self, "load_button"):
            return
        source_ready = self.source_wav is not None
        stems_ready = bool(self.stem_paths)
        idle = not self.busy

        self._set_state(self.load_button, idle)
        self._set_state(self.separate_button, idle and source_ready)
        self._set_state(self.play_button, (idle and source_ready) or self.preview_playing)
        self._set_state(self.stem_bypass_button, idle and source_ready)
        self._update_stem_bypass_button()
        self._set_state(self.render_button, idle and source_ready)
        self._set_state(self.render_mp3_button, idle and source_ready)
        self._set_state(self.export_stems_button, idle and stems_ready)
        self._set_state(self.settings_button, idle)
        self._set_state(self.cleanup_button, idle and bool(self.session_name))
        self._set_state(self.cancel_button, self.busy)
        if self.busy:
            self.cancel_button.grid()
        else:
            self.cancel_button.grid_remove()
        self._set_state(self.select_all_button, idle and source_ready)
        self._set_state(self.range_scale, idle and source_ready)
        self._set_state(self.playback_scale, idle and source_ready)
        self._set_state(self.start_spinbox, idle and source_ready)
        self._set_state(self.end_spinbox, idle and source_ready)
        for widget in self.effect_widgets:
            self._set_state(widget, idle and source_ready)
        if hasattr(self, "eq_editor"):
            self.eq_editor.set_enabled(idle and source_ready)
        for widget in self.preset_widgets:
            self._set_state(widget, idle and stems_ready)
        self.play_button.configure(text="Stop (Space)" if self.preview_playing else "Play (Space)")

        for stem in STEMS:
            enabled = idle and stems_ready and stem in self.stem_paths
            for widget in self.stem_widgets[stem]:
                self._set_state(widget, enabled)

        self._update_step_text()
        self._update_workspace_summary()

    def _set_state(self, widget: tk.Widget, enabled: bool) -> None:
        if hasattr(widget, "set_enabled"):
            widget.set_enabled(enabled)  # type: ignore[attr-defined]
        elif widget.winfo_class() == "TCombobox":
            widget.configure(state="readonly" if enabled else "disabled")
        else:
            widget.configure(state="normal" if enabled else "disabled")

    def _reset_playback_tracking(self) -> None:
        self._cancel_live_preview_restart()
        self._stop_realtime_playback()
        self.preview_playing = False
        self.current_preview_file = None
        self.playback_started_at = None
        self.playback_start_seconds = 0.0
        self.playback_duration_seconds = 0.0
        self.playback_tempo_ratio = 1.0
        self.playback_output_duration_seconds = 0.0
        self.playback_cursor_manual = False
        self.playback_seek_dragging = False
        self.last_preview_stems = None
        self.last_preview_label = ""
        self.last_preview_mode = ""
        self.last_preview_stem = None
        self._set_playback_position(0.0)

    def _clear_stem_state(self, _status: str = "Waiting") -> None:
        self.stem_paths = {}
        self.stem_range = (0.0, self.duration_seconds)
        self.last_preview_stems = None
        self.last_preview_label = ""
        self._refresh_action_states()

    def _update_playback_position(self) -> None:
        if self.playback_started_at is None:
            return
        elapsed = max(time.monotonic() - self.playback_started_at, 0.0)
        audio_clock = getattr(self.realtime_processes, "position_seconds", None)
        if audio_clock is not None:
            elapsed = audio_clock()
        take_eq_error = getattr(self.realtime_processes, "take_eq_error", None)
        if take_eq_error:
            error = take_eq_error()
            if error:
                self.append_log(f"Live EQ/mixer update failed: {error}")
                self.status_var.set("Live audio could not update. Reapplying the current settings.")
                self._schedule_live_preview_restart()
        read_position = getattr(self.realtime_processes, "playback_position", None)
        state = read_position() if read_position else None
        take_seek_error = getattr(self.realtime_processes, "take_seek_error", None)
        seek_error = take_seek_error() if take_seek_error else ""
        if seek_error:
            self.append_log(f"Live seek failed: {seek_error}")
            self.status_var.set("Could not move to that position. Playback continued.")
        if state is not None:
            self.playback_start_seconds = state.start_seconds
            self.playback_duration_seconds = state.duration_seconds
            self.playback_tempo_ratio = state.tempo_ratio
            self.playback_output_duration_seconds = state.duration_seconds / state.tempo_ratio
        play_end = self.playback_start_seconds + self.playback_duration_seconds
        # The waveform uses source time, while the player uses output time.
        # Keep the speed captured at playback start until a restart applies edits.
        position = (state.position_seconds if state is not None else
                    min(self.playback_start_seconds + elapsed * self.playback_tempo_ratio, play_end))
        if not self.playback_seek_dragging and not (state and state.seeking):
            self._set_playback_position(position)

        failed = False
        if self.realtime_processes:
            # start_realtime_mix returns [FFplay, FFmpeg]. FFmpeg can finish
            # while FFplay is still draining buffered audio; only the player
            # tells us the output has ended, including tempo-filter tail audio.
            finished = self.realtime_processes[0].poll() is not None
            if finished:
                failed = any(process.poll() not in (None, 0) for process in self.realtime_processes)
        else:
            # winsound does not expose completion, so use the rendered WAV's
            # measured duration, not the selected source range's duration.
            finished = elapsed >= self.playback_output_duration_seconds

        if finished:
            self._cancel_live_preview_restart()
            self._stop_realtime_playback()
            self.preview_playing = False
            self.playback_started_at = None
            if failed:
                self.status_var.set("Preview failed. Check the audio settings and output device.")
                self.append_log("Realtime preview failed: FFplay or FFmpeg exited with an error.")
            else:
                self._set_playback_position(play_end)
                self.status_var.set("Playback finished.")
                loop_var = getattr(self, "loop_var", None)
                if loop_var is not None and loop_var.get() and not self.closing:
                    self._loop_after = self.after(80, self._loop_preview)
            self._refresh_action_states()

    def _set_playback_position(self, position: float, redraw: bool = True) -> None:
        position = max(0.0, min(float(position), max(self.duration_seconds, 0.0)))
        self.updating_playback_position = True
        try:
            self.playback_position_var.set(position)
        finally:
            self.updating_playback_position = False
        self._update_playback_label(position)
        if redraw:
            self._draw_playback_cursor()

    def _playback_position_changed(self, value: str) -> None:
        if self.updating_playback_position:
            return
        try:
            position = float(value)
        except ValueError:
            return
        self.playback_cursor_manual = True
        self._update_playback_label(position)
        self._draw_playback_cursor()

    def _playback_seek_begin(self, _event: tk.Event | None = None) -> None:
        self.playback_seek_dragging = True

    def _playback_seek_end(self, _event: tk.Event | None = None) -> None:
        self.playback_seek_dragging = False
        self._set_playback_position(float(self.playback_position_var.get()))
        self.playback_cursor_manual = True
        if self.preview_playing:
            self._restart_preview_from_cursor()

    def _restart_preview_from_cursor(self, show_errors: bool = True) -> None:
        try:
            stems, label = self._build_last_preview_request()
            seek = getattr(self.realtime_processes, "seek", None)
            if self.preview_playing and seek:
                start, end = self._playback_bounds()
                if seek(start, end - start, stems=tuple(stems), effects=self._build_audio_effects(),
                        fade_in=float(self.fade_in_var.get()), fade_out=float(self.fade_out_var.get()),
                        fade_bounds=self._selection_bounds()):
                    self._cancel_live_preview_restart()
                    self.last_preview_stems = list(stems)
                    return
        except StemRangeError as exc:
            self.stop_preview(show_status=False)
            self.status_var.set(str(exc))
            return
        except (ValueError, tk.TclError, AudioProcessingError) as exc:
            if show_errors:
                messagebox.showerror("Preview settings", str(exc))
            else:
                self.status_var.set(f"Preview settings need attention: {exc}")
            return
        cursor = float(self.playback_position_var.get())
        preview_mode = self.last_preview_mode
        preview_stem = self.last_preview_stem
        self.stop_preview(show_status=False)
        self._set_playback_position(cursor)
        self.playback_cursor_manual = True
        try:
            self.pending_preview_mode = (preview_mode, preview_stem)
            self._start_preview(stems, label)
        except StemRangeError as exc:
            self.status_var.set(str(exc))
        except AudioProcessingError as exc:
            messagebox.showerror("Preview settings", str(exc))

    def _update_playback_label(self, position: float) -> None:
        if self.duration_seconds <= 0:
            self.playback_label_var.set("--")
            return
        self.playback_label_var.set(
            f"{self._format_duration(position)} / {self._format_duration(self.duration_seconds)}"
        )

    def _format_duration(self, seconds: float) -> str:
        total_seconds = max(int(round(seconds)), 0)
        minutes, remaining_seconds = divmod(total_seconds, 60)
        return f"{minutes}:{remaining_seconds:02d}"

    def _update_step_text(self) -> None:
        if self.busy:
            self.step_var.set(f"In progress: {self.busy_title}. If it takes too long, click Cancel.")
        else:
            self.step_var.set("")

    def _queue_log(self, message: str) -> None:
        if "Downloading:" in message:
            self.worker_queue.put(("status", "Downloading stem model"))
        elif "Separating track" in message:
            self.worker_queue.put(("status", "Separating stems"))
        self.worker_queue.put(("log", message))

    def _queue_status(self, message: str) -> None:
        self.worker_queue.put(("status", message))

    def _queue_progress(self, value: float) -> None:
        self.worker_queue.put(("progress", float(value)))

    def _process_worker_queue(self) -> None:
        self.worker_queue_after_id = None
        if self.closing:
            return
        try:
            while not self.closing:
                try:
                    kind, payload = self.worker_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_worker_message(kind, payload)
                except Exception:
                    # A bad UI result must never strand the queued "done" event.
                    logging.exception("Could not apply worker result: %s", kind)
                    self._pending_project = None
                    if self.cancel_event:
                        self.cancel_event.set()
                    self.status_var.set("Error updating the screen. Details are in the log.")
        finally:
            if not self.closing:
                self.worker_queue_after_id = self.after(100, self._process_worker_queue)

    def _handle_worker_message(self, kind, payload) -> None:
        if kind == "log":
            self.append_log(str(payload))
        elif kind == "status":
            self._set_busy_status(str(payload))
        elif kind == "progress":
            self.progressbar.stop()
            self.progressbar.configure(mode="determinate")
            self.busy_progress_percent = float(payload)
            self.progress_var.set(self.busy_progress_percent)
            self._apply_busy_status()
        elif kind == "source_ready":
            self._handle_source_ready(payload)  # type: ignore[arg-type]
        elif kind == "stems_ready":
            self._handle_stems_ready(payload)  # type: ignore[arg-type]
        elif kind == "render_ready":
            self._handle_render_ready(Path(str(payload)))
        elif kind == "stems_exported":
            self._handle_stems_exported(payload)  # type: ignore[arg-type]
        elif kind == "project_saved":
            self._handle_project_saved(payload)
        elif kind == "preview_ready":
            self._handle_preview_ready(payload)  # type: ignore[arg-type]
        elif kind == "temp_cleaned":
            self._clear_after_temp_delete()
            self.append_log("Deleted current temp after render.")
        elif kind == "cancelled":
            self._pending_project = None
            self.status_var.set("Task cancelled.")
            self.append_log(str(payload))
        elif kind == "error":
            self._pending_project = None
            self.status_var.set("Error. Check the detailed log.")
            self.set_log_visible(True)
            messagebox.showerror("Error", str(payload))
        elif kind == "done":
            self._set_busy(False)

    def _handle_source_ready(self, payload: dict[str, object]) -> None:
        self.current_input = Path(str(payload["input"]))
        self.source_wav = Path(str(payload["source_wav"]))
        self.session_name = str(payload["session"])
        self.file_label_var.set(self.current_input.name)
        self.duration_seconds = float(payload["duration"])
        self.peaks = list(payload["peaks"])  # type: ignore[arg-type]
        self.source_channels = int(payload.get("channels", 2))
        self._clear_stem_state("Waiting")
        self._reset_playback_tracking()
        self.selection_start_var.set(0.0)
        self.selection_end_var.set(round(self.duration_seconds, 2))
        self._configure_selection_limits(max(self.duration_seconds, 1.0))
        self._update_selection_label()
        self._set_playback_position(0.0)
        self.draw_waveform()
        self.status_var.set(f"Loaded: {self.current_input.name}")
        self.append_log(f"Loaded: {self.current_input}")
        self._source_workspace_ready()
        self._refresh_action_states()

    def _handle_stems_ready(self, payload: dict) -> None:
        self.stem_paths = {name: Path(path) for name, path in payload["paths"].items() if Path(path).exists()}
        self.stem_range = tuple(payload["range"])
        missing = [stem for stem in STEMS if stem not in self.stem_paths]
        if missing:
            self._clear_stem_state("Waiting")
            messagebox.showerror("Stem Split", "Missing stem files: " + ", ".join(missing))
            return
        self.status_var.set("Stem Split complete.")
        self.append_log("Stem Split complete.")
        self._selection_changed()
        self._saved_edits = None
        self._commit_edit()
        self._refresh_action_states()

    def _handle_render_ready(self, output_path: Path) -> None:
        self.status_var.set(f"Rendered: {output_path.name}")
        self.append_log(f"Rendered: {output_path}")
        self._show_results([output_path])

    def _handle_stems_exported(self, outputs: list[str]) -> None:
        self.status_var.set(f"Stem export complete: {len(outputs)} files")
        for path in outputs:
            self.append_log(f"Exported stem: {path}")
        self._show_results(outputs)

    def _handle_preview_ready(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload["path"]))
        start_seconds = float(payload["start"])
        duration_seconds = float(payload["duration"])
        self.stop_preview(show_status=False)
        try:
            winsound.PlaySound(str(preview_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except RuntimeError as exc:
            messagebox.showerror("Preview failed", f"Cannot play audio.\n{exc}")
            return
        self.current_preview_file = preview_path
        self.preview_playing = True
        self.playback_started_at = time.monotonic()
        self.playback_start_seconds = start_seconds
        self.playback_duration_seconds = duration_seconds
        self.playback_tempo_ratio = float(payload["tempo_ratio"])
        self.playback_output_duration_seconds = float(payload["output_duration"])
        try:
            self._file_spectrum = analyze_rendered_preview(self.paths, preview_path)
        except (OSError, AudioProcessingError) as exc:
            self.append_log(f"Spectrum unavailable for rendered preview: {exc}")
        self._set_playback_position(start_seconds)
        self.status_var.set(f"Preview playing: {preview_path.name}")
        self._refresh_action_states()

    def _clear_after_temp_delete(self) -> None:
        self.stop_preview(show_status=False)
        self.source_wav = None
        self.current_input = None
        self.session_name = ""
        self.file_label_var.set("No file")
        self.peaks = []
        self.duration_seconds = 0.0
        self._reset_playback_tracking()
        self._clear_stem_state("Waiting")
        self.selection_start_var.set(0.0)
        self.selection_end_var.set(0.0)
        self._configure_selection_limits(1.0)
        self.draw_waveform()
        self._refresh_action_states()

    def append_log(self, message: str) -> None:
        logging.info(message)
        self.log_messages.append(message.rstrip())
        if self.log_visible:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message.rstrip() + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

    def toggle_log_visibility(self) -> None:
        self.set_log_visible(not self.log_visible)

    def _legacy_set_log_visible(self, visible: bool) -> None:
        self.log_visible = visible
        self.log_toggle_button.configure(text="Hide Log" if visible else "Show Log")
        if visible:
            self.log_text.grid()
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            for message in self.log_messages[-500:]:
                self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        else:
            self.log_text.grid_remove()

    def _legacy_configure_selection_limits(self, limit: float) -> None:
        for widget in (self.range_scale, self.start_spinbox, self.end_spinbox):
            widget.configure(to=limit)
        self.playback_scale.configure(to=limit)

    def _selection_changed(self) -> None:
        try:
            if not all(math.isfinite(float(variable.get())) for variable in (self.selection_start_var, self.selection_end_var)):
                raise ValueError("Non-finite selection")
        except (tk.TclError, ValueError):
            self.status_var.set("Enter numeric start and end times.")
            return
        if self.duration_seconds > 0:
            start = min(self.duration_seconds, round(max(0.0, float(self.selection_start_var.get())), 2))
            end = min(self.duration_seconds, round(max(0.0, float(self.selection_end_var.get())), 2))
            start, end = self._clamp_stem_selection(start, end)
            self._configure_selection_limits(self.duration_seconds)
            if start != self.selection_start_var.get():
                self.selection_start_var.set(start)
            if end != self.selection_end_var.get():
                self.selection_end_var.set(end)
            if not self.preview_playing and not self.playback_cursor_manual:
                self._set_playback_position(min(start, end), redraw=False)
        self._update_selection_label()
        self.draw_waveform()

    def _legacy_update_selection_label(self) -> None:
        start = min(self.selection_start_var.get(), self.selection_end_var.get())
        end = max(self.selection_start_var.get(), self.selection_end_var.get())
        length = max(end - start, 0.0)
        self.selection_label.configure(
            text=f"{self._format_duration(start)} - {self._format_duration(end)}  ({self._format_duration(length)})"
        )

    def _schedule_waveform_resize_draw(self, _event: tk.Event | None = None) -> None:
        if self.waveform_resize_after_id:
            try:
                self.after_cancel(self.waveform_resize_after_id)
            except tk.TclError:
                pass
        self.waveform_resize_after_id = self.after(90, self._draw_waveform_after_resize)

    def _draw_waveform_after_resize(self) -> None:
        self.waveform_resize_after_id = None
        if not self.closing:
            self.draw_waveform()

    def _schedule_fade_waveform_draw(self, force_full: bool = False) -> None:
        if not self.closing and not self.waveform_fade_after_id:
            self.waveform_fade_after_id = self.after_idle(self._draw_waveform_after_fade_change)

    def _draw_waveform_after_fade_change(self) -> None:
        self.waveform_fade_after_id = None
        if not self.closing:
            self.draw_waveform()

    def _legacy_draw_waveform(self) -> None:
        canvas = self.wave_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        view_start, view_end = self._wave_view_bounds()
        view_span = view_end - view_start
        if self.duration_seconds > 0:
            self.wave_scroll.set(view_start / self.duration_seconds, min(view_end / self.duration_seconds, 1.0))
        mid = height // 2
        canvas.create_rectangle(0, 0, width, height, fill="#0b1018", outline="")
        for y in (height // 4, mid, height * 3 // 4):
            canvas.create_line(0, y, width, y, fill="#1d2735")
        for index in range(0, max(width, 1), max(width // 12, 80)):
            canvas.create_line(index, 0, index, height, fill="#151e2b")
        canvas.create_line(0, mid, width, mid, fill="#2f3945")

        if not self.peaks:
            margin = 24
            canvas.create_rectangle(
                margin,
                margin,
                width - margin,
                height - margin,
                outline="#314057",
                dash=(5, 5),
            )
            canvas.create_text(
                width // 2,
                mid - 12,
                fill="#d7dee8",
                text="Drop an audio file here",
                font=("Segoe UI", 14, "bold"),
            )
            canvas.create_text(
                width // 2,
                mid + 16,
                fill="#8c99a8",
                text="or Open Audio · WAV, MP3, FLAC, M4A supported",
                font=("Segoe UI", 9),
            )
            return

        selection_start = 0.0
        selection_end = 0.0
        if self.duration_seconds > 0:
            selection_start, selection_end = self._selection_bounds_no_error()
        peak_count = len(self.peaks)
        for x in range(0, width, 2):
            seconds = view_start + view_span * x / width
            index = min(int(seconds / self.duration_seconds * peak_count), peak_count - 1)
            raw_peak = self.peaks[index]
            gain = self._fade_display_gain(seconds, selection_start, selection_end)
            peak = raw_peak * gain
            texture = (0.35 + 0.65 * raw_peak) * gain
            spectral_height = max(int(texture * height * 0.44), 1)
            color = "#8a521f" if peak > 0.45 else "#55351e"
            canvas.create_line(x, mid - spectral_height, x, mid + spectral_height, fill=color)

        for x in range(width):
            seconds = view_start + view_span * x / width
            index = min(int(seconds / self.duration_seconds * peak_count), peak_count - 1)
            peak = self.peaks[index] * self._fade_display_gain(seconds, selection_start, selection_end)
            y = max(int(peak * (height * 0.44)), 1)
            canvas.create_line(x, mid - y, x, mid + y, fill="#54a3ff")

        if self.duration_seconds > 0:
            tick_count = max(2, min(12, width // 100))
            for tick in range(tick_count + 1):
                seconds = view_start + view_span * tick / tick_count
                x = int(width * tick / tick_count)
                canvas.create_line(x, height - 12, x, height, fill="#455165")
                canvas.create_text(
                    x + 4,
                    height - 14,
                    text=self._format_duration(seconds),
                    anchor="sw",
                    fill="#7f8da3",
                    font=("Segoe UI", 7),
                )
            start, end = selection_start, selection_end
            x1 = int((start - view_start) / view_span * width)
            x2 = int((end - view_start) / view_span * width)
            canvas.create_rectangle(x1, 0, x2, height, outline="#ffd166", width=2)
            canvas.create_rectangle(0, 0, x1, height, fill="#000000", stipple="gray50", outline="")
            canvas.create_rectangle(x2, 0, width, height, fill="#000000", stipple="gray50", outline="")
            self._draw_fade_overlay(canvas, x1, x2, height, max(end - start, 0.0))
            self._draw_playback_cursor()

    def _legacy_draw_fade_overlay_only(self) -> None:
        canvas = self.wave_canvas
        canvas.delete("fade_overlay")
        if self.duration_seconds <= 0:
            return
        start, end = self._selection_bounds_no_error()
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        view_start, view_end = self._wave_view_bounds()
        x1 = int((start - view_start) / (view_end - view_start) * width)
        x2 = int((end - view_start) / (view_end - view_start) * width)
        self._draw_fade_overlay(canvas, x1, x2, height, max(end - start, 0.0))
        self._draw_playback_cursor()

    def _draw_fade_overlay(
        self,
        canvas: tk.Canvas,
        selection_x1: int,
        selection_x2: int,
        height: int,
        selection_seconds: float,
    ) -> None:
        if selection_seconds <= 0 or selection_x2 <= selection_x1:
            return
        span = selection_x2 - selection_x1
        fade_in = max(float(self.fade_in_var.get()), 0.0)
        fade_out = max(float(self.fade_out_var.get()), 0.0)
        fade_in_x = min(selection_x2, selection_x1 + int(span * min(fade_in, selection_seconds / 2) / selection_seconds))
        fade_out_x = max(selection_x1, selection_x2 - int(span * min(fade_out, selection_seconds / 2) / selection_seconds))
        if fade_in_x - selection_x1 >= 3:
            canvas.create_line(selection_x1, height - 12, fade_in_x, 12, fill="#f7f7f7", width=2, tags=("fade_overlay",))
        if selection_x2 - fade_out_x >= 3:
            canvas.create_line(fade_out_x, 12, selection_x2, height - 12, fill="#f7f7f7", width=2, tags=("fade_overlay",))

    def _fade_display_gain(self, seconds: float, selection_start: float, selection_end: float) -> float:
        if selection_end <= selection_start:
            return 1.0
        max_fade = (selection_end - selection_start) / 2
        fade_in = min(max(float(self.fade_in_var.get()), 0.0), max_fade)
        fade_out = min(max(float(self.fade_out_var.get()), 0.0), max_fade)
        gain = 1.0
        if fade_in > 0 and selection_start <= seconds < selection_start + fade_in:
            gain = min(gain, max((seconds - selection_start) / fade_in, 0.0))
        if fade_out > 0 and selection_end - fade_out < seconds <= selection_end:
            gain = min(gain, max((selection_end - seconds) / fade_out, 0.0))
        return gain

    def _legacy_draw_playback_cursor(self) -> None:
        canvas = self.wave_canvas
        canvas.delete("playback_cursor")
        if self.duration_seconds <= 0:
            return
        if not (self.current_preview_file or self.preview_playing or self.playback_cursor_manual):
            return
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        position = max(0.0, min(float(self.playback_position_var.get()), self.duration_seconds))
        view_start, view_end = self._wave_view_bounds()
        if not view_start <= position <= view_end:
            return
        play_x = int((position - view_start) / (view_end - view_start) * width)
        canvas.create_line(play_x, 0, play_x, height, fill="#ff4d6d", width=2, tags=("playback_cursor",))
        canvas.create_polygon(
            play_x - 5,
            0,
            play_x + 5,
            0,
            play_x,
            9,
            fill="#ff4d6d",
            outline="",
            tags=("playback_cursor",),
        )

    def _selection_bounds_no_error(self) -> tuple[float, float]:
        try:
            values = (float(self.selection_start_var.get()), float(self.selection_end_var.get()))
            if not all(math.isfinite(value) for value in values):
                return 0.0, self.duration_seconds
        except (tk.TclError, ValueError):
            return 0.0, self.duration_seconds
        start, end = min(values), max(values)
        start = max(0.0, min(start, self.duration_seconds))
        end = max(0.0, min(end, self.duration_seconds))
        return start, end

    def _wave_mouse_down(self, event: tk.Event) -> None:
        if self.duration_seconds <= 0 or self.busy:
            return
        self.wave_canvas.focus_set()
        seconds = self._event_to_seconds(event)
        self.playback_cursor_manual = False
        self.drag_start_seconds = seconds
        self.selection_start_var.set(seconds)
        self.selection_end_var.set(seconds)
        self._selection_changed()

    def _wave_mouse_drag(self, event: tk.Event) -> None:
        if self.duration_seconds <= 0 or self.drag_start_seconds is None or self.busy:
            return
        seconds = self._event_to_seconds(event)
        self.selection_start_var.set(min(self.drag_start_seconds, seconds))
        self.selection_end_var.set(max(self.drag_start_seconds, seconds))
        self._selection_changed()

    def _wave_mouse_up(self, _event: tk.Event) -> None:
        selecting = self.drag_start_seconds is not None
        self.drag_start_seconds = None
        if selecting and self.preview_playing and not self.busy:
            self.stop_preview(show_status=False)
            self.playback_cursor_manual = False
            try:
                self._start_context_preview()
            except (ValueError, tk.TclError, AudioProcessingError) as exc:
                self.status_var.set(f"Preview settings need attention: {exc}")

    def _wave_seek_begin(self, event: tk.Event) -> None:
        if self.duration_seconds <= 0 or self.busy:
            return
        self.playback_seek_dragging = True
        self._wave_seek_to_event(event)

    def _wave_seek_end(self, _event: tk.Event) -> None:
        self.playback_seek_dragging = False
        self._schedule_live_eq_update()
        self._schedule_live_mixer_update()

    def _wave_seek_to_event(self, event: tk.Event) -> None:
        if self.duration_seconds <= 0 or self.busy:
            return
        self.wave_canvas.focus_set()
        self.drag_start_seconds = None
        seconds = self._event_to_seconds(event)
        self.playback_cursor_manual = True
        self._set_playback_position(seconds)
        if self.preview_playing:
            self._restart_preview_from_cursor()

    def _event_to_seconds(self, event: tk.Event) -> float:
        width = max(self.wave_canvas.winfo_width(), 1)
        ratio = max(0.0, min(float(event.x) / width, 1.0))
        start, end = self._wave_view_bounds()
        return start + ratio * (end - start)

    def _cancel_main_after_callbacks(self) -> None:
        for attr in (
            "_layout_after",
            "_compact_after",
            "worker_queue_after_id",
            "drop_queue_after_id",
            "playback_progress_after_id",
            "waveform_resize_after_id",
            "waveform_fade_after_id",
        ):
            after_id = getattr(self, attr)
            if not after_id:
                continue
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(self, attr, None)
        self._stop_loading_messages()

        # Include widget-specific idle redraws in this application's interpreter.
        if self.closing:
            for after_id in self.tk.call("after", "info"):
                # The child widget owns its registered Python command and
                # removes it during destroy; only cancel the Tcl timer here.
                self.tk.call("after", "cancel", after_id)

    def on_close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.withdraw()
        if self.cancel_event:
            self.cancel_event.set()
        processes = list(self.realtime_processes)
        close = getattr(self.realtime_processes, "close", None)
        if close:
            close(wait=False)
        if self._file_spectrum is not None:
            self._file_spectrum.close(wait=False)
            self._file_spectrum = None
        if self.current_process is not None:
            processes.append(self.current_process)
        for process in processes:
            self._terminate_owned_process(process)
        self.realtime_processes = []
        self.preview_playing = False
        self._cancel_main_after_callbacks()
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
            self._workspace_close()
            self._disable_file_drop()
            self.settings["delete_temp_after_render"] = bool(self.delete_temp_var.get())
            self.settings["output_dir"] = str(self.output_dir)
            self.paths.write_settings(self.settings)
        except Exception:
            logging.exception("Could not persist all closing-session preferences")
        finally:
            self._cancel_main_after_callbacks()
            self.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--qa-transport":
        from backend.audio_processing.qa_transport import check
        raise SystemExit(check(StemSamplePrepApp, sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--qa-live-seek":
        from backend.audio_processing.qa_live_seek import check
        raise SystemExit(check(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--qa-live-eq":
        from backend.audio_processing.qa_live_eq import check
        raise SystemExit(check(sys.argv[2]))
    app = StemSamplePrepApp()
    if "--smoke-test" in sys.argv:
        app.after(750, app.on_close)
    app.mainloop()
