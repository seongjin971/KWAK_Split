"""Split scope and coverage regressions using isolated, generated audio."""
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import test_workspace
from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import extract_audio_range, read_duration
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
def playback():
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
def test_outside_coverage_is_inline_and_starts_no_processing(session, playback, action):
    app = session.app
    attach_selected_stems(session)
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    app._selection_changed()
    with patch("StemSamplePrep.render_mix") as render, \
            patch("tkinter.messagebox.showerror") as error, \
            patch("tkinter.messagebox.showwarning") as warning:
        with pytest.raises(StemRangeError, match="2.00.*4.00"):
            app._validate_stem_range(*app._selection_bounds())
        getattr(app, action)()
    render.assert_not_called()
    playback.assert_not_called()
    session.separator.assert_not_called()
    error.assert_not_called()
    warning.assert_not_called()
    assert "2.00–4.00s" in app.status_var.get()
    assert "Click Split Stems" in app.status_var.get()
    assert app.status_frame.grid_info()
    assert not app.busy and not app.preview_playing
    assert not list(app.output_dir.iterdir())


def test_coverage_notice_tracks_scope_and_clears_for_valid_selection(session):
    app = session.app
    attach_selected_stems(session)
    app.selection_end_var.set(5)
    app._selection_changed()
    assert "required range" in app.status_var.get()
    app.split_scope_var.set("Full track")
    app._sync_stem_range_notice()
    assert "full track" in app.status_var.get()
    app.selection_end_var.set(3.5)
    app._selection_changed()
    assert not app._stem_coverage_notice
    assert app.status_var.get() == ""
    assert not app.status_frame.grid_info()
    app.status_var.set("Saved: previous.wav")
    app._sync_stem_range_notice()
    assert app.status_var.get() == "Saved: previous.wav"
    session.separator.assert_not_called()


@pytest.mark.parametrize("edit", ("numeric", "waveform"))
def test_expanding_selection_stops_active_stem_playback_without_modal(session, playback, edit):
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
                app._wave_mouse_down(SimpleNamespace(x=0))
                app._wave_mouse_drag(SimpleNamespace(x=1))
                app._wave_mouse_up(SimpleNamespace(x=1))
        assert not app.preview_playing
        assert all(player.poll() is not None for player in players)
        assert playback.call_count == 1
        assert "Click Split Stems" in app.status_var.get()
        error.assert_not_called()
        session.separator.assert_not_called()
        assert not session.callback_errors
