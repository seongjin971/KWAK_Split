from __future__ import annotations

from backend.audio_processing.equalizer import pass_section_qs
from backend.audio_processing.playback_stream import AnalyzedPlayback, DecoderStage
from backend.audio_processing.live_eq import LiveEqController, bank_target, available as live_eq_available

import json
import math
import os
import re
import shutil
import subprocess
import wave
from array import array
from dataclasses import dataclass, fields, replace
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from backend.app_paths import AppPaths
from backend.audio_processing.musical import build_rubberband_filter
from backend.compact_model import EQ_GAIN_LIMIT


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
    offset_seconds: float = 0.0


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
    high_pass_slope: int = 12
    low_pass_slope: int = 12
    pitch_semitones: float = 0.0
    tempo_ratio: float = 1.0
    peak_normalize: bool = False
    limiter_enabled: bool = True
    limiter_ceiling: float = 0.98
    sample_rate: int = 44100
    bit_depth: int = 16
    mp3_bitrate: int = 320


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
        "-c:a",
        "pcm_f32le",
        str(output_path),
    ]
    if log:
        log("Converting input file to working WAV.")
    _run_checked(command, paths, log, cancel_event, process_callback)


def extract_audio_range(paths: AppPaths, source: Path, output: Path, start: float, duration: float,
                        cancel_event=None, process_callback=None, log=None) -> None:
    if start < 0 or duration <= 0:
        raise AudioProcessingError("Select a range to separate.")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(require_ffmpeg(paths)), "-hide_banner", "-y", "-ss", f"{start:.6f}",
               "-i", str(source), "-t", f"{duration:.6f}", "-vn", "-ac", "2",
               "-c:a", "pcm_f32le", str(output)]
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
        process.stdout.close()
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


def stereo_waveform_peaks(paths: AppPaths, audio_path: Path, bucket_count: int = 4096,
                          cancel_event: Event | None = None, process_callback=None) -> list[tuple[float, float]]:
    """Read the working PCM WAV without summing channels or discarding highs."""
    try:
        handle = wave.open(str(audio_path), "rb")
    except wave.Error:
        return _stereo_float_peaks(paths, audio_path, bucket_count, cancel_event, process_callback)
    with handle:
        frames, channels, width = handle.getnframes(), handle.getnchannels(), handle.getsampwidth()
        if width not in (2, 3, 4):
            raise AudioProcessingError("Working audio must be 16, 24 or 32-bit PCM.")
        count = min(bucket_count, max(1, frames))
        bucket_size = max(1, math.ceil(frames / count))
        left, right = [0.0] * count, [0.0] * count
        index, maximum = 0, float(1 << (8*width-1))
        while raw := handle.readframes(8192):
            if _is_cancelled(cancel_event):
                raise OperationCancelled("Waveform preparation cancelled.")
            if width in (2, 4):
                values = array("h" if width == 2 else "i")
                values.frombytes(raw)
            else:
                values = [int.from_bytes(raw[i:i+3], "little", signed=True) for i in range(0, len(raw), 3)]
            for offset in range(0, len(values), channels):
                bucket = min(index // bucket_size, count-1)
                left[bucket] = max(left[bucket], abs(values[offset]) / maximum)
                right[bucket] = max(right[bucket], abs(values[offset + (1 if channels > 1 else 0)]) / maximum)
                index += 1
        return list(zip(left, right))


def _stereo_float_peaks(paths, source, count, cancel_event, process_callback):
    ffmpeg = find_executable(paths, "ffmpeg")
    if not ffmpeg:
        raise ToolMissingError("FFmpeg is required for floating-point working audio.")
    rate = 48000
    bucket_size = max(1, math.ceil(read_duration(paths, source) * rate / count))
    left, right = [0.0]*count, [0.0]*count
    process = subprocess.Popen([ffmpeg, "-v", "error", "-i", str(source), "-vn", "-ac", "2", "-ar", str(rate),
                                "-f", "f32le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=paths.runtime_env(), **_no_window_kwargs())
    if process_callback: process_callback(process)
    index = 0
    try:
        while raw := process.stdout.read(65536):
            if _is_cancelled(cancel_event):
                raise OperationCancelled("Waveform preparation cancelled.")
            values = array("f"); values.frombytes(raw)
            for offset in range(0, len(values)-1, 2):
                bucket = min(index//bucket_size, count-1)
                left[bucket] = max(left[bucket], abs(values[offset]))
                right[bucket] = max(right[bucket], abs(values[offset+1]))
                index += 1
        if _is_cancelled(cancel_event):
            raise OperationCancelled("Waveform preparation cancelled.")
        if process.wait() != 0:
            raise AudioProcessingError("Stereo waveform preparation failed.")
    finally:
        process.stdout.close()
        if process.poll() is None: _stop_process(process)
        if process_callback: process_callback(None)
    return list(zip(left, right))


def audio_channels(paths: AppPaths, audio_path: Path, cancel_event=None, process_callback=None) -> int:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            return handle.getnchannels()
    except (wave.Error, EOFError):
        probe = find_executable(paths, "ffprobe")
        if probe:
            output = _run_capture([probe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                                   "stream=channels", "-of", "csv=p=0", str(audio_path)],
                                  paths, None, cancel_event, process_callback)
            try:
                return int(output.strip().splitlines()[0])
            except (ValueError, IndexError):
                pass
    return 2


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
    include_silent: bool = False,
    fade_bounds: tuple[float, float] | None = None,
) -> None:
    active = _prepare_active_stems(stems, duration_seconds, cancel_event, include_silent)

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
                working_float=True,
                fade_bounds=fade_bounds,
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
        fade_bounds=fade_bounds,
    )


def start_realtime_mix(
    paths: AppPaths,
    stems: Iterable[MixStem],
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    effects: AudioEffects | None = None,
    fade_bounds: tuple[float, float] | None = None,
    *, output_player=None,
) -> list[subprocess.Popen]:
    ffmpeg = require_ffmpeg(paths)
    ffplay = require_ffplay(paths) if output_player is None else None
    settings = dict(stems=tuple(stems), start_seconds=start_seconds, duration_seconds=duration_seconds,
                    fade_in=fade_in, fade_out=fade_out, effects=effects or AudioEffects(),
                    fade_bounds=fade_bounds)

    def decoder_factory(**updated):
        return _start_realtime_decoder(paths, ffmpeg, **updated)

    try:
        stage = decoder_factory(**settings)
    except Exception:
        if output_player is not None:output_player.terminate()
        raise
    if output_player is not None:
        return AnalyzedPlayback(stage, output_player, decoder_factory=decoder_factory, settings=settings)
    ffplay_command = [
        str(ffplay), "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit", "-stats",
        "-f", "s16le", "-ar", "44100", "-ch_layout", "stereo",
        "-probesize", "32", "-analyzeduration", "0", "-avioflags", "direct", "-i", "pipe:0",
    ]
    try:
        player = subprocess.Popen(
            ffplay_command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, bufsize=0, env=paths.runtime_env(), **_no_window_kwargs(),
        )
    except Exception:
        stage.close()
        raise
    return AnalyzedPlayback(stage, player, decoder_factory=decoder_factory, settings=settings)


def _start_realtime_decoder(paths, ffmpeg, stems, start_seconds, duration_seconds,
                            fade_in, fade_out, effects, fade_bounds):
    """A seek warms another decoder while the current output device keeps playing."""
    active = _prepare_active_stems(stems, duration_seconds, None, include_silent=True)
    live_filters, parameters = _live_eq_plan(effects)
    controller = (LiveEqController(parameters, dual_bank=True, mixer_weights=_mix_weights(active))
                  if live_eq_available() else None)
    input_args, filter_complex = _build_mix_filter(
        active,
        start_seconds,
        duration_seconds,
        fade_in,
        fade_out,
        effects,
        fade_bounds=fade_bounds,
        live_eq_filters=([controller.filter, *live_filters]
                         if controller else None),
        live_mixer=controller is not None,
    )
    ffmpeg_command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-filter_complex_threads", "1",
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
        "s16le",
        "-flush_packets", "1",
        "-threads:a", "1",
        "pipe:1",
    ]
    ffmpeg_process = subprocess.Popen(
        ffmpeg_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
        env=paths.runtime_env(),
        **_no_window_kwargs(),
    )
    assert ffmpeg_process.stdout is not None
    structure = _eq_restart_key(effects)
    def eq_parameters(updated):
        return _live_eq_plan(updated)[1] if _eq_restart_key(updated) == structure else None
    identities = tuple((stem.name, stem.path, stem.offset_seconds) for stem in active)
    def mixer_parameters(updated):
        updated = list(updated)
        items = {(stem.name, stem.path, stem.offset_seconds): stem for stem in updated}
        if len(items) != len(updated) or items.keys() != set(identities):
            return None  # Input files/ranges require the existing rebuild path.
        return _mix_weights([items[key] for key in identities])
    return DecoderStage(ffmpeg_process, controller, eq_parameters, mixer_parameters)


def _mix_weights(stems):
    return tuple(round(stem.gain, 6) for stem in stems)


def analyze_rendered_preview(paths: AppPaths, audio_path: Path) -> AnalyzedPlayback:
    """Analyze the rendered file that winsound plays, without rendering again."""
    command = [str(require_ffmpeg(paths)), "-v", "error", "-nostdin", "-i", str(audio_path),
               "-ar", "44100", "-ac", "2", "-f", "s16le", "pipe:1"]
    decoder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=paths.runtime_env(), **_no_window_kwargs())
    return AnalyzedPlayback(decoder)


def _prepare_active_stems(
    stems: Iterable[MixStem],
    duration_seconds: float,
    cancel_event: Event | None,
    include_silent: bool = False,
) -> list[MixStem]:
    active = [stem for stem in stems if stem.gain > 0.0001 or (include_silent and stem.gain >= 0)]
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
    working_float: bool = False,
    fade_bounds: tuple[float, float] | None = None,
) -> None:
    input_args, filter_complex = _build_mix_filter(
        active,
        start_seconds,
        duration_seconds,
        fade_in,
        fade_out,
        effects,
        post_gain,
        fade_bounds=fade_bounds,
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
        str(effects.sample_rate),
        "-ac",
        "2",
        *(["-c:a", "pcm_f32le"] if working_float else _output_format_args(output_path, effects)),
        str(output_path),
    ]
    if log:
        names = ", ".join(stem.name for stem in active)
        log(f"Starting WAV render: {names}")
    _run_checked(command, paths, log, cancel_event, process_callback)


def _output_format_args(output_path: Path, effects: AudioEffects | None = None) -> list[str]:
    effects = effects or AudioEffects()
    if effects.sample_rate not in (44100, 48000) or effects.bit_depth not in (16, 24):
        raise AudioProcessingError("WAV supports 44.1/48kHz and 16/24bit.")
    if effects.mp3_bitrate not in (128, 192, 256, 320):
        raise AudioProcessingError("Unsupported MP3 bitrate.")
    if output_path.suffix.lower() == ".mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{effects.mp3_bitrate}k"]
    return ["-c:a", "pcm_s24le" if effects.bit_depth == 24 else "pcm_s16le"]


def _build_mix_filter(
    active: list[MixStem],
    start_seconds: float,
    duration_seconds: float,
    fade_in: float,
    fade_out: float,
    effects: AudioEffects,
    post_gain: float = 1.0,
    fade_bounds: tuple[float, float] | None = None,
    live_eq_filters: list[str] | None = None,
    live_mixer: bool = False,
) -> tuple[list[str], str]:
    input_args: list[str] = []
    for stem in active:
        local_start = start_seconds - stem.offset_seconds
        if local_start < -0.001:
            raise AudioProcessingError("The selection is outside the separated stem range. Separate the required range again.")
        input_args.extend(
            [
                "-ss",
                f"{max(local_start, 0):.6f}",
                "-t",
                f"{duration_seconds:.6f}",
                "-i",
                str(stem.path),
            ]
        )

    # Fades belong to the full selected source range, including when previewing
    # a later cursor position or a shortened fallback excerpt. Tempo is applied
    # afterward, so the waveform and these endpoints use the same source time.
    fade_start, fade_end = fade_bounds or (start_seconds, start_seconds + duration_seconds)
    if not all(math.isfinite(value) for value in (fade_start, fade_end)) or fade_end <= fade_start:
        raise AudioProcessingError("Fade bounds must describe a non-empty source range.")
    max_fade = (fade_end - fade_start) / 2
    fade_in = max(0.0, min(fade_in, max_fade))
    fade_out = max(0.0, min(fade_out, max_fade))
    fade_filters: list[str] = []
    if fade_in > 0 and start_seconds < fade_start + fade_in:
        elapsed = max(0.0, start_seconds - fade_start)
        remaining = fade_in - elapsed
        silence = elapsed / fade_in
        fade_filters.append(
            f"afade=t=in:st={max(0.0, fade_start - start_seconds):.6f}"
            f":d={remaining:.6f}:silence={silence:.9f}"
        )
    if fade_out > 0:
        remaining = max(0.0, fade_end - start_seconds)
        if remaining == 0:
            fade_filters.append("volume=0")
        else:
            fade_filters.append(
                f"afade=t=out:st={max(0.0, fade_end - fade_out - start_seconds):.6f}"
                f":d={min(fade_out, remaining):.6f}:unity={min(1.0, remaining / fade_out):.9f}"
            )
    filters: list[str] = []
    labels: list[str] = []
    for index, stem in enumerate(active):
        gain = 1.0 if live_mixer else stem.gain
        chain = f"[{index}:a]aresample={effects.sample_rate},volume={gain:.6f}"
        if fade_filters:
            chain += "," + ",".join(fade_filters)
        label = f"a{index}"
        chain += f"[{label}]"
        filters.append(chain)
        labels.append(f"[{label}]")

    # Use the same bounded blocks in preview and export, including Rubber Band.
    tail_filters = ["asetnsamples=n=256:p=0"]
    tail_filters.extend(_effect_filters(effects, keep_unity=True) if live_eq_filters is None else live_eq_filters)
    rubberband = build_rubberband_filter(effects.tempo_ratio, effects.pitch_semitones)
    if rubberband:
        tail_filters.append(rubberband)
    if post_gain < 0.9999 or post_gain > 1.0001:
        tail_filters.append(f"volume={post_gain:.6f}")
    if effects.limiter_enabled:
        tail_filters.append(f"alimiter=limit={_limiter_ceiling(effects):.6f}:level=false:latency=true")
    if not tail_filters:
        tail_filters.append("anull")

    if live_mixer:
        weights = " ".join(f"{v:.6f}" for v in _mix_weights(active))
        filters.append("".join(labels) + f"amix@kw_stems=inputs={len(labels)}:weights='{weights}'"
                       f":normalize=0:duration=first:dropout_transition=0,{','.join(tail_filters)}[outa]")
    elif len(labels) == 1:
        filters.append(f"{labels[0]}{','.join(tail_filters)}[outa]")
    else:
        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:duration=first,{','.join(tail_filters)}[outa]"
        )
    return input_args, ";".join(filters)


def _effect_filters(effects: AudioEffects, keep_unity: bool = False) -> list[str]:
    filters: list[str] = []
    for band in ("low", "mid", "high"):
        gain = getattr(effects, band + "_db")
        if keep_unity or abs(gain) >= .05:
            filters.append(_eq_filter(getattr(effects, band + "_shape"), getattr(effects, band + "_freq"),
                                      getattr(effects, band + "_q"), gain if abs(gain) >= .05 else 0))
    for key, name in (("high_pass", "highpass"), ("low_pass", "lowpass")):
        frequency = getattr(effects, key + "_hz")
        if frequency > 0:
            for q in pass_section_qs(getattr(effects, key + "_slope"), _clamp_q(getattr(effects, key + "_q"))):
                filters.append(f"{name}=f={_clamp_frequency(frequency):.3f}:t=q:w={q:.3f}:precision=f64")
    return filters


_LIVE_EQ_VALUES = frozenset(f"{band}_{field}" for band in ("low", "mid", "high")
                          for field in ("db", "freq", "q", "shape")) | {
    "high_pass_hz", "low_pass_hz", "high_pass_q", "low_pass_q", "high_pass_slope", "low_pass_slope"}


def _eq_restart_key(effects):
    """Only non-EQ processing needs the existing restart path."""
    return tuple(getattr(effects, field.name) for field in fields(effects)
                 if field.name not in _LIVE_EQ_VALUES)


def _live_eq_plan(effects):
    """Two fixed filter banks let an inaudible bank change topology safely."""
    filters, parameters = [], {}
    for band in ("low", "mid", "high"):
        gain = getattr(effects, band + "_db")
        selected = _eq_filter(getattr(effects, band + "_shape"), 1000, 1, 0).split("=", 1)[0]
        for name, shape in (("equalizer", "Bell"), ("bass", "Low Shelf"), ("treble", "High Shelf")):
            active = name == selected
            # Inactive alternatives use fixed values, so dragging a frequency
            # does not enqueue redundant commands to inaudible filters.
            text = _eq_filter(shape, getattr(effects, band + "_freq") if active else 1000,
                              getattr(effects, band + "_q") if active else 1,
                              gain if active and abs(gain) >= .05 else 0)
            options = text.split("=", 1)[1] + f":m={int(active)}"
            target = f"{name}@kw_{band}"
            filters.append((target, options))
            for option in options.split(":"):
                key, value = option.split("=")
                if key in ("f", "w", "g", "m"):
                    parameters[target, key] = float(value)
    for key, name in (("high_pass", "highpass"), ("low_pass", "lowpass")):
        frequency = getattr(effects, key + "_hz")
        sections = (pass_section_qs(getattr(effects, key + "_slope"), _clamp_q(getattr(effects, key + "_q")))
                    if frequency > 0 else ())
        for index in range(4):
            active = index < len(sections)
            target = f"{name}@kw_{key}_{index}"
            f = round(_clamp_frequency(frequency), 3) if active else 1000.
            w = round(sections[index], 3) if active else .707
            filters.append((target, f"f={f:.3f}:t=q:w={w:.3f}:precision=f64:m={int(active)}"))
            parameters[target, "f"], parameters[target, "w"], parameters[target, "m"] = f, w, float(active)
    branches = [",".join(f"{bank_target(target, bank)}={options}" for target, options in filters)
                for bank in range(2)]
    graph = ("asplit=2[kw_eq_a_in][kw_eq_b_in];"
             f"[kw_eq_a_in]{branches[0]}[kw_eq_a];"
             f"[kw_eq_b_in]{branches[1]}[kw_eq_b];"
             "[kw_eq_a][kw_eq_b]amix@kw_eq_crossfade=inputs=2:weights='1 0':normalize=0"
             ":duration=first:dropout_transition=0")
    return [graph], parameters


def _eq_filter(shape: str, frequency: float, q: float, gain_db: float) -> str:
    frequency = _clamp_frequency(frequency)
    q = _clamp_q(q)
    gain_db = _clamp_db(gain_db)
    shape_key = shape.strip().lower().replace(" ", "_")
    if shape_key == "low_shelf":
        return f"bass=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}:precision=f64"
    if shape_key == "high_shelf":
        return f"treble=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}:precision=f64"
    return f"equalizer=f={frequency:.3f}:t=q:w={q:.3f}:g={gain_db:.3f}:precision=f64"


def _clamp_db(value: float) -> float:
    return max(min(float(value), EQ_GAIN_LIMIT), -EQ_GAIN_LIMIT)


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
        filters.append(f"alimiter=limit={_limiter_ceiling(effects):.6f}:level=false:latency=true")
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-af",
        ",".join(filters),
        "-ar",
        str(effects.sample_rate),
        "-ac",
        "2",
        *_output_format_args(output_path, effects),
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
        process.stdout.close()
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
        process.stdout.close()
        if process_callback:
            process_callback(None)

    if _is_cancelled(cancel_event):
        raise OperationCancelled("Operation cancelled.")
    if exit_code != 0:
        tail = "\n".join(captured[-8:])
        raise AudioProcessingError(f"FFmpeg operation failed.\n{tail}")
