from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "delete_temp_after_render": False,
    "output_dir": "",
    "keep_adjustments": False,
    "recent_project": "",
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def from_runtime(cls) -> "AppPaths":
        return cls(app_root())

    @property
    def bin(self) -> Path:
        return self.root / "bin"

    @property
    def backend(self) -> Path:
        return self.root / "backend"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    def ensure(self) -> None:
        for folder in (self.bin, self.models, self.temp, self.output, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        if not self.settings_file.exists():
            self.write_settings(DEFAULT_SETTINGS)

    def read_settings(self) -> dict[str, Any]:
        if not self.settings_file.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            with self.settings_file.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_SETTINGS)
        settings = dict(DEFAULT_SETTINGS)
        if isinstance(loaded, dict):
            for key in DEFAULT_SETTINGS:
                if key in loaded:
                    settings[key] = loaded[key]
        return settings

    def write_settings(self, settings: dict[str, Any]) -> None:
        data = dict(DEFAULT_SETTINGS)
        data.update(settings)
        with self.settings_file.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        self.temp.mkdir(parents=True, exist_ok=True)
        self.models.mkdir(parents=True, exist_ok=True)

        env["TEMP"] = str(self.temp)
        env["TMP"] = str(self.temp)
        env["PYTHONPYCACHEPREFIX"] = str(self.temp / "pycache")
        env["TORCH_HOME"] = str(self.models / "torch")
        env["XDG_CACHE_HOME"] = str(self.models / "cache")
        env["HF_HOME"] = str(self.models / "huggingface")
        env["DEMUCS_CACHE"] = str(self.models / "demucs")
        env["MPLCONFIGDIR"] = str(self.temp / "matplotlib")
        env["NUMBA_CACHE_DIR"] = str(self.models / "numba")
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        return env

    def models_have_payload(self) -> bool:
        if not self.models.exists():
            return False
        for path in self.models.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".th", ".pt", ".pth", ".bin", ".safetensors"} and path.stat().st_size > 1024 * 1024:
                return True
        return False
