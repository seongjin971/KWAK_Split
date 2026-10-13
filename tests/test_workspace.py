"""Integration tests against the real Tk widget tree, using generated audio only."""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from StemSamplePrep import StemSamplePrepApp
from backend.app_paths import AppPaths
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, extract_audio_range, render_mix


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="workspace-test-", dir=Path(__file__).resolve().parents[1] / "temp")
        self.addCleanup(self.folder.cleanup)
        self.paths = AppPaths(Path(self.folder.name))
        self.paths.ensure()
        self.source = self.paths.root / "test.wav"
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=6:sample_rate=48000", "-c:a", "pcm_s24le", str(self.source)],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.patches = [patch.object(AppPaths, "from_runtime", return_value=self.paths),
                        patch.dict(os.environ,{"SDL_AUDIODRIVER":"dummy"}),
                        patch.object(StemSamplePrepApp, "_configure_logging"),
                        patch("tkinter.messagebox.askyesnocancel", return_value=False),
                        patch("tkinter.messagebox.askyesno", return_value=True),
                        patch("tkinter.messagebox.askokcancel", return_value=True),
                        patch("tkinter.messagebox.showwarning"), patch("tkinter.messagebox.showinfo"),
                        patch("tkinter.messagebox.showerror")]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.app = StemSamplePrepApp(ui_scale=getattr(self, "ui_scale", 1.0))
        self.callback_errors = []
        self.app.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.app.load_audio_path(self.source)
        self.wait_idle()

    def tearDown(self):
        self.app._workspace_close()
        self.app.closing = True
        self.app.stop_preview(show_status=False)
        self.app._cancel_main_after_callbacks()
        self.app._disable_file_drop()
        self.app.destroy()
        self.app._warm_transport.close()
        for p in reversed(self.patches):
            p.stop()
        self.folder.cleanup()

    def wait_idle(self, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if not self.app.busy:
                break
            time.sleep(0.02)
        self.app.update()
        self.assertFalse(self.app.busy, "Worker did not finish")
        self.assertFalse(self.callback_errors, self.callback_errors)
        self.assertFalse(self.mocks[-1].called, self.mocks[-1].call_args)

    def test_responsive_compact_layout_and_reachable_actions(self):
        for width, height in ((1280, 720), (900, 600), (760, 620), (640, 480), (480, 360), (1000, 420), (1000, 700)):
            with self.subTest(size=(width, height)):
                self.app.geometry(f"{width}x{height}")
                self.app.update()
                width,height=self.app.winfo_width(),self.app.winfo_height()
                self.assertEqual(width*7,height*10)
                self.assertGreaterEqual(width,self.app.minsize()[0])
                self.assertLessEqual(width,self.app.maxsize()[0])
                for widget in (self.app.load_button, self.app.settings_button,
                               self.app.render_button, self.app.render_mp3_button):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertGreaterEqual(widget.winfo_rootx(), self.app.winfo_rootx())
                    self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), self.app.winfo_rootx()+width)
                self.assertEqual(self.app._layout_mode, "side-by-side")
                self.assertLess(self.app.eq_panel.winfo_rootx(), self.app.mixer_panel.winfo_rootx())
                self.assertFalse(self.app.workspace_scroll.bar.winfo_ismapped())
                for widget in (self.app.eq_panel,self.app.mixer_panel,self.app.eq_editor,
                               self.app.play_button,self.app.export_stems_button,
                               self.app.fade_out_spinbox,*self.app.stem_widgets["other"]):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertGreaterEqual(widget.winfo_rootx(),self.app.winfo_rootx())
                    self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),self.app.winfo_rootx()+width+1)
                    self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.app.winfo_rooty()+height+1)
        self.assertEqual(self.app.ui_scale,1)

    def test_clear_audio_resets_adjustments(self):
        self.app.eq_low_var.set(7)
        self.app.tempo_percent_var.set(150)
        self.app.stem_vars["vocals"]["mute"].set(True)
        self.app.cleanup_current_temp()
        self.assertEqual(self.app.eq_low_var.get(), 0)
        self.assertEqual(self.app.tempo_percent_var.get(), 100)
        self.assertFalse(self.app.stem_vars["vocals"]["mute"].get())
        self.assertIsNone(self.app.source_wav)

    def test_drag_is_one_undo_step_and_redo_restores_it(self):
        self.app._begin_edit_drag()
        for value in (1, 2, 3, 4):
            self.app.eq_low_var.set(value)
        self.app._end_edit_drag()
        self.app._commit_edit()
        self.app.undo_edit()
        self.assertEqual(self.app.eq_low_var.get(), 0)
        self.app.redo_edit()
        self.assertEqual(self.app.eq_low_var.get(), 4)

    def test_zoom_seek_and_selection_only_preview(self):
        self.app.selection_start_var.set(2)
        self.app.selection_end_var.set(4)
        self.app.zoom_selection()
        self.app.update()
        midpoint = self.app._event_to_seconds(SimpleNamespace(x=self.app.wave_canvas.winfo_width() / 2))
        self.assertAlmostEqual(midpoint, 3)
        self.app.playback_cursor_manual = True
        self.app.playback_position_var.set(5)
        self.assertEqual(self.app._playback_bounds(), (2, 4))
        self.app._draw_fade_overlay_only()
        self.assertFalse(self.callback_errors)

    def test_selected_stem_offsets_match_original_render(self):
        crop = self.paths.root / "crop.wav"
        extract_audio_range(self.paths, self.source, crop, 2.0, 2.0)
        self.app.stem_paths = {"vocals": crop}
        self.app.stem_range = (2, 4)
        self.app.selection_start_var.set(2.5)
        self.app.selection_end_var.set(3.0)
        stems = self.app._build_mix_stems()
        self.assertEqual(stems[0].offset_seconds, 2)
        effects = AudioEffects(limiter_enabled=False)
        original_output = self.paths.output / "original.wav"
        cropped_output = self.paths.output / "cropped.wav"
        render_mix(self.paths, [MixStem("source", self.source, 1)], original_output, 2.5, 0.5, 0, 0, effects=effects)
        render_mix(self.paths, stems, cropped_output, 2.5, 0.5, 0, 0, effects=effects)
        # Decoded PCM is identical; metadata chunks may differ between outputs.
        import wave
        with wave.open(str(original_output)) as a, wave.open(str(cropped_output)) as b:
            self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))
        self.app.selection_end_var.set(5)
        with self.assertRaisesRegex(Exception, "[Ss]eparate"):
            self.app._build_mix_stems()

    def test_output_profiles_and_normalize_use_requested_format(self):
        for rate, depth, normalize in ((44100, 16, False), (44100, 24, True), (48000, 16, True), (48000, 24, False)):
            with self.subTest(rate=rate, depth=depth, normalize=normalize):
                target = self.paths.output / f"{rate}_{depth}.wav"
                render_mix(self.paths, [MixStem("source", self.source, 1)], target, 0, 1, 0, 0,
                           effects=AudioEffects(sample_rate=rate, bit_depth=depth, peak_normalize=normalize))
                output = subprocess.check_output([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(target)],
                                                 creationflags=subprocess.CREATE_NO_WINDOW)
                stream = json.loads(output)["streams"][0]
                self.assertEqual(int(stream["sample_rate"]), rate)
                self.assertEqual(int(stream["bits_per_sample"]), depth)

    def test_result_actions_are_connected(self):
        self.app._show_results([self.source])
        self.assertEqual(self.app._selected_result(), self.source)
        with patch("os.startfile") as start:
            self.app.play_result_file()
            start.assert_called_with(self.source)
            self.app.open_result_folder()
            start.assert_called_with(self.source.parent)

    def test_english_ui_summaries_and_dialogs(self):
        import re
        korean = re.compile("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
        self.assertEqual(self.app.split_scope_var.get(), "Selection")
        self.app._update_workspace_summary()
        self.assertIn("Monitor: Original audio", self.app.mix_summary_var.get())
        self.assertIn("Export: Original audio", self.app.mix_summary_var.get())
        with patch("tkinter.messagebox.askokcancel") as confirm:
            self.assertTrue(self.app._confirm_render())
            confirm.assert_not_called()
        self.app.open_render_settings()
        self.app.update()

        def check_text(widget):
            for option in ("text", "values"):
                if option in widget.keys():
                    self.assertNotRegex(str(widget.cget(option)), korean)
            for child in widget.winfo_children():
                check_text(child)

        check_text(self.app)
        self.app._close_render_settings()

    def test_loop_restarts_and_explicit_stop_cancels_repeat(self):
        from backend.audio_processing.ffmpeg_tools import start_realtime_mix
        self.app.selection_start_var.set(0.2)
        self.app.selection_end_var.set(0.6)
        self.app.loop_var.set(True)
        with patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}), \
                patch("StemSamplePrep.start_realtime_mix", wraps=start_realtime_mix), \
                patch.object(self.app,"_loop_preview",wraps=self.app._loop_preview) as loops:
            self.app.toggle_playback()
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and loops.call_count < 2:
                self.app.update()
                time.sleep(0.02)
            self.assertGreaterEqual(loops.call_count, 2)
            self.app.stop_preview()
            count = loops.call_count
            for _ in range(20):
                self.app.update()
                time.sleep(0.02)
            self.assertEqual(loops.call_count, count)
            self.assertFalse(self.app.preview_playing)
            prepared=self.app._warm_transport._cached
            self.assertIsNotNone(prepared)
            self.assertTrue(prepared[1].player.paused)
            self.assertEqual(prepared[1].position_seconds(),0)

    def test_zero_volume_stem_can_export_silent_wav(self):
        target = self.paths.output / "silent.wav"
        render_mix(self.paths, [MixStem("vocals", self.source, 0)], target, 0, 1, 0, 0, include_silent=True)
        import wave
        with wave.open(str(target)) as handle:
            samples = handle.readframes(handle.getnframes())
        self.assertTrue(samples)
        self.assertEqual(set(samples), {0})


if __name__ == "__main__":
    unittest.main()
