from __future__ import annotations

import sys
from pathlib import Path


HELPER = '''

# KWAK Split portable WAV writer patch.
def _save_wav_portable(wav: torch.Tensor,
                       path: tp.Union[str, Path],
                       samplerate: int,
                       bits_per_sample: int,
                       as_float: bool) -> None:
    import wave
    import numpy as np

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = wav.detach().cpu()
    if data.dim() != 2:
        raise ValueError("Expected audio tensor shaped as channels x samples.")
    data = data.transpose(0, 1).contiguous().numpy()
    channels = data.shape[1]

    if as_float:
        bits_per_sample = 32
    if bits_per_sample not in (16, 32):
        bits_per_sample = 16

    clipped = np.clip(data, -1.0, 1.0)
    if bits_per_sample == 32:
        pcm = (clipped * 2147483647.0).astype("<i4")
        sample_width = 4
    else:
        pcm = (clipped * 32767.0).astype("<i2")
        sample_width = 2

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(samplerate)
        handle.writeframes(pcm.tobytes())
'''


OLD_BLOCK = '''    elif suffix == ".wav":
        if as_float:
            bits_per_sample = 32
            encoding = 'PCM_F'
        else:
            encoding = 'PCM_S'
        ta.save(str(path), wav, sample_rate=samplerate,
                encoding=encoding, bits_per_sample=bits_per_sample)
'''

NEW_BLOCK = '''    elif suffix == ".wav":
        _save_wav_portable(wav, path, samplerate, bits_per_sample, as_float)
'''


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_demucs_audio.py <demucs_runtime_dir>", file=sys.stderr)
        return 2

    runtime = Path(sys.argv[1]).resolve()
    audio_py = runtime / "Lib" / "site-packages" / "demucs" / "audio.py"
    if not audio_py.exists():
        print(f"Could not find {audio_py}", file=sys.stderr)
        return 1

    text = audio_py.read_text(encoding="utf-8")
    if "_save_wav_portable" not in text:
        text = text.replace("\ndef save_audio(", HELPER + "\n\ndef save_audio(", 1)
    if OLD_BLOCK in text:
        text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    elif NEW_BLOCK not in text:
        print("Could not locate Demucs WAV save block.", file=sys.stderr)
        return 1

    audio_py.write_text(text, encoding="utf-8")
    print(f"Patched {audio_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
