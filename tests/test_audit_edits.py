"""Independent audit regressions for real compact edit interactions."""
from pathlib import Path
from unittest.mock import patch

import pytest

import test_workspace


@pytest.fixture
def session():
    case = test_workspace.WorkspaceTests()
    case.setUp()
    try:
        yield case
    finally:
        case.tearDown()


def test_fader_track_jump_and_drag_are_one_undo_step(session):
    app = session.app
    app.stem_paths = {stem: app.source_wav for stem in app.stem_vars}
    app.stem_range = (0, app.duration_seconds)
    app._refresh_action_states()
    app.update()
    app._commit_edit()
    fader = app.stem_widgets["vocals"][0]
    initial = app.stem_vars["vocals"]["volume"].get()
    top, bottom = fader.bounds()
    x = round(fader.winfo_width() * .6)
    fader.event_generate("<ButtonPress-1>", x=x, y=round(bottom))
    app.update()
    fader.event_generate("<B1-Motion>", x=x, y=round((top + bottom) / 2))
    fader.event_generate("<ButtonRelease-1>", x=x, y=round((top + bottom) / 2))
    app.update()
    changed = app.stem_vars["vocals"]["volume"].get()
    assert changed != initial
    app.undo_edit()
    assert app.stem_vars["vocals"]["volume"].get() == initial
    app.redo_edit()
    assert app.stem_vars["vocals"]["volume"].get() == changed
    assert not session.callback_errors


def test_advanced_cannot_commit_out_of_range_q_by_closing(session):
    app = session.app
    app.open_advanced()
    app.update()
    entry = next(widget for widget, _, variable, _ in app._numeric_fields
                 if variable is app.eq_mid_q_var)
    entry.delete(0, "end")
    entry.insert(0, "999")
    app._close_render_settings()
    app.update()
    assert app._dialog is not None
    assert "Q" in app.advanced_error_var.get()
    assert "0.3" in app.advanced_error_var.get()
    entry.delete(0, "end")
    entry.insert(0, "1.25")
    app._close_render_settings()
    app.update()
    assert app._dialog is None
    assert app.eq_mid_q_var.get() == 1.25
    assert app._build_audio_effects().mid_q == 1.25
    assert not session.callback_errors


def test_invalid_save_folder_keeps_existing_output_and_dialog(session):
    app = session.app
    previous = app.output_dir
    app.open_render_settings()
    app.update()
    app.settings_folder_var.set(str(session.source))
    app._save_compact_settings()
    assert app.output_dir == previous
    assert app._dialog is not None
    assert "folder" in app.settings_error_var.get().lower()
    app.settings_folder_var.set("")
    app._save_compact_settings()
    assert app.output_dir == previous
    assert app._dialog is not None
    picked = session.paths.root / "new output"
    with patch("tkinter.filedialog.askdirectory", return_value=str(picked)):
        app._browse_save_folder()
    app._save_compact_settings()
    assert app.output_dir == Path(picked)
    assert app._dialog is None
    assert not session.callback_errors


def test_resizing_after_undo_preserves_edit_and_scroll_access(session):
    app = session.app
    app.fade_in_var.set(.04)
    app._commit_edit()
    app.eq_mid_var.set(4)
    app._commit_edit()
    app.undo_edit()
    snapshot = app._edit_snapshot()
    for width, height in ((640, 480), (1000, 700), (760, 600), (1280, 800)):
        app.geometry(f"{width}x{height}")
        app.update()
        assert app._edit_snapshot() == snapshot
        if app._layout_mode == "stacked":
            app.workspace_scroll.canvas.yview_moveto(1)
            app.update()
            assert (app.mixer_panel.winfo_rooty() + app.mixer_panel.winfo_height()
                    <= app.workspace_scroll.canvas.winfo_rooty()
                    + app.workspace_scroll.canvas.winfo_height() + 2)
    app.redo_edit()
    assert app.eq_mid_var.get() == 4
    assert app.fade_in_var.get() == .04
    assert not session.callback_errors


def test_crossed_pass_filters_are_accepted_and_can_be_changed(session):
    app = session.app
    app.eq_low_shape_var.set("High Pass")
    app.eq_high_shape_var.set("Low Pass")
    app.eq_low_freq_var.set(2000)
    app.eq_high_freq_var.set(1000)
    app.update()
    crossed = app._build_audio_effects()
    assert crossed.high_pass_hz == 2000
    assert crossed.low_pass_hz == 1000
    assert not app.busy
    assert "high-pass" not in app.status_var.get().lower()

    app.eq_high_freq_var.set(8000)
    app.update()
    effects = app._build_audio_effects()
    assert not session.callback_errors, session.callback_errors
    assert effects.high_pass_hz == 2000
    assert effects.low_pass_hz == 8000
    assert app.eq_editor.handles
    assert not session.callback_errors
