"""Independent playback audit with generated audio and isolated hidden windows."""
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import test_workspace
from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import AudioProcessingError, extract_audio_range, render_mix


@pytest.fixture
def session():
    # Do not map a QA window over the user's running application.
    original = StemSamplePrepApp._set_initial_compact_window

    def hidden_window(app):
        original(app)
        app.withdraw()

    case = test_workspace.WorkspaceTests()
    with patch.object(StemSamplePrepApp, "_set_initial_compact_window", hidden_window), \
            patch("StemSamplePrep.StemSeparator.separate") as separate:
        try:
            case.setUp()
            case.auto_separate = separate
            yield case
        finally:
            try:
                if hasattr(case, "app"):
                    case.tearDown()
            finally:
                # unittest cleanups also cover a failed Tcl/Tk initialization.
                case.doCleanups()


class FakePlayer:
    """Controllable audio child; lets tests inspect exact playback requests."""
    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    kill = terminate

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def playback(session):
    # These deterministic wall-clock tests cover the legacy FFplay fallback;
    # device-clock and retained pause are exercised by real warm-transport tests.
    session.app._warm_transport.close()
    session.app._warm_transport.unavailable="mocked fallback transport"
    with patch("StemSamplePrep.start_realtime_mix", side_effect=lambda *a, **kw: [FakePlayer(), FakePlayer()]) as starts, \
            patch("StemSamplePrep.winsound.PlaySound"):
        yield starts


def test_open_audio_only_prepares_source_and_waveform(session):
    app = session.app
    session.auto_separate.assert_not_called()
    assert app.source_wav.exists() and app.peaks
    assert app.stem_paths == {} and not app.busy
    assert app.separate_button.enabled
    assert all(not widgets[0].enabled for widgets in app.stem_widgets.values())


def test_pause_resume_keeps_source_position_at_changed_speed(session, playback):
    app = session.app
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    app.tempo_percent_var.set(50)
    with patch("StemSamplePrep.time.monotonic", return_value=100):
        app.toggle_playback()
    with patch("StemSamplePrep.time.monotonic", return_value=102):
        app.toggle_playback()
    assert not app.preview_playing
    assert app.playback_position_var.get() == pytest.approx(2)
    app.tempo_percent_var.set(200)
    with patch("StemSamplePrep.time.monotonic", return_value=103):
        app.toggle_playback()
    assert app.preview_playing
    assert playback.call_args.kwargs["start_seconds"] == pytest.approx(2)
    assert playback.call_args.kwargs["duration_seconds"] == pytest.approx(3)
    assert playback.call_args.kwargs["effects"].tempo_ratio == 2


def test_stem_preview_and_export_share_selection_effects_and_offsets(session, playback):
    app = session.app
    crop = session.paths.root / "selected-stem.wav"
    extract_audio_range(session.paths, session.source, crop, 2, 3)
    app.stem_paths = {"vocals": crop}
    app.stem_range = (2, 5)
    app.selection_start_var.set(2.5)
    app.selection_end_var.set(4.5)
    app.stem_vars["vocals"]["volume"].set(50)
    app.eq_low_shape_var.set("High Pass")
    app.eq_high_shape_var.set("Low Pass")
    app.high_pass_slope_var.set(36)
    app.low_pass_slope_var.set(48)
    app.high_pass_q_var.set(1.1)
    app.tempo_percent_var.set(125)
    app.pitch_semitones_var.set(3)
    app.fade_in_var.set(.04)
    app.fade_out_var.set(.08)
    app.toggle_playback()
    live = playback.call_args
    with patch("StemSamplePrep.render_mix", wraps=render_mix) as export:
        app.render_wav()
        session.wait_idle()
    rendered = export.call_args
    assert live.args[1] == rendered.args[1]
    assert live.args[1][0].offset_seconds == 2
    for option in ("start_seconds", "duration_seconds", "fade_in", "fade_out"):
        assert live.kwargs[option] == rendered.kwargs[option]
    assert asdict(live.kwargs["effects"]) == asdict(rendered.kwargs["effects"])
    assert app.result_files[0].exists()
    assert not session.callback_errors


def test_stem_coverage_rejects_outside_selection_before_audio_starts(session, playback):
    app = session.app
    app.stem_paths = {"vocals": app.source_wav}
    app.stem_range = (2, 4)
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    with pytest.raises(AudioProcessingError, match="separate"):
        app._start_context_preview()
    playback.assert_not_called()
    assert not app.preview_playing


@pytest.mark.parametrize("transport", ("playing", "paused", "finished"))
def test_routine_transport_state_does_not_open_duplicate_status_row(session, playback, transport):
    app = session.app
    app.loop_var.set(False)
    with patch("StemSamplePrep.time.monotonic", return_value=100):
        app.toggle_playback()
        if transport == "paused":
            app.toggle_playback()
        elif transport == "finished":
            for process in app.realtime_processes:
                process.returncode = 0
            app._update_playback_position()
    assert not app.status_label.grid_info()
    app.status_var.set("Preview failed. Check the audio settings and output device.")
    assert app.status_label.grid_info()


def test_waveform_selection_applies_to_current_playback_on_release(session, playback):
    app = session.app
    with patch("StemSamplePrep.time.monotonic", return_value=100):
        app.toggle_playback()
        # Exercise the production right-drag callbacks. Mapping positions here
        # keeps this audio regression independent of hidden-window geometry.
        with patch.object(app, "_event_to_seconds", side_effect=[2, 3]):
            app._wave_mouse_down(SimpleNamespace(x=0))
            app._wave_mouse_drag(SimpleNamespace(x=1))
            app._wave_mouse_up(SimpleNamespace(x=1))
    assert app._selection_bounds() == (2, 3)
    assert app.preview_playing
    assert playback.call_args.kwargs["start_seconds"] == pytest.approx(2)
    assert playback.call_args.kwargs["duration_seconds"] == pytest.approx(1)


def test_empty_waveform_selection_does_not_keep_old_range_playing(session, playback):
    app = session.app
    with patch("StemSamplePrep.time.monotonic", return_value=100):
        app.toggle_playback()
        with patch.object(app, "_event_to_seconds", return_value=2):
            app._wave_mouse_down(SimpleNamespace(x=0))
            app._wave_mouse_up(SimpleNamespace(x=0))
    assert not app.preview_playing
    assert not session.callback_errors


def test_outside_stem_selection_stops_old_audio_and_explains_range(session, playback):
    app = session.app
    app.stem_paths = {"vocals": app.source_wav}
    app.stem_range = (0, 4)
    app.selection_start_var.set(1)
    app.selection_end_var.set(3)
    with patch("StemSamplePrep.time.monotonic", return_value=100):
        app.toggle_playback()
        with patch.object(app, "_event_to_seconds", side_effect=[4, 5]):
            app._wave_mouse_down(SimpleNamespace(x=0))
            app._wave_mouse_drag(SimpleNamespace(x=1))
            app._wave_mouse_up(SimpleNamespace(x=1))
    assert not app.preview_playing
    assert "separate" in app.status_var.get().lower()
    assert not session.callback_errors
