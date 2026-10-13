"""Unscaled float stems, runtime routing and existing playback/export contracts."""
from array import array
from dataclasses import replace
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
from threading import Event
from unittest.mock import Mock

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing import STEMS
from backend.audio_processing.ffmpeg_tools import (
    AudioEffects, AudioProcessingError, MixStem, OperationCancelled,
    read_duration, render_mix, require_ffmpeg, start_realtime_mix,
)
from backend.audio_processing.separation import StemSeparator
from backend.demucs_runner import write_float_wav


ROOT = Path(__file__).resolve().parents[1]


def decode(paths, path):
    completed = subprocess.run(
        [str(require_ffmpeg(paths)), "-v", "error", "-i", str(path),
         "-f", "f32le", "-c:a", "pcm_f32le", "-"],
        check=True, capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    samples = array("f")
    samples.frombytes(completed.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


@pytest.mark.parametrize("samplerate,channels", [(44100, 2), (48000, 1)])
def test_float_wav_preserves_over_unity_samples_and_frame_count(tmp_path, samplerate, channels):
    path = tmp_path / "raw stem.wav"
    values = [-2.0, 1.75, 0.125, -0.25, 0.0, 0.999]
    pcm = struct.pack("<6f", *values)
    write_float_wav(path, pcm, samplerate, channels)
    contents = path.read_bytes()
    assert contents[:4] == b"RIFF" and contents[8:12] == b"WAVE"
    assert struct.unpack_from("<I", contents, 4)[0] == len(contents) - 8
    assert struct.unpack_from("<H", contents, 20)[0] == 3
    assert contents[38:42] == b"fact"
    assert struct.unpack_from("<I", contents, 46)[0] == len(values) // channels
    assert contents[58:] == pcm
    result = subprocess.run(
        [str(ROOT / "bin/ffprobe.exe"), "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, check=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    stream = json.loads(result.stdout)["streams"][0]
    assert stream["codec_name"] == "pcm_f32le"
    assert int(stream["sample_rate"]) == samplerate and stream["channels"] == channels
    assert list(decode(AppPaths(ROOT), path)) == list(struct.unpack("<6f", pcm))


@pytest.mark.parametrize("pcm,rate,channels", [(b"123", 44100, 2), (b"", 0, 2), (b"", 44100, 0)])
def test_float_wav_rejects_invalid_frames_before_writing(tmp_path, pcm, rate, channels):
    path = tmp_path / "invalid.wav"
    with pytest.raises(ValueError):
        write_float_wav(path, pcm, rate, channels)
    assert not path.exists()


@pytest.mark.parametrize("runtime", ["portable", "venv", "current", "local-cli", "path-cli", "missing"])
def test_runtime_selection_uses_isolated_runner_when_python_is_available(tmp_path, monkeypatch, runtime):
    paths = AppPaths(tmp_path)
    python = paths.backend / "demucs_runtime" / ("Scripts/python.exe" if runtime == "venv" else "python.exe")
    if runtime in ("portable", "venv"):
        python.parent.mkdir(parents=True)
        python.touch()
        if runtime == "venv":
            (python.parents[1] / "pyvenv.cfg").write_text("executable = python.exe\n")
    if runtime == "local-cli":
        paths.bin.mkdir()
        (paths.bin / "demucs.exe").touch()
    monkeypatch.setattr("backend.audio_processing.separation.shutil.which",
                        lambda name: "external-demucs.exe" if runtime == "path-cli" else None)
    monkeypatch.setattr("backend.audio_processing.separation.importlib.util.find_spec",
                        lambda name: object() if runtime == "current" else None)
    monkeypatch.setattr("backend.audio_processing.separation.subprocess.run",
                        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0))
    command = StemSeparator(paths).available_command()
    if runtime in ("portable", "venv", "current"):
        assert command == [sys.executable if runtime == "current" else str(python),
                           "-I", "-B", str(paths.backend / "demucs_runner.py")]
    elif runtime == "local-cli":
        assert command == [str(paths.bin / "demucs.exe")]
    elif runtime == "path-cli":
        assert command == ["external-demucs.exe"]
    else:
        assert command is None


@pytest.mark.parametrize("frozen", [True, False])
def test_current_python_fallback_rejects_nonisolated_or_frozen_runtime(tmp_path, monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr("backend.audio_processing.separation.shutil.which", lambda name: None)
    monkeypatch.setattr("backend.audio_processing.separation.importlib.util.find_spec", lambda name: object())
    check = Mock(return_value=subprocess.CompletedProcess([], 1))
    monkeypatch.setattr("backend.audio_processing.separation.subprocess.run", check)
    assert StemSeparator(AppPaths(tmp_path)).available_command() is None
    if frozen:
        check.assert_not_called()
    else:
        assert check.call_args.args[0][1:3] == ["-I", "-B"]


@pytest.mark.parametrize("runner", [True, False])
def test_separation_preserves_progress_paths_and_cli_fallback(tmp_path, monkeypatch, runner):
    paths = AppPaths(tmp_path)
    separator = StemSeparator(paths)
    prefix = ([sys.executable, "-I", "-B", str(paths.backend / "demucs_runner.py")]
              if runner else ["external-demucs.exe"])
    monkeypatch.setattr(separator, "available_command", lambda: prefix)
    monkeypatch.setattr(separator, "_default_jobs", lambda: 2)
    process = Mock(stdout=io.StringIO("Running\r 50%|test\r 100%|test\n"))
    process.wait.return_value = 0

    def launch(command, **kwargs):
        output = Path(command[command.index("--out") + 1])
        for stem in STEMS:
            (output / f"{stem}.wav").touch()
        assert command[-1] == str(tmp_path / "input.wav")
        assert command[command.index("--name") + 1] == "htdemucs"
        assert command[command.index("--jobs") + 1] == "2"
        assert kwargs["cwd"] == str(tmp_path)
        assert kwargs["env"]["TORCH_HOME"] == str(paths.models / "torch")
        if runner:
            assert command[command.index("--shifts") + 1] == "1"
            assert command[command.index("--overlap") + 1] == "0.25"
        else:
            assert "--shifts" not in command and "--overlap" not in command
        return process

    monkeypatch.setattr("backend.audio_processing.separation.subprocess.Popen", launch)
    logs, progress, processes = [], [], []
    result = separator.separate(tmp_path / "input.wav", "job", logs.append,
                                progress.append, process_callback=processes.append)
    assert set(result) == set(STEMS)
    assert progress == [50.0, 100.0, 100.0]
    assert processes == [process, None] and process.stdout.closed
    assert any(("original levels" if runner else "CLI fallback") in line for line in logs)


@pytest.mark.parametrize("cancel", [True, False])
def test_runner_cancel_and_failure_keep_existing_process_contract(tmp_path, monkeypatch, cancel):
    separator = StemSeparator(AppPaths(tmp_path))
    monkeypatch.setattr(separator, "available_command", lambda: ["test-runner"])
    event = Event()
    process = Mock(stdout=io.StringIO("diagnostic\nmodel failed\n"))
    process.wait.return_value = 1
    process.poll.return_value = None
    monkeypatch.setattr("backend.audio_processing.separation.subprocess.Popen", lambda *a, **kw: process)
    callbacks = []

    def process_changed(child):
        callbacks.append(child)
        if cancel and child:
            event.set()

    with pytest.raises(OperationCancelled if cancel else AudioProcessingError,
                       match="cancelled" if cancel else "model failed"):
        separator.separate(tmp_path / "input.wav", "job", cancel_event=event,
                           process_callback=process_changed)
    assert callbacks == [process, None] and process.stdout.closed
    assert process.terminate.called == cancel


def test_over_unity_stems_keep_mix_balance_and_existing_export_limiter(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    paths = AppPaths(tmp_path)
    paths.ensure()
    rate = 44100
    count = rate * 2
    items = []
    for name, amplitude in zip(STEMS, (2.0, 0.25, 0.5, 0.125)):
        values = array("f", (amplitude * math.sin(2 * math.pi * 440 * (i // 2) / rate)
                             for i in range(count * 2)))
        if sys.byteorder != "little":
            values.byteswap()
        path = tmp_path / f"{name}.wav"
        write_float_wav(path, values.tobytes(), rate, 2)
        items.append(MixStem(name, path, 0.125))
    unlimited = AudioEffects(limiter_enabled=False, sample_rate=rate, bit_depth=24)
    mixed = paths.output / "mix.wav"
    render_mix(paths, items, mixed, 0, 2, 0, 0, effects=unlimited)
    samples = decode(paths, mixed)
    assert max(map(abs, samples)) == pytest.approx(2.875 * 0.125, abs=0.0001)
    levels = []
    for item in items:
        output = paths.output / f"{item.name}.wav"
        render_mix(paths, [item], output, 0, 2, 0, 0, effects=unlimited)
        levels.append(max(map(abs, decode(paths, output))))
    assert levels[0] / levels[1] == pytest.approx(8, abs=0.01)

    loud_solo = [replace(items[0], gain=1.0), *(replace(item, gain=0.0) for item in items[1:])]
    limited = replace(unlimited, limiter_enabled=True)
    for extension in ("wav", "mp3"):
        output = paths.output / f"limited.{extension}"
        render_mix(paths, loud_solo, output, 0, 2, 0, 0, effects=limited)
        assert read_duration(paths, output) == pytest.approx(2, abs=0.1)
        decoded = decode(paths, output)
        assert all(math.isfinite(value) for value in decoded)
        # Lossy reconstruction may overshoot slightly; WAV obeys the ceiling.
        assert 0.9 < max(map(abs, decoded)) < (0.981 if extension == "wav" else 1.05)

    playback = start_realtime_mix(paths, loud_solo, 0, 2, 0, 0, limited)
    try:
        from test_spectrum import wait_for
        assert wait_for(lambda: playback.spectrum_frame())
        assert not playback.error and not playback.eq_controller.error
    finally:
        playback.close()
