"""Run inside the Demucs Python runtime; preserve raw stem levels in float WAVs.

This file is shipped beside the runtime, not imported by the desktop app.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct


def write_float_wav(path: Path, pcm: bytes, samplerate: int, channels: int) -> None:
    """Write interleaved little-endian float32 PCM, including peaks above 1.0."""
    if samplerate <= 0 or channels <= 0 or len(pcm) % (channels * 4):
        raise ValueError("Invalid float PCM format or incomplete audio frame.")
    frames = len(pcm) // (channels * 4)
    # WAVEFORMATEX (IEEE_FLOAT), sample count, then unmodified sample bytes.
    fmt = struct.pack("<HHIIHHH", 3, channels, samplerate,
                      samplerate * channels * 4, channels * 4, 32, 0)
    riff_size = 4 + 8 + len(fmt) + 12 + 8 + len(pcm)
    if riff_size > 0xFFFFFFFF:
        raise ValueError("Stem exceeds the 4 GiB RIFF WAV size limit.")
    with Path(path).open("wb") as handle:
        handle.write(struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE"))
        handle.write(struct.pack("<4sI", b"fmt ", len(fmt)))
        handle.write(fmt)
        handle.write(struct.pack("<4sII", b"fact", 4, frames))
        handle.write(struct.pack("<4sI", b"data", len(pcm)))
        handle.write(pcm)


def separate(source: Path, out: Path, *, name: str = "htdemucs",
             shifts: int = 1, overlap: float = 0.25, jobs: int = 0) -> None:
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from demucs.separate import load_track

    model = get_model(name)
    model.cpu()
    model.eval()
    wav = load_track(source, model.audio_channels, model.samplerate)
    if wav.ndim != 2 or wav.shape[-1] == 0 or not torch.isfinite(wav).all():
        raise ValueError("Input audio is empty or contains non-finite samples.")

    # Match Demucs normalization and restore its original scale after inference.
    ref = wav.mean(0)
    mean = ref.mean()
    scale = ref.std() if ref.numel() > 1 else ref.new_tensor(0.0)
    if not torch.isfinite(scale) or scale <= 0:
        # Antiphase stereo can have a silent channel average. Silence, DC and
        # single-frame inputs must not divide by zero either.
        scale = wav.std() if wav.numel() > 1 else wav.new_tensor(0.0)
        if not torch.isfinite(scale) or scale <= 0:
            scale = wav.new_tensor(1.0)
    wav = (wav - mean) / scale
    print(f"Separating {source} (float32 stems, original levels)", flush=True)
    sources = apply_model(
        model, wav[None], device="cuda" if torch.cuda.is_available() else "cpu",
        shifts=shifts, split=True, overlap=overlap, progress=True, num_workers=jobs,
    )[0]
    sources = sources * scale + mean
    if not torch.isfinite(sources).all():
        raise ValueError("Demucs produced non-finite audio samples.")

    out.mkdir(parents=True, exist_ok=True)
    for stem, stem_name in zip(sources, model.sources):
        pcm = stem.detach().cpu().t().contiguous().numpy().astype("<f4", copy=False).tobytes()
        write_float_wav(out / f"{stem_name}.wav", pcm, model.samplerate, model.audio_channels)
    print("Float32 stems saved without clipping or per-stem rescaling.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--name", default="htdemucs")
    parser.add_argument("--shifts", type=int, default=1)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--jobs", type=int, default=0)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"Input file not found: {args.source}")
    if args.shifts < 0 or not 0 <= args.overlap < 1 or args.jobs < 0:
        parser.error("Require shifts >= 0, 0 <= overlap < 1 and jobs >= 0.")
    separate(args.source, args.out, name=args.name, shifts=args.shifts,
             overlap=args.overlap, jobs=args.jobs)


if __name__ == "__main__":
    main()
