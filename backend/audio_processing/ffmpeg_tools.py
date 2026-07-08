from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import wave
from array import array
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from backend.app_paths import AppPaths
from backend.audio_processing.musical import build_rubberband_filter


LogCallback = Callable[[str], None] | None
ProcessCallback = Callable[[subprocess.Popen | None], None] | None


class AudioProcessingError(RuntimeError):
    pass


class OperationCancelled(AudioProcessingError):
    pass


class ToolMissingError(AudioProcessingError):
    pass


@dataclass(frozen=True)
class MixStem:
    name: str
    path: Path
    gain: float


@dataclass(frozen=True)
class AudioEffects:
    low_db: float = 0.0
    mid_db: float = 0.0
    high_db: float = 0.0
    low_freq: float = 100.0
    mid_freq: float = 1000.0
    high_freq: float = 8000.0
    low_q: float = 0.8
    mid_q: float = 1.0
    high_q: float = 0.8
    low_shape: str = "Bell"
    mid_shape: str = "Bell"
    high_shape: str = "Bell"
    high_pass_hz: float = 0.0
    low_pass_hz: float = 0.0
    high_pass_q: float = 0.7
    low_pass_q: float = 0.7
    pitch_semitones: float = 0.0
    tempo_ratio: float = 1.0
    peak_normalize: bool = False
    limiter_enabled: bool = True
    limiter_ceiling: float = 0.98


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "audio"


def find_executable(paths: AppPaths, name: str) -> Path | None:
    local = paths.bin / f"{name}.exe"
    if local.exists():
        return local
    found = shutil.which(name)
    return Path(found) if found else None


def require_ffmpeg(paths: AppPaths) -> Path:
    ffmpeg = find_executable(paths, "ffmpeg")
    if not ffmpeg:
        raise ToolMissingError("FFmpeg was not found. Check bin/ffmpeg.exe in the app folder.")
    return ffmpeg


def require_ffplay(paths: AppPaths) -> Path:
    ffplay = find_executable(paths, "ffplay")
    if not ffplay:
        raise ToolMissingError("FFplay was not found. Check bin/ffplay.exe in the app folder.")
    return ffplay


def _no_window_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def _is_cancelled(cancel_event: Event | None) -> bool:
    return bool(cancel_event and cancel_event.is_set())


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _ffprobe_duration(paths: AppPaths, audio_path: Path) -> float | None:
    ffprobe = find_executable(paths, "ffprobe")
    if not ffprobe:
        return None
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(audio_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=paths.runtime_env(),
            encoding="utf-8",
            errors="replace",
            **_no_window_kwargs(),
        )
        payload = json.loads(completed.stdout)
        return float(payload["format"]["duration"])
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError):
        return None


def read_duration(paths: AppPaths, audio_path: Path) -> float:
    probed = _ffprobe_duration(paths, audio_path)
    if probed and probed > 0:
        return probed
    if audio_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(audio_path), "rb") as handle:
                return handle.getnframes() / float(handle.getframerate())
        except (wave.Error, OSError):
            pass
    raise AudioProcessingError("Could not read the audio duration. Check the FFmpeg/FFprobe setup.")


def convert_to_work_wav(
    paths: AppPaths,
    input_path: Path,
    output_path: Path,
    log: LogCallback = None,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback = None,
) -> None:
    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_executable(paths, "ffmpeg")
    if input_path.suffix.lower() == ".wav" and not ffmpeg:
        try:
            with wave.open(str(input_path), "rb"):
                shutil.copy2(input_path, output_path)
                if log:
                    log("Copied WAV file to the working temp folder.")
                return
        except (wave.Error, OSError):
            pass

    ffmpeg = require_ffmpeg(paths)
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        *_output_format_args(output_path),
        str(output_path),
    ]
    if log:
        log("Converting input file to working WAV.")
    _run_checked(command, paths, log, cancel_event, process_callback)


def waveform_peaks(
    paths: AppPaths,
    audio_path: Path,
    bucket_count: int = 900,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback = None,
) -> list[float]:
    ffmpeg = find_executable(paths, "ffmpeg")
    if ffmpeg:
        return _waveform_peaks_ffmpeg(paths, ffmpeg, audio_path, bucket_count, cancel_event, process_callback)
    if audio_path.suffix.lower() == ".wav":
        return _waveform_peaks_wav(audio_path, bucket_count, cancel_event)
    raise ToolMissingError("bin/ffmpeg.exe is required to build the waveform.")


def _waveform_peaks_ffmpeg(
    paths: AppPaths,
    ffmpeg: Path,
    audio_path: Path,
    bucket_count: int,
    cancel_event: Event | None,
    process_callback: ProcessCallback,
) -> list[float]:
    duration = max(read_duration(paths, audio_path), 0.01)
    sample_rate = 8000
    total_samples = max(int(duration * sample_rate), 1)
    samples_per_bucket = max(math.ceil(total_samples / bucket_count), 1)
    peaks = [0.0 for _ in range(bucket_count)]
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=paths.runtime_env(),
        **_no_window_kwargs(),
    )
    if process_callback:
        process_callback(process)
    assert process.stdout is not None
    sample_index = 0
    max_possible = 32768.0
    try:
        while True:
            if _is_cancelled(cancel_event):
                _stop_process(process)
                raise OperationCancelled("Operation cancelled.")
            chunk = process.stdout.read(32768)
            if not chunk:
                break
            if len(chunk) % 2:
                chunk = chunk[:-1]
            values = array("h")
            values.frombytes(chunk)
            for value in values:
                bucket = min(sample_index // samples_per_bucket, bucket_count - 1)
                peaks[bucket] = max(peaks[bucket], min(abs(value) / max_possible, 1.0))
                sample_index += 1
    finally:
        if process_callback:
            process_callback(None)

    exit_code = process.wait()
    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")
    if exit_code != 0:
        raise AudioProcessingError("FFmpeg waveform generation failed.")
    return peaks


def _waveform_peaks_wav(audio_path: Path, bucket_count: int, cancel_event: Event | None) -> list[float]:
    with wave.open(str(audio_path), "rb") as handle:
        frames = handle.getnframes()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        if sample_width != 2:
            raise AudioProcessingError("A 16-bit WAV file is required to build the waveform without FFmpeg.")
        samples_per_bucket = max(math.ceil(frames / bucket_count), 1)
        peaks = [0.0 for _ in range(bucket_count)]
        frame_index = 0
        max_possible = 32768.0
        while True:
            if _is_cancelled(cancel_event):
                raise OperationCancelled("Operation cancelled.")
            raw = handle.readframes(4096)
            if not raw:
                break
            values = array("h")
            values.frombytes(raw)
            for offset in range(0, len(values), channels):
                sample = values[offset]
                bucket = min(frame_index // samples_per_bucket, bucket_count - 1)
                peaks[bucket] = max(peaks[bucket], min(abs(sample) / max_possible, 1.0))
                frame_index += 1
        return peaks


def render_mix(
    paths: AppPaths,
    stems: Iterable[MixStem],
    output_path: Path,
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    log: LogCallback = None,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback = None,
    effects: AudioEffects | None = None,
) -> None:
    active = _prepare_active_stems(stems, duration_seconds, cancel_event)

    ffmpeg = require_ffmpeg(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    effects = effects or AudioEffects()
    if effects.peak_normalize:
        normalize_dir = paths.temp / "renders"
        normalize_dir.mkdir(parents=True, exist_ok=True)
        temp_path = normalize_dir / f"{safe_name(output_path.stem)}_{os.getpid()}.normalize_work.wav"
        temp_effects = replace(effects, peak_normalize=False, limiter_enabled=False)
        try:
            _render_mix_once(
                paths,
                ffmpeg,
                active,
                temp_path,
                start_seconds,
                duration_seconds,
                fade_in,
                fade_out,
                temp_effects,
                log,
                cancel_event,
                process_callback,
                post_gain=0.125,
            )
            max_volume_db = _measure_max_volume_db(paths, ffmpeg, temp_path, cancel_event, process_callback)
            target_db = _linear_to_db(_limiter_ceiling(effects))
            gain_db = 0.0 if max_volume_db is None else target_db - max_volume_db
            if log:
                log(f"Peak normalize gain: {gain_db:.2f} dB")
            _apply_output_gain(
                paths,
                ffmpeg,
                temp_path,
                output_path,
                gain_db,
                effects,
                log,
                cancel_event,
                process_callback,
            )
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass
        return

    _render_mix_once(
        paths,
        ffmpeg,
        active,
        output_path,
        start_seconds,
        duration_seconds,
        fade_in,
        fade_out,
        effects,
        log,
        cancel_event,
        process_callback,
    )


def start_realtime_mix(
    paths: AppPaths,
    stems: Iterable[MixStem],
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    effects: AudioEffects | None = None,
) -> list[subprocess.Popen]:
    active = _prepare_active_stems(stems, duration_seconds, None)
    ffmpeg = require_ffmpeg(paths)
    ffplay = require_ffplay(paths)
    effects = effects or AudioEffects()
    input_args, filter_complex = _build_mix_filter(
        active,
        start_seconds,
        duration_seconds,
        fade_in,
        fade_out,
        effects,
    )
    ffmpeg_command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[outa]",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-sample_fmt",
        "s16",
        "-f",
        "wav",
        "pipe:1",
    ]
    ffplay_command = [
        str(ffplay),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nodisp",
        "-autoexit",
        "-i",
        "pipe:0",
    ]
    ffmpeg_process = subprocess.Popen(
        ffmpeg_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=paths.runtime_env(),
        **_no_window_kwargs(),
    )
    assert ffmpeg_process.stdout is not None
    try:
        ffplay_process = subprocess.Popen(
            ffplay_command,
            stdin=ffmpeg_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=paths.runtime_env(),
            **_no_window_kwargs(),
        )
    except Exception:
        _stop_process(ffmpeg_process)
        raise
    finally:
        ffmpeg_process.stdout.close()
    return [ffplay_process, ffmpeg_process]


def _prepare_active_stems(
    stems: Iterable[MixStem],
    duration_seconds: float,
    cancel_event: Event | None,
) -> list[MixStem]:
    active = [stem for stem in stems if stem.gain > 0.0001]
    if not active:
        raise AudioProcessingError("No stems to render. Check mute, solo, and volume settings.")
    if duration_seconds <= 0:
        raise AudioProcessingError("Selected range length is 0 seconds.")
    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")
    return active


def _render_mix_once(
    paths: AppPaths,
    ffmpeg: Path,
    active: list[MixStem],
    output_path: Path,
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    effects: AudioEffects,
    log: LogCallback,
    cancel_event: Event | None,
    process_callback: ProcessCallback,
    post_gain: float = 1.0,
) -> None:
    input_args, filter_complex = _build_mix_filter(
        active,
        start_seconds,
        duration_seconds,
        fade_in,
        fade_out,
        effects,
        post_gain,
    )
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[outa]",
        "-ar",
        "44100",
        "-ac",
        "2",
        *_output_format_args(output_path),
        str(output_path),
    ]
    if log:
        names = ", ".join(stem.name for stem in active)
        log(f"Starting WAV render: {names}")
    _run_checked(command, paths, log, cancel_event, process_callback)


def _output_format_args(output_path: Path) -> list[str]:
    if output_path.suffix.lower() == ".mp3":
        return ["-c:a", "libmp3lame", "-b:a", "320k"]
    return ["-sample_fmt", "s16"]


def _build_mix_filter(
    active: list[MixStem],
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    effects: AudioEffects,
    post_gain: float = 1.0,
) -> tuple[list[str], str]:
    input_args: list[str] = []
    for stem in active:
        input_args.extend(
            [
                "-ss",
                f"{max(start_seconds, 0):.6f}",
                "-t",
                f"{duration_seconds:.6f}",
                "-i",
                str(stem.path),
            ]
        )

    fade_in = max(0.0, min(fade_in, duration_seconds / 2))
    fade_out = max(0.0, min(fade_out, duration_seconds / 2))
    filters: list[str] = []
    labels: list[str] = []
    for index, stem in enumerate(active):
        chain = f"[{index}:a]aresample=44100,volume={stem.gain:.6f}"
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in:.6f}"
        if fade_out > 0:
            chain += f",afade=t=out:st={max(duration_seconds - fade_out, 0):.6f}:d={fade_out:.6f}"
        label = f"a{index}"
        chain += f"[{label}]"
        filters.append(chain)
        labels.append(f"[{label}]")

    tail_filters = _effect_filters(effects)
    rubberband = build_rubberband_filter(effects.tempo_ratio, effects.pitch_semitones)
    if rubberband:
        tail_filters.append(rubberband)
    if post_gain < 0.9999 or post_gain > 1.0001:
        tail_filters.append(f"volume={post_gain:.6f}")
    if effects.limiter_enabled:
        tail_filters.append(f"alimiter=limit={_limiter_ceiling(effects):.6f}")
    if not tail_filters:
        tail_filters.append("anull")

    if len(labels) == 1:
        filters.append(f"{labels[0]}{','.join(tail_filters)}[outa]")
    else:
        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:duration=first,{','.join(tail_filters)}[outa]"
        )
    return input_args, ";".join(filters)


def _effect_filters(effects: AudioEffects) -> list[str]:
    filters: list[str] = []
    if abs(effects.low_db) >= 0.05:
        filters.append(_eq_filter(effects.low_shape, effects.low_freq, effects.low_q, effects.low_db))
    if abs(effects.mid_db) >= 0.05:
        filters.append(_eq_filter(effects.mid_shape, effects.mid_freq, effects.mid_q, effects.mid_db))
    if abs(effects.high_db) >= 0.05:
        filters.append(_eq_filter(effects.high_shape, effects.high_freq, effects.high_q, effects.high_db))
    if effects.high_pass_hz > 0:
        filters.append(f"highpass=f={_clamp_frequency(effects.high_pass_hz):.3f}:t=q:w={_clamp_q(effects.high_pass_q):.3f}")
    if effects.low_pass_hz > 0:
        filters.append(f"lowpass=f={_clamp_frequency(effects.low_pass_hz):.3f}:t=q:w={_clamp_q(effects.low_pass_q):.3f}")
    return filters


def _eq_filter(shape: str, frequency: float, q: float, gain_db: float) -> str:
    frequency = _clamp_frequency(frequency)
    q = _clamp_q(q)
    gain_db = _clamp_db(gain_db)
    shape_key = shape.strip().lower().replace(" ", "_")
    if shape_key == "low_shelf":
        return f"bass=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}"
    if shape_key == "high_shelf":
        return f"treble=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}"
    return f"equalizer=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}"


def _clamp_db(value: float) -> float:
    return max(min(float(value), 18.0), -18.0)


def _clamp_frequency(value: float) -> float:
    return max(min(float(value), 20000.0), 20.0)


def _clamp_q(value: float) -> float:
    return max(min(float(value), 10.0), 0.1)


def _limiter_ceiling(effects: AudioEffects) -> float:
    return max(min(float(effects.limiter_ceiling), 1.0), 0.05)


def _linear_to_db(value: float) -> float:
    value = max(float(value), 0.000001)
    return 20.0 * math.log10(value)


def _measure_max_volume_db(
    paths: AppPaths,
    ffmpeg: Path,
    audio_path: Path,
    cancel_event: Event | None,
    process_callback: ProcessCallback,
) -> float | None:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-i",
        str(audio_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        os.devnull,
    ]
    output = _run_capture(command, paths, None, cancel_event, process_callback)
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", output)
    return float(match.group(1)) if match else None


def _apply_output_gain(
    paths: AppPaths,
    ffmpeg: Path,
    input_path: Path,
    output_path: Path,
    gain_db: float,
    effects: AudioEffects,
    log: LogCallback,
    cancel_event: Event | None,
    process_callback: ProcessCallback,
) -> None:
    filters = [f"volume={gain_db:.6f}dB"]
    if effects.limiter_enabled:
        filters.append(f"alimiter=limit={_limiter_ceiling(effects):.6f}")
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-af",
        ",".join(filters),
        "-ar",
        "44100",
        "-ac",
        "2",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    _run_checked(command, paths, log, cancel_event, process_callback)


def _run_capture(
    command: list[str],
    paths: AppPaths,
    log: LogCallback = None,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback = None,
) -> str:
    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=paths.runtime_env(),
        **_no_window_kwargs(),
    )
    if process_callback:
        process_callback(process)
    assert process.stdout is not None
    captured: list[str] = []
    try:
        for line in process.stdout:
            if _is_cancelled(cancel_event):
                _stop_process(process)
                raise OperationCancelled("Operation cancelled.")
            text = line.strip()
            if text:
                captured.append(text)
                if log:
                    log(text)
        exit_code = process.wait()
    finally:
        if process_callback:
            process_callback(None)

    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")
    if exit_code != 0:
        tail = "\n".join(captured[-8:])
        raise AudioProcessingError(f"FFmpeg operation failed.\n{tail}")
    return "\n".join(captured)


def _run_checked(
    command: list[str],
    paths: AppPaths,
    log: LogCallback = None,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback = None,
) -> None:
    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=paths.runtime_env(),
        **_no_window_kwargs(),
    )
    if process_callback:
        process_callback(process)
    assert process.stdout is not None
    captured: list[str] = []
    try:
        for line in process.stdout:
            if _is_cancelled(cancel_event):
                _stop_process(process)
                raise OperationCancelled("Operation cancelled.")
            text = line.strip()
            if text:
                captured.append(text)
                if log:
                    log(text)
        exit_code = process.wait()
    finally:
        if process_callback:
            process_callback(None)

    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")
    if exit_code != 0:
        tail = "\n".join(captured[-8:])
        raise AudioProcessingError(f"FFmpeg operation failed.\n{tail}")
