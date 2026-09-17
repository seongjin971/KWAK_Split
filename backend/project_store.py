"""Versioned projects, immutable companion audio assets and edit history."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import uuid
from pathlib import Path

from backend.audio_processing.ffmpeg_tools import OperationCancelled

FORMAT = "kwak-split-project"
VERSION = 1
EDIT_DEFAULTS = {
    "selection_start": 0.0, "selection_end": 0.0,
    "fade_in": 0.02, "fade_out": 0.02,
    "eq_low": 0.0, "eq_mid": 0.0, "eq_high": 0.0,
    "eq_low_freq": 100.0, "eq_mid_freq": 1000.0, "eq_high_freq": 8000.0,
    "eq_low_q": 0.8, "eq_mid_q": 1.0, "eq_high_q": 0.8,
    "eq_low_shape": "Bell", "eq_mid_shape": "Bell", "eq_high_shape": "Bell",
    "high_pass": 0.0, "low_pass": 0.0, "high_pass_q": 0.7, "low_pass_q": 0.7,
    "pitch_semitones": 0.0, "tempo_percent": 100.0,
    "peak_normalize": False, "limiter_enabled": True, "limiter_ceiling": 0.98,
    "stem_bypass": False, "loop": False, "sample_rate": 44100, "bit_depth": 16,
    "mp3_bitrate": 320,
}


def validate_edits(edits):
    if not isinstance(edits, dict):
        raise ValueError("Invalid project settings format.")
    result = dict(EDIT_DEFAULTS)
    for name, default in EDIT_DEFAULTS.items():
        value = edits.get(name, default)
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f"Invalid setting: {name}")
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid number: {name}")
        elif value not in ("Bell", "Low Shelf", "High Shelf"):
            raise ValueError(f"Invalid EQ shape: {name}")
        result[name] = value
    if result["sample_rate"] not in (44100, 48000) or result["bit_depth"] not in (16, 24):
        raise ValueError("Unsupported WAV format.")
    if result["mp3_bitrate"] not in (128, 192, 256, 320):
        raise ValueError("Unsupported MP3 bitrate.")
    if not 50 <= result["tempo_percent"] <= 200 or not -12 <= result["pitch_semitones"] <= 12:
        raise ValueError("Pitch or speed is outside the supported range.")
    stems = edits.get("stems", {})
    if not isinstance(stems, dict):
        raise ValueError("Invalid stem settings.")
    result["stems"] = {}
    for stem in ("vocals", "drums", "bass", "other"):
        values = stems.get(stem, {"volume": 100.0, "mute": False, "solo": False})
        if not isinstance(values, dict):
            raise ValueError("Invalid stem settings.")
        volume = values.get("volume", 100.0)
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 200:
            raise ValueError("Stem volume must be between 0% and 200%.")
        if not all(isinstance(values.get(key, False), bool) for key in ("mute", "solo")):
            raise ValueError("Invalid Mute/Solo value.")
        result["stems"][stem] = {"volume": volume, "mute": values.get("mute", False), "solo": values.get("solo", False)}
    return result


def atomic_json(path: Path, document: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_project(path: Path, document: dict, source: Path, stems: dict[str, Path], cancel_event=None):
    """Copy audio once by content hash. Only replace the manifest after success."""
    document = copy.deepcopy(document)
    document.update(format=FORMAT, version=VERSION, edits=validate_edits(document["edits"]))
    assets = path.with_name(path.name + ".assets")
    assets.mkdir(parents=True, exist_ok=True)

    def copy_asset(audio):
        digest = hashlib.sha256()
        temporary = assets / (uuid.uuid4().hex + ".tmp")
        try:
            with audio.open("rb") as src, temporary.open("wb") as dest:
                while chunk := src.read(1024 * 1024):
                    if cancel_event and cancel_event.is_set():
                        raise OperationCancelled("Project save cancelled.")
                    digest.update(chunk)
                    dest.write(chunk)
            destination = assets / (digest.hexdigest() + ".wav")
            if not destination.exists():
                os.replace(temporary, destination)
            return destination.relative_to(path.parent).as_posix()
        finally:
            temporary.unlink(missing_ok=True)

    document["source"] = copy_asset(source)
    document["stems"] = {name: copy_asset(audio) for name, audio in stems.items()}
    if cancel_event and cancel_event.is_set():
        raise OperationCancelled("Project save cancelled.")
    atomic_json(path, document)


def read_project(path: Path, allow_external=False):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("The project file is too large.")
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict) or document.get("format") != FORMAT or document.get("version") != VERSION:
        raise ValueError("Unsupported KWAK Split project.")
    document["edits"] = validate_edits(document.get("edits"))
    if "original_input" in document and not isinstance(document["original_input"], str):
        raise ValueError("Invalid original audio name.")
    coverage = document.get("stem_range", [0, 0])
    if (not isinstance(coverage, list) or len(coverage) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in coverage)
            or not 0 <= coverage[0] <= coverage[1]):
        raise ValueError("Invalid stem time range.")

    def resolve(value):
        if not isinstance(value, str) or not value:
            raise ValueError("The project audio path is missing.")
        resolved = (path.parent / value).resolve()
        if not allow_external and path.parent.resolve() not in resolved.parents:
            raise ValueError("The audio path points outside the project folder.")
        return resolved

    document["source_path"] = resolve(document.get("source"))
    stems = document.get("stems", {})
    if not isinstance(stems, dict) or set(stems) - {"vocals", "drums", "bass", "other"}:
        raise ValueError("Invalid stem list.")
    document["stem_paths"] = {name: resolve(value) for name, value in stems.items()}
    return document


class EditHistory:
    def __init__(self, state, limit=100):
        self.states = [copy.deepcopy(state)]
        self.index = 0
        self.limit = limit

    def push(self, state):
        if state == self.states[self.index]:
            return
        self.states = self.states[:self.index + 1] + [copy.deepcopy(state)]
        self.states = self.states[-self.limit:]
        self.index = len(self.states) - 1

    def undo(self):
        self.index = max(0, self.index - 1)
        return copy.deepcopy(self.states[self.index])

    def redo(self):
        self.index = min(len(self.states) - 1, self.index + 1)
        return copy.deepcopy(self.states[self.index])
