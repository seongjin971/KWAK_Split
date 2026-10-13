"""Playback regressions without opening a window or using an audio device.

Run with: python -B -m unittest discover -s tests -p test_playback.py -v
"""

import queue
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem


def playback_app(speed=1.0, source_start=10.0, source_duration=12.0):
    app = SimpleNamespace(
        paths=Mock(),
        playback_started_at=100.0,
        playback_start_seconds=source_start,
        playback_duration_seconds=source_duration,
        playback_tempo_ratio=speed,
        playback_output_duration_seconds=source_duration / speed,
        playback_position_var=Mock(),
        playback_cursor_manual=False,
        preview_playing=True,
        current_preview_file=None,
        realtime_processes=[Mock(poll=Mock(return_value=None)), Mock(poll=Mock(return_value=0))],
        playback_seek_dragging=False,
        status_var=Mock(),
        append_log=Mock(),
        _refresh_action_states=Mock(),
        _cancel_live_preview_restart=Mock(),
        _stop_realtime_playback=Mock(),
        _set_playback_position=Mock(),
        fade_in_var=Mock(get=Mock(return_value=0.0)),
        fade_out_var=Mock(get=Mock(return_value=0.0)),
        _playback_bounds=Mock(return_value=(source_start, source_start + source_duration)),
        _selection_bounds=Mock(return_value=(source_start, source_start + source_duration)),
        _infer_preview_mode=Mock(return_value=("source", None)),
        _build_audio_effects=Mock(return_value=AudioEffects(tempo_ratio=speed)),
    )
    app._update_playback_position = MethodType(StemSamplePrepApp._update_playback_position, app)
    app.stop_preview = MethodType(StemSamplePrepApp.stop_preview, app)
    return app


def advance(app, seconds):
    with patch("StemSamplePrep.time.monotonic", return_value=100.0 + seconds):
        app._update_playback_position()


class PlaybackTests(unittest.TestCase):
    def test_cursor_maps_wall_time_to_original_audio_at_each_speed(self):
        for speed, expected in ((0.5, 12.0), (1.0, 14.0), (2.0, 18.0)):
            with self.subTest(speed=speed):
                app = playback_app(speed)
                advance(app, 4.0)
                app._set_playback_position.assert_called_with(expected)
                self.assertTrue(app.preview_playing)

    def test_half_speed_does_not_stop_at_original_duration(self):
        app = playback_app(0.5)
        advance(app, 12.0)
        self.assertTrue(app.preview_playing)
        app._stop_realtime_playback.assert_not_called()
        app._set_playback_position.assert_called_with(16.0)

    def test_realtime_output_tail_is_not_cut_at_estimated_end(self):
        app = playback_app(0.5)
        advance(app, 24.2)
        self.assertTrue(app.preview_playing)
        app._stop_realtime_playback.assert_not_called()
        app._set_playback_position.assert_called_with(22.0)

    def test_double_speed_finishes_when_player_finishes(self):
        app = playback_app(2.0)
        app.realtime_processes[0].poll.return_value = 0
        advance(app, 6.1)
        self.assertFalse(app.preview_playing)
        self.assertIsNone(app.playback_started_at)
        app._set_playback_position.assert_called_with(22.0)
        app.status_var.set.assert_called_with("Playback finished.")

    def test_encoder_exit_does_not_end_buffered_playback(self):
        app = playback_app(0.5)
        advance(app, 18.0)
        self.assertTrue(app.preview_playing)
        app._stop_realtime_playback.assert_not_called()

    def test_failed_player_does_not_report_success(self):
        app = playback_app()
        app.realtime_processes[0].poll.return_value = 1
        advance(app, 0.5)
        self.assertFalse(app.preview_playing)
        self.assertIn("failed", app.status_var.set.call_args.args[0].lower())
        app._set_playback_position.assert_called_with(10.5)

    def test_failed_encoder_is_not_reported_as_successful_playback(self):
        app = playback_app()
        app.realtime_processes[0].poll.return_value = 0
        app.realtime_processes[1].poll.return_value = 1
        advance(app, 0.5)
        self.assertFalse(app.preview_playing)
        self.assertIn("failed", app.status_var.set.call_args.args[0].lower())

    def test_rendered_preview_uses_measured_output_duration(self):
        app = playback_app(0.5)
        app.realtime_processes = []
        app.current_preview_file = Path("preview.wav")
        app.playback_output_duration_seconds = 24.3
        advance(app, 12.0)
        self.assertTrue(app.preview_playing)
        advance(app, 24.2)
        self.assertTrue(app.preview_playing)
        advance(app, 24.4)
        self.assertFalse(app.preview_playing)
        app._set_playback_position.assert_called_with(22.0)

    def test_rendered_double_speed_finishes_after_six_seconds(self):
        app = playback_app(2.0)
        app.realtime_processes = []
        app.current_preview_file = Path("preview.wav")
        advance(app, 6.1)
        self.assertFalse(app.preview_playing)

    def test_stop_captures_position_using_speed_of_active_audio(self):
        app = playback_app(0.5)
        # UI may already show a newly entered speed before preview restarts.
        app.tempo_percent_var = Mock(get=Mock(return_value=200.0))
        with patch("StemSamplePrep.time.monotonic", return_value=104.0), patch("StemSamplePrep.winsound.PlaySound"):
            app.stop_preview()
        app._set_playback_position.assert_called_with(12.0)
        self.assertFalse(app.preview_playing)
        self.assertTrue(app.playback_cursor_manual)

    def test_realtime_start_captures_effect_speed(self):
        app = playback_app(0.5)
        app.playback_started_at = None
        app.preview_playing = False
        app.playback_tempo_ratio = 1.0
        app.playback_output_duration_seconds = 0.0
        processes = [Mock(poll=Mock(return_value=None)), Mock(poll=Mock(return_value=None))]
        with patch("StemSamplePrep.time.monotonic", return_value=100.0), \
                patch("StemSamplePrep.start_realtime_mix", return_value=processes) as start_mix, \
                patch("StemSamplePrep.winsound.PlaySound"):
            StemSamplePrepApp._start_preview(app, [MixStem("source", Path("source.wav"), 1.0)], "Source")
        self.assertEqual(app.playback_tempo_ratio, 0.5)
        self.assertEqual(app.playback_output_duration_seconds, 24.0)
        self.assertEqual(app.playback_duration_seconds, 12.0)
        self.assertEqual(start_mix.call_args.kwargs["fade_bounds"], (10.0, 22.0))

    def test_rendered_preview_receives_captured_speed_and_measured_duration(self):
        app = playback_app()
        app.preview_playing = False
        payload = {"path": "preview.wav", "start": 10.0, "duration": 12.0,
                   "output_duration": 24.3, "tempo_ratio": 0.5, "label": "Source"}
        with patch("StemSamplePrep.winsound.PlaySound"), patch("StemSamplePrep.time.monotonic", return_value=100.0), \
                patch("StemSamplePrep.analyze_rendered_preview"):
            StemSamplePrepApp._handle_preview_ready(app, payload)
        self.assertEqual(app.playback_tempo_ratio, 0.5)
        self.assertEqual(app.playback_output_duration_seconds, 24.3)
        self.assertEqual(app.playback_duration_seconds, 12.0)

    def test_render_worker_measures_wav_before_publishing_preview(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="playback-test-", dir=Path(__file__).resolve().parents[1] / "temp") as folder:
            app = playback_app(0.5)
            app.paths = SimpleNamespace(temp=Path(folder))
            app._delete_old_previews = Mock()
            app._queue_status = Mock()
            app._register_process = Mock()
            app.cancel_event = None
            app.worker_queue = queue.Queue()
            app._run_worker = lambda _title, worker: worker()
            with patch("StemSamplePrep.render_mix"), patch("StemSamplePrep.read_duration", return_value=24.3) as measure:
                StemSamplePrepApp._start_rendered_preview(
                    app, [MixStem("source", Path("source.wav"), 1.0)], "Source",
                    10.0, 12.0, 0.0, 0.0, AudioEffects(tempo_ratio=0.5),
                )
            measure.assert_called_once()
            kind, payload = app.worker_queue.get_nowait()
            self.assertEqual(kind, "preview_ready")
            self.assertEqual(payload["output_duration"], 24.3)
            self.assertEqual(payload["tempo_ratio"], 0.5)

    def test_seek_restart_preserves_explicit_source_position(self):
        app = playback_app(0.5)
        cursor = [18.0]
        app.playback_position_var.get.side_effect = lambda: cursor[0]
        app._set_playback_position.side_effect = lambda value: cursor.__setitem__(0, value)
        app._build_last_preview_request = Mock(return_value=([], "Source"))
        app.last_preview_mode = "source"
        app.last_preview_stem = None
        app._start_preview = Mock()
        with patch("StemSamplePrep.time.monotonic", return_value=104.0), patch("StemSamplePrep.winsound.PlaySound"):
            StemSamplePrepApp._restart_preview_from_cursor(app)
        self.assertEqual(cursor[0], 18.0)
        self.assertTrue(app.playback_cursor_manual)
        app._start_preview.assert_called_once()

    def test_live_speed_restart_uses_updated_source_position(self):
        app = playback_app(0.5)
        cursor = [10.0]
        app.playback_position_var.get.side_effect = lambda: cursor[0]
        app._set_playback_position.side_effect = lambda value: cursor.__setitem__(0, value)
        app._build_last_preview_request = Mock(return_value=([], "Source"))
        app.last_preview_mode = "source"
        app.last_preview_stem = None
        app._start_preview = Mock()
        with patch("StemSamplePrep.time.monotonic", return_value=104.0), patch("StemSamplePrep.winsound.PlaySound"):
            StemSamplePrepApp._restart_preview_silent(app)
        self.assertEqual(cursor[0], 12.0)
        app._start_preview.assert_called_once()


if __name__ == "__main__":
    unittest.main()
