"""Range manipulation, precision and keyboard behavior through real Tk events."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.wave_selection import SelectionDrag
from test_compact_keyboard import session, press
from test_spectrum_ui import prepare, pump_until


@pytest.mark.parametrize("target,expected", [(-30, (2.004, 3.506)), (30, (2.504, 4.006)),
                                           (3.25, (2.25, 3.752))])
def test_translation_preserves_fractional_length_at_both_limits(target, expected):
    result = SelectionDrag("move", 3, 2, 3.502).bounds(target, (2.004, 4.006))
    assert result == pytest.approx(expected)
    assert result[1] - result[0] == pytest.approx(1.502)


def select(app, start, end, view=None):
    app.selection_start_var.set(start)
    app.selection_end_var.set(end)
    if view is not None:
        app.view_start, app.view_end = view
    app._selection_changed()
    app._commit_edit()
    app.update()


def x_at(app, seconds):
    start, end = app._wave_view_bounds()
    return round((seconds-start)/(end-start)*app.wave_canvas.winfo_width())


def drag(app, start_x, end_x, y=50):
    canvas = app.wave_canvas
    canvas.event_generate("<ButtonPress-3>", x=round(start_x), y=round(y))
    canvas.event_generate("<B3-Motion>", x=round(end_x), y=round(y))
    canvas.event_generate("<ButtonRelease-3>", x=round(end_x), y=round(y))
    app.update()


def move(app, seconds):
    grip = app._wave_selection.grip()
    x, y = (grip[0]+grip[2])/2, (grip[1]+grip[3])/2
    a, b = app._wave_view_bounds()
    drag(app, x, x + seconds/(b-a)*app.wave_canvas.winfo_width(), y)


def test_edges_use_wide_targets_without_initial_jump_and_keep_opposite_end(session):
    app = session.app
    select(app, 1, 5)
    for endpoint, start, target, opposite in (("start", 1, 2, 5), ("end", 5, 4, 2)):
        canvas = app.wave_canvas
        x = x_at(app, start) + 7
        canvas.event_generate("<Motion>", x=x, y=50)
        assert canvas.cget("cursor") == "sb_h_double_arrow"
        before = app._selection_bounds()
        canvas.event_generate("<ButtonPress-3>", x=x, y=50)
        assert app._selection_bounds() == before
        canvas.event_generate("<B3-Motion>", x=x_at(app, target)+7, y=50)
        canvas.event_generate("<ButtonRelease-3>", x=x_at(app, target)+7, y=50)
        app.update()
        a, b = app._selection_bounds()
        assert (a if endpoint == "start" else b) == pytest.approx(target, abs=.01)
        assert (b if endpoint == "start" else a) == opposite
    drag(app, x_at(app, 2), x_at(app, 5.5))
    assert app._selection_bounds() == pytest.approx((3.99, 4))
    assert not session.callback_errors


def test_grip_move_is_one_undo_step_and_new_body_drag_still_replaces_range(session):
    app = session.app
    select(app, 1, 3)
    move(app, 2)
    assert app._selection_bounds() == pytest.approx((3, 5), abs=.01)
    app.undo_edit()
    assert app._selection_bounds() == (1, 3)
    app.redo_edit()
    assert app._selection_bounds() == pytest.approx((3, 5), abs=.01)
    drag(app, x_at(app, 3.5), x_at(app, 4.5))
    assert app._selection_bounds() == pytest.approx((3.5, 4.5), abs=.01)
    before = app._selection_bounds()
    drag(app, x_at(app, 4), x_at(app, 4))
    assert app._selection_bounds() == before


def test_narrow_zoomed_selection_and_offscreen_boundaries(session):
    app = session.app
    select(app, 2, 2.01, (1, 3))
    assert app._wave_selection.hit(SimpleNamespace(x=x_at(app, 2), y=50)) == "start"
    assert app._wave_selection.hit(SimpleNamespace(x=x_at(app, 2.01), y=50)) == "end"
    move(app, .4)
    a, b = app._selection_bounds()
    assert b-a == pytest.approx(.01)
    assert a == pytest.approx(2.4, abs=.01)
    select(app, .5, 5, (2, 4))
    assert not app.wave_canvas.find_withtag("selection-boundary")
    assert app._wave_selection.hit(SimpleNamespace(x=1, y=50)) == "new"
    assert app.wave_canvas.find_withtag("selection-move")


@pytest.mark.parametrize("target,expected", ((1,(1,2)), (3,(2,3))))
def test_restored_single_point_can_start_a_selection_in_either_direction(session, target, expected):
    app = session.app
    select(app, 2, 2)
    assert app._wave_selection.hit(SimpleNamespace(x=x_at(app,2),y=50)) == "new"
    drag(app, x_at(app,2), x_at(app,target))
    assert app._selection_bounds() == pytest.approx(expected,abs=.01)


def test_partial_stem_limits_and_fractional_duration_survive_move_history(session):
    app = session.app
    app.stem_paths = {stem: app.source_wav for stem in app.stem_vars}
    app.stem_range = (2.004, 4.006)
    select(app, 2.004, 3.506)
    move(app, 4)
    assert app._selection_bounds() == pytest.approx((2.504, 4.006))
    app.undo_edit()
    assert app._selection_bounds() == pytest.approx((2.004, 3.506))
    app.redo_edit()
    move(app, -4)
    assert app._selection_bounds() == pytest.approx((2.004, 3.506))
    assert float(app.selection_label.cget("text")[:-1]) == 1.5


def test_zoomed_drag_pans_beyond_canvas_and_release_cancels_timer(session):
    app = session.app
    select(app, 1.5, 2.5, (1, 3))
    canvas = app.wave_canvas
    canvas.event_generate("<ButtonPress-3>", x=x_at(app, 2.5), y=50)
    canvas.event_generate("<B3-Motion>", x=canvas.winfo_width()+60, y=50)
    pump_until(app, lambda: app.view_start > 1.1)
    assert app._selection_bounds()[0] == 1.5
    assert app._selection_bounds()[1] > 3
    canvas.event_generate("<ButtonRelease-3>", x=canvas.winfo_width()+60, y=50)
    assert app._wave_selection.pan_after is None and app._wave_selection.drag is None
    assert not session.callback_errors


def test_left_seek_on_every_handle_preserves_range_and_click_does_not_restart(session):
    app = session.app
    select(app, 1, 5)
    grip = app._wave_selection.grip()
    for x, y in ((x_at(app, 1), 50), (x_at(app, 5), 50), ((grip[0]+grip[2])/2, 8)):
        app.wave_canvas.event_generate("<ButtonPress-1>", x=round(x), y=y)
        app.wave_canvas.event_generate("<ButtonRelease-1>", x=round(x), y=y)
        assert app._selection_bounds() == (1, 5)
        assert app.playback_position_var.get() == pytest.approx(app._event_to_seconds(SimpleNamespace(x=round(x))))
    with patch.object(app, "stop_preview") as stop:
        app.preview_playing = True
        drag(app, x_at(app, 2), x_at(app, 2))
        stop.assert_not_called()
        app.preview_playing = False


def test_brackets_mark_paused_cursor_once_per_press_and_each_is_undoable(session):
    app = session.app
    select(app, 0, 6)
    app.focus_force();app.update()
    app._set_playback_position(2)
    app.event_generate("<KeyPress-bracketleft>")
    app._set_playback_position(3)
    app.event_generate("<KeyPress-bracketleft>")
    assert app._selection_bounds() == (2, 6)
    app.event_generate("<KeyRelease-bracketleft>")
    press(app, "bracketright")
    assert app._selection_bounds() == (2, 3)
    assert app.playback_position_var.get() == 3
    app.undo_edit();assert app._selection_bounds() == (2, 6)
    app.undo_edit();assert app._selection_bounds() == (0, 6)
    app.redo_edit();app.redo_edit();assert app._selection_bounds() == (2, 3)


def test_brackets_ignore_text_modal_busy_and_empty_states(session):
    app = session.app
    select(app, 1, 5)
    app._set_playback_position(3)
    with patch.object(app._wave_selection, "mark") as mark:
        app.start_spinbox.focus_set();app.update();press(app, "bracketleft")
        mark.assert_not_called()
        app.selection_start_var.set(1)
        app.open_render_settings();app._dialog.focus_set();app.update();press(app, "bracketright")
        mark.assert_not_called();app._close_render_settings()
    app.busy = True
    app._wave_selection.mark("start")
    assert app._selection_bounds() == (1, 5)
    app.busy = False
    with patch.object(app, "duration_seconds", 0):
        app._wave_selection.mark("end")
    assert not app._wave_selection.keys_down


def test_bracket_limits_and_opposite_side_crossing_remain_playable(session):
    app = session.app
    app.stem_paths = {stem: app.source_wav for stem in app.stem_vars}
    app.stem_range = (2.004, 4.006)
    select(app, 2.5, 3.5)
    for endpoint, cursor, expected in (("start", 6, (3.996,4.006)),
                                       ("end", 0, (2.004,2.014))):
        app._set_playback_position(cursor)
        app._wave_selection.mark(endpoint)
        app._wave_selection.release_key(endpoint)
        app.update()
        assert app._selection_bounds() == pytest.approx(expected)
        assert app._selection_bounds()[1]-app._selection_bounds()[0] == pytest.approx(.01)
    with patch.object(app._wave_selection, "mark") as mark:
        app.focus_force(); app.update()
        app.event_generate("<KeyPress-bracketleft>", state=4)
        app.event_generate("<KeyRelease-bracketleft>", state=4)
        mark.assert_not_called()


@pytest.mark.parametrize("inputs", (1, 4))
def test_marking_during_playback_keeps_stream_clock_and_applies_next_play(session, monkeypatch, inputs):
    app = session.app
    prepare(app, monkeypatch)
    if inputs == 4:
        app.stem_paths = {stem: app.source_wav for stem in app.stem_vars}
        app.stem_range = (0, app.duration_seconds)
    app._refresh_action_states();app.toggle_playback()
    pump_until(app, lambda: app.realtime_processes and app.realtime_processes.position_seconds() > .15)
    owner = app.realtime_processes
    app.focus_force();app.update()
    before = owner.playback_position().position_seconds
    press(app, "bracketleft")
    start = app._selection_bounds()[0]
    assert start == pytest.approx(before, abs=.15)
    pump_until(app, lambda: owner.playback_position().position_seconds > start+.35)
    press(app, "bracketright")
    end = app._selection_bounds()[1]
    assert end > start+.2
    pump_until(app, lambda: owner.playback_position().position_seconds > end+.1)
    assert app.realtime_processes is owner and app.preview_playing
    assert owner.player.poll() is None and owner._settings["fade_bounds"] == (0, 6)
    app.toggle_playback();app.toggle_playback()
    pump_until(app, lambda: app.realtime_processes and app.realtime_processes is not owner)
    assert app.realtime_processes._settings["fade_bounds"] == (start, end)
    assert not session.callback_errors
