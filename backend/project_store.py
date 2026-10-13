"""Legacy project-file utilities for archived QA; not used by the application."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import uuid
from pathlib import Path

from backend.audio_processing.ffmpeg_tools import OperationCancelled
from backend.edit_state import EDIT_DEFAULTS, EditHistory, validate_edits

FORMAT = "kwak-split-project"
VERSION = 2
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
    if not isinstance(document, dict) or document.get("format") != FORMAT or document.get("version") not in (1, VERSION):
        raise ValueError("Unsupported KWAK Split project.")
    if document.get("version") == 1 and isinstance(document.get("edits"), dict):
        # v1 had one two-pole pass filter. Preserve its sound when reopening.
        document["edits"].setdefault("high_pass_slope", 12)
        document["edits"].setdefault("low_pass_slope", 12)
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
