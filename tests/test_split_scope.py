"""Split scope and coverage regressions using isolated, generated audio."""
import json
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import test_workspace
from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import extract_audio_range, read_duration, render_mix
from backend.workspace_features import StemRangeError, WorkspaceFeatures


@pytest.fixture
def session():
    original = StemSamplePrepApp._set_initial_compact_window

    def hidden_window(app):
        original(app)
        app.withdraw()

    case = test_workspace.WorkspaceTests()
    with patch.object(StemSamplePrepApp, "_set_initial_compact_window", hidden_window), \
            patch("StemSamplePrep.StemSeparator.separate") as separate:
        case.setUp()
        case.separator = separate
        try:
            yield case
        finally:
            case.tearDown()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def attach_selected_stems(case):
    crop = case.paths.root / "selected-stem.wav"
    extract_audio_range(case.paths, case.source, crop, 2, 2)
    case.app.stem_paths = {name: crop for name in case.app.stem_vars}
    case.app.stem_range = (2, 4)
    case.app.selection_start_var.set(2)
    case.app.selection_end_var.set(4)
    case.app._selection_changed()
    case.app._refresh_action_states()


class FakePlayer:
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
    # Deterministic wall-clock coverage of the FFplay fallback. Native prepared
    # playback and paused selection changes use real device tests separately.
    session.app._warm_transport.close()
    session.app._warm_transport.unavailable="mocked fallback transport"
    with patch("StemSamplePrep.start_realtime_mix", side_effect=lambda *a, **kw: [FakePlayer(), FakePlayer()]) as starts, \
            patch("StemSamplePrep.winsound.PlaySound"):
        yield starts


def test_settings_scope_choices_persist_and_initialize_from_saved_value(session):
    app = session.app
    assert app.split_scope_var.get() == "Selection"
    app.open_render_settings()
    app._dialog.withdraw()
    choices = [widget for widget in descendants(app._dialog)
               if widget.winfo_class() == "TCombobox"
               and str(widget.cget("textvariable")) == str(app.split_scope_var)]
    assert len(choices) == 1
    choice = choices[0]
    assert tuple(choice.cget("values")) == ("Selection", "Full track")
    assert str(choice.cget("state")) == "readonly"
    choice.set("Full track")
    app._save_compact_settings()
    saved = session.paths.read_settings()
    assert saved["split_scope"] == "Full track"
    assert app._dialog is None
    # Exercise the real startup initializer with the persisted preferences.
    restored = SimpleNamespace(settings=saved, peak_normalize_var=app.peak_normalize_var)
    WorkspaceFeatures._init_workspace(restored)
    assert restored.split_scope_var.get() == "Full track"
    restored.settings = {"split_scope": "unsupported"}
    WorkspaceFeatures._init_workspace(restored)
    assert restored.split_scope_var.get() == "Selection"


def test_open_and_selection_changes_do_not_start_separation(session):
    app = session.app
    session.separator.assert_not_called()
    assert app.source_wav.exists() and app.peaks and not app.stem_paths
    for start, end in ((1, 3), (2, 4), (0, 6)):
        app.selection_start_var.set(start)
        app.selection_end_var.set(end)
        app._selection_changed()
        app.update_idletasks()
    session.separator.assert_not_called()
    assert not app.busy


def test_explicit_split_uses_selected_audio_then_full_track_and_reuses_coverage(session):
    app = session.app
    observed_inputs = []

    def separate_fixture(input_wav, session_name, **kwargs):
        observed_inputs.append((input_wav, read_duration(session.paths, input_wav)))
        folder = session.paths.temp / "stems" / session_name
        folder.mkdir(parents=True)
        paths = {name: folder / (name + ".wav") for name in app.stem_vars}
        for path in paths.values():
            shutil.copyfile(input_wav, path)
        return paths

    session.separator.side_effect = separate_fixture
    with patch("StemSamplePrep.StemSeparator.available_command", return_value=["synthetic-separator"]), \
            patch.object(type(session.paths), "models_have_payload", return_value=True):
        app.selection_start_var.set(2)
        app.selection_end_var.set(4)
        app.separate_stems()
        session.wait_idle()
        assert app.stem_range == (2, 4)
        assert observed_inputs[0][0] != app.source_wav
        assert observed_inputs[0][1] == pytest.approx(2)
        assert len(app.stem_paths) == 4
        app.selection_start_var.set(2.5)
        app.selection_end_var.set(3.5)
        app.separate_stems()
        assert session.separator.call_count == 1
        assert not app.busy
        app.split_scope_var.set("Full track")
        app.separate_stems()
        session.wait_idle()
        assert session.separator.call_count == 2
        assert observed_inputs[1][0] == app.source_wav
        assert observed_inputs[1][1] == pytest.approx(6)
        assert app.stem_range == (0, app.duration_seconds)
        app.selection_start_var.set(0)
        app.selection_end_var.set(app.duration_seconds)
        app._selection_changed()
        app._validate_stem_range(*app._selection_bounds())
        assert not app._stem_coverage_notice
        app.separate_stems()
        assert session.separator.call_count == 2


@pytest.mark.parametrize("action", ("toggle_playback", "render_wav", "render_mp3", "export_individual_stems"))
def test_outside_selection_clamps_before_playback_and_exports(session, playback, action):
    app = session.app
    attach_selected_stems(session)
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    app._selection_changed()
    assert app._selection_bounds() == (2, 4)
    with patch("StemSamplePrep.render_mix", wraps=render_mix) as render, \
            patch("tkinter.messagebox.showerror") as error, \
            patch("tkinter.messagebox.showwarning") as warning:
        with pytest.raises(StemRangeError, match="2.00.*4.00"):
            app._validate_stem_range(1, 5)
        getattr(app, action)()
        if app.busy:
            session.wait_idle()
    if action == "toggle_playback":
        assert playback.call_args.kwargs["start_seconds"] == 2
        assert playback.call_args.kwargs["duration_seconds"] == 2
        render.assert_not_called()
    else:
        assert render.call_count == (4 if action == "export_individual_stems" else 1)
        for call in render.call_args_list:
            assert call.kwargs["start_seconds"] == 2
            assert call.kwargs["duration_seconds"] == 2
        assert all(path.is_file() for path in app.result_files)
        assert all(read_duration(session.paths, path) == pytest.approx(2, abs=.05)
                   for path in app.result_files)
        playback.assert_not_called()
    session.separator.assert_not_called()
    error.assert_not_called()
    warning.assert_not_called()
    assert not app.busy
    assert not app._stem_coverage_notice


def test_coverage_notice_tracks_scope_and_clears_for_valid_selection(session):
    app = session.app
    attach_selected_stems(session)
    # The guard still explains corrupt/un-normalized raw state. Normal editor
    # input is clamped and immediately clears that obsolete recovery notice.
    app.selection_end_var.set(5)
    app._sync_stem_range_notice()
    assert "required range" in app.status_var.get()
    app.split_scope_var.set("Full track")
    app._sync_stem_range_notice()
    assert "full track" in app.status_var.get()
    app.selection_end_var.set(3.5)
    app._selection_changed()
    assert not app._stem_coverage_notice
    assert app.status_var.get() == ""
    assert not app.status_label.grid_info()
    app.status_var.set("Saved: previous.wav")
    app._sync_stem_range_notice()
    assert app.status_var.get() == "Saved: previous.wav"
    session.separator.assert_not_called()


@pytest.mark.parametrize("edit", ("numeric", "waveform"))
def test_expanding_selection_restarts_playback_inside_coverage(session, playback, edit):
    app = session.app
    attach_selected_stems(session)
    with patch("StemSamplePrep.time.monotonic", return_value=100), \
            patch("tkinter.messagebox.showerror") as error:
        app.toggle_playback()
        assert app.preview_playing
        players = list(app.realtime_processes)
        if edit == "numeric":
            app.selection_end_var.set(5)
            app._commit_numeric(app.end_spinbox)
        else:
            with patch.object(app, "_event_to_seconds", side_effect=(3, 5)):
                # A real selection drag exceeds the click-jitter threshold.
                app._wave_mouse_down(SimpleNamespace(x=100, y=50))
                app._wave_mouse_drag(SimpleNamespace(x=200, y=50))
                app._wave_mouse_up(SimpleNamespace(x=200, y=50))
        assert app.preview_playing
        assert all(player.poll() is not None for player in players)
        assert playback.call_count == 2
        expected_start = 2 if edit == "numeric" else 3
        assert app._selection_bounds() == (expected_start, 4)
        assert playback.call_args.kwargs["start_seconds"] == expected_start
        assert playback.call_args.kwargs["duration_seconds"] == 4 - expected_start
        assert not app._stem_coverage_notice
        error.assert_not_called()
        session.separator.assert_not_called()
        assert not session.callback_errors


@pytest.mark.parametrize("selected,expected", [
    ((1, 5), (2, 4)), ((0, 1), (2, 2.01)), ((5, 6), (3.99, 4)),
    ((4, 4), (3.99, 4)), ((3, 3), (3, 3.01)), ((4, 2), (2, 4)),
])
def test_selection_boundaries_remain_playable_and_display_centiseconds(session, selected, expected):
    app = session.app
    attach_selected_stems(session)
    app.selection_start_var.set(selected[0])
    app.selection_end_var.set(selected[1])
    app._selection_changed()
    assert app._selection_bounds() == pytest.approx(expected)
    assert app.start_spinbox.get() == f"{expected[0]:.2f}"
    assert app.end_spinbox.get() == f"{expected[1]:.2f}"
    assert float(app.start_spinbox.cget("from")) == 2
    assert float(app.end_spinbox.cget("to")) == 4
    app._validate_stem_range(*app._selection_bounds())
    session.separator.assert_not_called()


@pytest.mark.parametrize("limits,selected,expected", [
    ((2.004, 4.006), (0, 6), (2.004, 4.006)),
    ((2.004, 2.009), (0, 6), (2.004, 2.009)),
    ((2.004, 4.006), (6, 6), (3.996, 4.006)),
])
def test_fractional_coverage_is_never_rounded_outwards(limits, selected, expected):
    subject = SimpleNamespace(_stem_selection_limits=lambda: limits)
    result = WorkspaceFeatures._clamp_stem_selection(subject, *selected)
    assert result == pytest.approx(expected)
    assert limits[0] <= result[0] < result[1] <= limits[1]


def test_split_completion_and_history_keep_redo_across_older_wider_selections(session):
    app = session.app
    app.eq_low_var.set(3)
    app._commit_edit()  # This pre-split snapshot covers the entire source.
    attach_selected_stems(session)
    app.selection_start_var.set(0)
    app.selection_end_var.set(6)
    app._handle_stems_ready({"paths": app.stem_paths, "range": [2, 4]})
    assert app._selection_bounds() == (2, 4)
    app.eq_low_var.set(7)
    app.selection_start_var.set(2.5)
    app.selection_end_var.set(3.5)
    app._commit_edit()
    last_index = app.history.index
    app.undo_edit()
    app.undo_edit()
    assert app.eq_low_var.get() == 3
    assert app._selection_bounds() == (2, 4)
    app.redo_edit()
    app.redo_edit()
    assert app.history.index == last_index
    assert app.eq_low_var.get() == 7
    assert app._selection_bounds() == (2.5, 3.5)
    session.separator.assert_not_called()


def test_recovery_clamps_older_saved_selection_and_source_reopen_removes_limits(session):
    app = session.app
    attach_selected_stems(session)
    app._write_recovery()
    recovery = session.paths.temp / "recovery.json"
    saved = json.loads(recovery.read_text(encoding="utf-8"))
    saved["edits"]["selection_start"] = 0
    saved["edits"]["selection_end"] = 6
    recovery.write_text(json.dumps(saved), encoding="utf-8")
    app.restore_last_session()
    session.wait_idle()
    assert app._selection_bounds() == (2, 4)
    assert app._stem_selection_limits() == (2, 4)
    app.load_audio_path(session.source)
    session.wait_idle()
    assert not app.stem_paths
    assert app._selection_bounds() == (0, 6)
    assert float(app.start_spinbox.cget("from")) == 0
    assert float(app.end_spinbox.cget("to")) == 6
    session.separator.assert_not_called()


def test_incomplete_stems_keep_source_edit_limits_and_range_safety_guard(session):
    app = session.app
    attach_selected_stems(session)
    del app.stem_paths["other"]
    app.selection_start_var.set(0)
    app.selection_end_var.set(6)
    app._selection_changed()
    assert app._selection_bounds() == (0, 6)
    assert app._stem_selection_limits() is None
    with pytest.raises(StemRangeError):
        app._validate_stem_range(*app._selection_bounds())
