"""Real Demucs amplitude checks; run with the app-local Demucs Python."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--real-source", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()
    root, work = args.app_root.resolve(), args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    runner = root / "backend/demucs_runner.py"
    write_wav = runpy.run_path(str(runner))["write_float_wav"]
    env = {**os.environ, "TORCH_HOME": str(root / "models/torch"),
           "TEMP": str(work), "TMP": str(work),
           "PATH": str(root / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")}
    names = ("vocals", "drums", "bass", "other")
    report = {"app_root": str(root), "shifts_for_gain_check": 0,
              "listening_tested": False, "runs": {}}

    def run(label, command):
        started = time.monotonic()
        with (args.evidence_dir / f"{label}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=root, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=1800,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        report["runs"][label] = {"exit_code": completed.returncode,
                                 "seconds": round(time.monotonic() - started, 3)}
        assert completed.returncode == 0, label
        print(f"{label}: {report['runs'][label]}", flush=True)

    def split(label, source, shifts=0, legacy=False):
        output = work / label
        prefix = ["-m", "demucs"] if legacy else [str(runner)]
        run(label, [sys.executable, "-I", "-B", *prefix, "--name", "htdemucs",
                    "--out", str(output), "--jobs", "2", "--shifts", str(shifts),
                    "--overlap", "0.25", str(source)])
        return {name: next(output.rglob(f"{name}.wav")) for name in names}

    def decode(path):
        result = subprocess.run([str(root / "bin/ffmpeg.exe"), "-v", "error", "-i", str(path),
                                 "-ar", "44100", "-ac", "2", "-c:a", "pcm_f32le", "-f", "f32le", "-"],
                                env=env, capture_output=True, check=True, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2).astype(np.float64)

    def relative_db(error, reference):
        return float(10 * np.log10(max(float(np.sum(error ** 2)), 1e-30)
                                  / max(float(np.sum(reference ** 2)), 1e-30)))

    rate = 44100
    t = np.arange(rate * 4) / rate
    left = np.sin(2 * np.pi * 80 * t) + .3 * np.sin(2 * np.pi * 440 * t)
    right = .85 * np.sin(2 * np.pi * 80 * t) + .2 * np.sin(2 * np.pi * 660 * t)
    audio = np.stack((left, right), axis=1)
    audio = (audio * (2 / np.max(np.abs(audio)))).astype("<f4")
    high, low = work / "high.wav", work / "low.wav"
    write_wav(high, audio.tobytes(), rate, 2)
    write_wav(low, (audio / 16).astype("<f4").tobytes(), rate, 2)
    loud_stems = split("high", high)
    quiet_stems = split("low", low)
    old_stems = split("legacy-high", high, legacy=True)
    report["gain_check"] = {}
    for name in names:
        loud, quiet, old = (decode(items[name]) for items in (loud_stems, quiet_stems, old_stems))
        assert loud.shape == quiet.shape == old.shape == audio.shape
        assert np.isfinite(loud).all()
        error = relative_db(loud - quiet * 16, loud)
        peak = float(np.max(np.abs(loud)))
        scale = max(1.01 * peak, 1.0)
        # Legacy writer scales, truncates to int16 and divides by 32768 on read.
        predicted_old = np.trunc(loud / scale * 32767) / 32768
        old_error = float(np.max(np.abs(old - predicted_old)))
        report["gain_check"][name] = {
            "new_peak": peak, "old_peak": float(np.max(np.abs(old))),
            "scale_equivariance_error_db": error,
            "legacy_rescale_max_sample_error": old_error,
            "legacy_attenuation_db": float(20 * np.log10(scale)),
            "frames": len(loud),
        }
        assert error < -60, (name, error)
        assert old_error < 0.0002, (name, old_error)
        probe = subprocess.run([str(root / "bin/ffprobe.exe"), "-v", "error", "-show_streams",
                                "-of", "json", str(loud_stems[name])], capture_output=True,
                               check=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        stream = json.loads(probe.stdout)["streams"][0]
        assert stream["codec_name"] == "pcm_f32le"
        assert stream["channels"] == 2 and stream["sample_rate"] == "44100"
    assert any(item["new_peak"] > 1.05 for item in report["gain_check"].values())

    # Exercise normalization guards with the actual Torch/runtime types, without
    # repeating expensive model inference for each pathological input.
    import torch
    from types import SimpleNamespace
    from unittest.mock import patch
    model = SimpleNamespace(audio_channels=2, samplerate=rate, sources=names,
                            cpu=lambda: None, eval=lambda: None)
    cases = {"silence": torch.zeros(2, 32), "one_frame": torch.zeros(2, 1),
             "dc": torch.full((2, 32), .25),
             "antiphase": torch.tensor([[.1, -.1] * 16, [-.1, .1] * 16])}
    report["normalization_guards"] = []
    separate = runpy.run_path(str(runner))["separate"]

    def inference(model, wav, **kwargs):
        assert torch.isfinite(wav).all()
        return wav[:, None].repeat(1, 4, 1, 1) / 4

    with patch("demucs.pretrained.get_model", return_value=model), \
            patch("demucs.apply.apply_model", side_effect=inference):
        for label, wav in cases.items():
            with patch("demucs.separate.load_track", return_value=wav):
                separate(high, work / label)
            assert all(np.isfinite(decode(work / label / f"{name}.wav")).all() for name in names)
            report["normalization_guards"].append(label)
        for label, wav in {"empty": torch.zeros(2, 0), "nan": torch.full((2, 8), float("nan"))}.items():
            with patch("demucs.separate.load_track", return_value=wav):
                try:
                    separate(high, work / label)
                except ValueError:
                    report["normalization_guards"].append(f"{label}_rejected")
                else:
                    raise AssertionError(label)

    if args.real_source:
        new_stems = split("real-track", args.real_source.resolve(), shifts=1)
        source = decode(args.real_source)

        def metrics(stems):
            tracks = [decode(stems[name]) for name in names]
            assert all(track.shape == source.shape for track in tracks)
            matrix = np.stack([track.ravel() for track in tracks], axis=1)
            # Small normal equation avoids an additional full-track LAPACK copy.
            gains = np.linalg.solve(matrix.T @ matrix, matrix.T @ source.ravel())
            return {"frames": len(source), "peaks": {name: float(np.max(np.abs(track)))
                    for name, track in zip(names, tracks)},
                    "least_squares_gains": dict(zip(names, map(float, gains))),
                    "sum_residual_db": relative_db(sum(tracks) - source, source)}

        report["real_track_new"] = metrics(new_stems)
        if args.reference_dir:
            report["real_track_historical"] = metrics(
                {name: next(args.reference_dir.rglob(f"{name}.wav")) for name in names})
        report["real_track_note"] = "Historical shifts differ; least-squares metrics are diagnostic, not ground truth."

    (args.evidence_dir / "runtime.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
