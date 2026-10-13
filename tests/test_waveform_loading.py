"""Peak fidelity, channel independence and cancellation for float working audio."""
from array import array
import math
from threading import Event
from unittest.mock import Mock

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import OperationCancelled, stereo_waveform_peaks
from backend.demucs_runner import write_float_wav


@pytest.mark.parametrize("count", [7, 4096, 40000])
def test_float_peaks_preserve_full_bandwidth_channels_and_bucket_edges(tmp_path, count):
    frames = 30000  # Buckets and pipe chunks use different boundaries.
    values = array("f")
    for i in range(frames):
        left = 1.8 * math.sin(2 * math.pi * 18000 * i / 48000)
        right = -.125 * math.sin(2 * math.pi * 9000 * i / 48000)
        values.extend((left, right))
    values[16382] = -2.25
    values[16385] = .75
    source = tmp_path / "floating.wav"
    write_float_wav(source, values.tobytes(), 48000, 2)
    peaks = stereo_waveform_peaks(AppPaths(tmp_path), source, count)
    bucket_size = math.ceil(frames / count)
    expected = [(max((abs(value) for value in values[2*a:2*b:2]), default=0),
                 max((abs(value) for value in values[2*a+1:2*b:2]), default=0))
                for a, b in ((i*bucket_size, min((i+1)*bucket_size, frames)) for i in range(count))]
    assert peaks == expected
    assert max(left for left, right in peaks) == 2.25
    assert max(right for left, right in peaks) == .75


def test_cancelled_waveform_does_not_probe_or_launch_ffmpeg(tmp_path, monkeypatch):
    event = Event()
    event.set()
    source = tmp_path / "floating.wav"
    write_float_wav(source, bytes(32), 48000, 2)
    launched = Mock(side_effect=AssertionError("A cancelled job launched a process"))
    monkeypatch.setattr("backend.audio_processing.ffmpeg_tools.subprocess.Popen", launched)
    with pytest.raises(OperationCancelled):
        stereo_waveform_peaks(AppPaths(tmp_path), source, cancel_event=event)
    launched.assert_not_called()


def test_cancellation_releases_owned_waveform_process(tmp_path):
    source = tmp_path / "floating.wav"
    write_float_wav(source, bytes(48000 * 8), 48000, 2)
    event = Event()
    processes = []

    def registered(process):
        processes.append(process)
        if process is not None:
            event.set()

    with pytest.raises(OperationCancelled):
        stereo_waveform_peaks(AppPaths(tmp_path), source, cancel_event=event,
                              process_callback=registered)
    assert processes[-1] is None and processes[0].poll() is not None
