from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from typing import Callable

from backend.app_paths import AppPaths
from backend.audio_processing import STEMS
from backend.audio_processing.ffmpeg_tools import AudioProcessingError, OperationCancelled


LogCallback = Callable[[str], None] | None
ProgressCallback = Callable[[float], None] | None
ProcessCallback = Callable[[subprocess.Popen | None], None] | None


def _no_window_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


class DemucsMissingError(AudioProcessingError):
    pass


class StemSeparator:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def available_command(self) -> list[str] | None:
        embedded_python = self.paths.backend / "demucs_runtime" / "python.exe"
        if embedded_python.exists():
            return [str(embedded_python), "-m", "demucs"]

        venv_python = self.paths.backend / "demucs_runtime" / "Scripts" / "python.exe"
        if venv_python.exists() and self._venv_home_exists(venv_python):
            return [str(venv_python), "-m", "demucs"]

        local_demucs = self.paths.bin / "demucs.exe"
        if local_demucs.exists():
            return [str(local_demucs)]

        path_demucs = shutil.which("demucs")
        if path_demucs:
            return [path_demucs]

        if importlib.util.find_spec("demucs"):
            return [sys.executable, "-m", "demucs"]

        return None

    def _venv_home_exists(self, venv_python: Path) -> bool:
        cfg = venv_python.parents[1] / "pyvenv.cfg"
        if not cfg.exists():
            return False
        try:
            for line in cfg.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip().lower() == "executable":
                    executable = Path(value.strip())
                    return not executable.is_absolute() or executable.exists()
        except OSError:
            return False
        return True

    def separate(
        self,
        source_wav: Path,
        session_name: str,
        log: LogCallback = None,
        progress: ProgressCallback = None,
        cancel_event: Event | None = None,
        process_callback: ProcessCallback = None,
    ) -> dict[str, Path]:
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled("Operation cancelled.")

        command_prefix = self.available_command()
        if not command_prefix:
            raise DemucsMissingError(
                "Demucs runtime was not found. See the 'Preparing the Demucs runtime' section in README "
                "and place the portable runtime under backend/demucs_runtime."
            )

        output_root = self.paths.temp / "stems" / session_name
        self._safe_remove_tree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        jobs = self._default_jobs()
        command = [
            *command_prefix,
            "--name",
            "htdemucs",
            "--out",
            str(output_root),
        ]
        if jobs > 0:
            command.extend(["--jobs", str(jobs)])
        command.append(str(source_wav))
        if log and jobs > 0:
            log(f"Demucs CPU jobs: {jobs}")
        if log:
            log("Starting Demucs 4-stem separation. Large files can take a while.")

        started_at = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=str(self.paths.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.paths.runtime_env(),
            **_no_window_kwargs(),
        )
        if process_callback:
            process_callback(process)
        assert process.stdout is not None
        captured: list[str] = []
        percent_pattern = re.compile(r"(\d{1,3})%")
        buffer = ""
        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    self._stop_process(process)
                    raise OperationCancelled("Operation cancelled.")
                chunk = process.stdout.read(256)
                if not chunk:
                    break
                buffer += chunk
                parts = re.split(r"[\r\n]", buffer)
                buffer = parts.pop()
                for raw in parts:
                    text = raw.strip()
                    if not text:
                        continue
                    captured.append(text)
                    match = percent_pattern.search(text)
                    if match and progress:
                        progress(min(float(match.group(1)), 100.0))
                    if log:
                        log(text)
            text = buffer.strip()
            if text:
                captured.append(text)
                match = percent_pattern.search(text)
                if match and progress:
                    progress(min(float(match.group(1)), 100.0))
                if log:
                    log(text)
            exit_code = process.wait()
        finally:
            if process_callback:
                process_callback(None)

        if cancel_event and cancel_event.is_set():
            raise OperationCancelled("Operation cancelled.")
        if exit_code != 0:
            tail = "\n".join(captured[-10:])
            raise AudioProcessingError(f"Demucs separation failed.\n{tail}")

        stems = self._locate_stems(output_root)
        missing = [stem for stem in STEMS if stem not in stems]
        if missing:
            raise AudioProcessingError("Some stems were missing from the separation output: " + ", ".join(missing))
        if progress:
            progress(100.0)
        if log:
            log(f"Demucs split finished in {self._format_elapsed(time.monotonic() - started_at)}.")
        return stems

    def _default_jobs(self) -> int:
        cpu_count = os.cpu_count() or 1
        if cpu_count < 6:
            return 0
        return 2

    def _format_elapsed(self, seconds: float) -> str:
        total = max(int(seconds), 0)
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _locate_stems(self, output_root: Path) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for stem in STEMS:
            candidates = sorted(output_root.rglob(f"{stem}.wav"), key=lambda path: path.stat().st_mtime)
            if candidates:
                found[stem] = candidates[-1]
        return found

    def _safe_remove_tree(self, target: Path) -> None:
        resolved_target = target.resolve()
        resolved_temp = self.paths.temp.resolve()
        if resolved_target == resolved_temp or resolved_temp not in resolved_target.parents:
            raise AudioProcessingError("Unsafe temp cleanup path detected.")
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

    def _stop_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
