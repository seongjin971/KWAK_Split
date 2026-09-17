"""Optional FFmpeg/FFplay integration checks with silent SDL output.

Run with: python -B -m unittest discover -s tests -p test_playback_audio.py -v
No sound is sent to the user's speakers; test media stays under temp/.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from StemSamplePrep import StemSamplePrepApp
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, read_duration, render_mix
from test_playback import playback_app


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffplay"), "FFmpeg and FFplay must be on PATH")
class PlaybackAudioTests(unittest.TestCase):
    def test_tempo_preview_with_real_processes_and_rendered_files(self):
        with tempfile.TemporaryDirectory(prefix="playback-audio-", dir=Path(__file__).resolve().parents[1] / "temp") as folder:
            paths = AppPaths(Path(folder))
            paths.ensure()
            source = paths.temp / "source.wav"
            subprocess.run(
                [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "sine=frequency=440:sample_rate=44100:duration=12",
                 "-af", "volume=0.1", "-ac", "2", str(source)],
                check=True, capture_output=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for speed in (0.5, 1.0, 2.0):
                with self.subTest(speed=speed), patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}):
                    effects = AudioEffects(tempo_ratio=speed)
                    stems = [MixStem("source", source, 1.0)]
                    rendered = paths.output / f"speed_{speed}.wav"
                    render_mix(paths, stems, rendered, 5.0, 4.0, 0.0, 0.0, effects=effects)
                    measured = read_duration(paths, rendered)
                    self.assertAlmostEqual(measured, 4.0 / speed, delta=0.5)

                    app = playback_app(speed, source_start=5.0, source_duration=4.0)
                    app.paths = paths
                    app.preview_playing = False
                    app.playback_started_at = None
                    app.realtime_processes = []
                    # Exercise the production cleanup method against real children.
                    app._stop_realtime_playback = lambda: StemSamplePrepApp._stop_realtime_playback(app)
                    with patch("StemSamplePrep.winsound.PlaySound"):
                        StemSamplePrepApp._start_preview(app, stems, "Source")
                    processes = list(app.realtime_processes)
                    started = time.monotonic()
                    checked_slow_midpoint = False
                    try:
                        while app.preview_playing and time.monotonic() - started < 20.0:
                            elapsed = time.monotonic() - started
                            app._update_playback_position()
                            if speed == 0.5 and 4.1 < elapsed < 5.0:
                                self.assertTrue(app.preview_playing, "Half-speed preview stopped at source duration")
                                self.assertIsNone(processes[0].poll())
                                checked_slow_midpoint = True
                            time.sleep(0.05)
                        elapsed = time.monotonic() - started
                        self.assertFalse(app.preview_playing, "Preview failed to finish")
                        self.assertTrue(all(process.poll() == 0 for process in processes))
                        self.assertGreaterEqual(elapsed, measured - 0.3)
                        app._set_playback_position.assert_called_with(9.0)
                        app.status_var.set.assert_called_with("Playback finished.")
                        if speed == 0.5:
                            self.assertTrue(checked_slow_midpoint)
                        if speed == 2.0:
                            self.assertLess(elapsed, 4.0, "Double-speed preview stayed active for source duration")
                        print(f"\nSpeed {speed * 100:.0f}%: source 5..9s, WAV {measured:.3f}s, "
                              f"player {elapsed:.3f}s, final cursor 9s", flush=True)
                    finally:
                        StemSamplePrepApp._stop_realtime_playback(app)


if __name__ == "__main__":
    unittest.main()
