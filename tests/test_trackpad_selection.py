"""Trackpad-style button-one events, fixed anchors and uninterrupted monitoring."""
from unittest.mock import patch

import pytest

from test_compact_keyboard import session
from test_wave_selection import select, x_at
from test_spectrum_ui import prepare, pump_until


def click(app, seconds, state=0, y=50):
    canvas=app.wave_canvas; x=x_at(app,seconds)
    canvas.event_generate("<ButtonPress-1>",x=x,y=y,state=state)
    canvas.event_generate("<ButtonRelease-1>",x=x,y=y,state=state)
    app.update()


def drag(app, x1, x2, y=50, state=0, button=1):
    canvas=app.wave_canvas
    canvas.event_generate(f"<ButtonPress-{button}>",x=round(x1),y=round(y),state=state)
    canvas.event_generate(f"<B{button}-Motion>",x=round(x2),y=round(y),state=state|(0x100<<(button-1)))
    canvas.event_generate(f"<ButtonRelease-{button}>",x=round(x2),y=round(y),state=state|(0x100<<(button-1)))
    app.update()


@pytest.mark.parametrize("button", (1,3))
def test_end_handle_keeps_paused_cursor_inside_and_outside_new_range(session, button):
    app=session.app;select(app,1,5);click(app,3,state=8)
    for old_end,new_end in ((5,4),(4,2.5)):
        drag(app,x_at(app,old_end),x_at(app,new_end),state=8,button=button)
        assert app._selection_bounds()==pytest.approx((1,new_end),abs=.01)
        assert app.playback_position_var.get()==3 and not app.preview_playing
        # Idle audio preparation may clamp its request, but never the cursor.
        request=app._prepared_request()
        assert request.start_seconds==(3 if new_end>3 else 1)
        assert app.playback_position_var.get()==3
    app.undo_edit();assert app._selection_bounds()==pytest.approx((1,4),abs=.01)
    assert app.playback_position_var.get()==3
    assert not session.callback_errors


@pytest.mark.parametrize("inputs", (1,4))
@pytest.mark.parametrize("button", (1,3))
def test_end_handle_keeps_playing_position_and_applies_end_in_same_stream(session, monkeypatch, inputs, button):
    app=session.app;prepare(app,monkeypatch)
    if inputs==4:
        app.stem_paths={stem:app.source_wav for stem in app.stem_vars}
        app.stem_range=(0,6)
    select(app,1,5.5);click(app,2.5,state=8)
    app.fade_in_var.set(.1);app.fade_out_var.set(.2)
    app._refresh_action_states();app.toggle_playback()
    pump_until(app,lambda:app.realtime_processes and app.realtime_processes.position_seconds()>.12)
    owner=app.realtime_processes;player=owner.player
    for old_end,new_end in ((5.5,5),(5,5.5)):
        before=owner.playback_position().position_seconds
        revision=owner.applied_seek_revision
        drag(app,x_at(app,old_end),x_at(app,new_end),state=8,button=button)
        assert app.preview_playing and app.realtime_processes is owner and owner.player is player
        pump_until(app,lambda:owner.applied_seek_revision>revision and not owner.playback_position().seeking)
        app._update_playback_position()
        position=owner.playback_position()
        assert position.position_seconds>=before-.03
        assert position.start_seconds+position.duration_seconds==pytest.approx(new_end,abs=.01)
        assert owner._settings['fade_bounds']==pytest.approx((1,new_end),abs=.01)
        assert owner._settings['fade_in']==.1 and owner._settings['fade_out']==.2
        assert player.poll() is None and not owner.error and not owner.take_seek_error()
    assert not session.callback_errors


@pytest.mark.parametrize("lock_state", (0, 0x08, 0x02|0x08|0x20))
def test_lock_keys_keep_handles_shift_selection_and_bracket_marking(session, lock_state):
    app=session.app
    select(app,1,5);click(app,3,state=lock_state)
    for endpoint,target,expected in ((1,2,(2,5)),(5,4,(2,4))):
        cursor=app.playback_position_var.get()
        click(app,endpoint,state=lock_state)
        assert app.playback_position_var.get()==cursor
        before=app._selection_bounds()
        drag(app,x_at(app,endpoint),x_at(app,target),state=lock_state)
        assert app._selection_bounds()==pytest.approx(expected,abs=.01)
        assert app.playback_position_var.get()==cursor
        app.undo_edit();assert app._selection_bounds()==before
        app.redo_edit();assert app._selection_bounds()==pytest.approx(expected,abs=.01)
    grip=app._wave_selection.grip();x,y=(grip[0]+grip[2])/2,(grip[1]+grip[3])/2
    drag(app,x,x+app.wave_canvas.winfo_width()/6,y,state=lock_state)
    assert app._selection_bounds()==pytest.approx((3,5),abs=.01)
    click(app,1,state=lock_state);click(app,4,state=lock_state|1)
    assert app._selection_bounds()==pytest.approx((1,4),abs=.01)
    click(app,2,state=lock_state)
    for event in ("<KeyPress-bracketleft>","<KeyRelease-bracketleft>"):
        app.event_generate(event,state=lock_state)
    assert app._selection_bounds()==pytest.approx((2,4),abs=.01)
    assert not app._history_dragging and not session.callback_errors


@pytest.mark.parametrize("modifier", (0x04, 0x10))
def test_control_and_windows_alt_still_exclude_range_gestures(session, modifier):
    app=session.app;select(app,1,5)
    drag(app,x_at(app,1),x_at(app,2),state=modifier|0x08)
    assert app._selection_bounds()==(1,5)
    assert app.playback_position_var.get()==pytest.approx(2,abs=.01)
    click(app,4,state=modifier|0x08|1)
    assert app._selection_bounds()==(1,5)
    with patch.object(app._wave_selection,"mark") as mark:
        for event in ("<KeyPress-bracketleft>","<KeyRelease-bracketleft>"):
            app.event_generate(event,state=modifier|0x08)
        mark.assert_not_called()


def test_click_shift_click_and_repeated_shift_use_one_fixed_anchor_and_undo(session):
    app=session.app
    select(app,0,6)
    click(app,2)
    assert app._selection_bounds()==(0,6)
    for endpoint, expected in ((4,(2,4)),(5,(2,5)),(1,(1,2))):
        click(app,endpoint,state=1)
        assert app._selection_bounds()==pytest.approx(expected,abs=.01)
        assert app.playback_position_var.get()==pytest.approx(2,abs=.01)
    app.undo_edit();assert app._selection_bounds()==pytest.approx((2,5),abs=.01)
    app.undo_edit();assert app._selection_bounds()==pytest.approx((2,4),abs=.01)
    app.redo_edit();assert app._selection_bounds()==pytest.approx((2,5),abs=.01)
    assert not app._history_dragging and not session.callback_errors


def test_shift_anchor_uses_source_time_across_zoom_and_not_a_previous_file(session):
    app=session.app
    click(app,2)
    app.view_start,app.view_end=1,5;app.draw_waveform()
    click(app,4,state=1)
    assert app._selection_bounds()==pytest.approx((2,4),abs=.01)
    with patch.object(app,"session_name","another-session"):
        app._set_playback_position(3)
        click(app,4.5,state=1)
        assert app._selection_bounds()==pytest.approx((3,4.5),abs=.01)


def test_shift_click_clamps_to_complete_stems_and_can_recover_point_selection(session):
    app=session.app
    select(app,2,2)
    click(app,1);click(app,3,state=1)
    assert app._selection_bounds()==pytest.approx((1,3),abs=.01)
    app.stem_paths={stem:app.source_wav for stem in app.stem_vars}
    app.stem_range=(2.004,4.006)
    select(app,2.5,3.5)
    click(app,0);click(app,6,state=1)
    assert app._selection_bounds()==pytest.approx((2.004,4.006))
    app.undo_edit();assert app._selection_bounds()==(2.5,3.5)


@pytest.mark.parametrize("endpoint,target,expected",((1,2,(2,5)),(5,4,(1,4))))
def test_left_boundary_drag_changes_only_range_and_is_one_undo(session,endpoint,target,expected):
    app=session.app
    select(app,1,5)
    with patch.object(app,"_wave_seek_begin") as seek:
        drag(app,x_at(app,endpoint)+6,x_at(app,target)+6)
        seek.assert_not_called()
    assert app._selection_bounds()==pytest.approx(expected,abs=.01)
    app.undo_edit();assert app._selection_bounds()==(1,5)
    app.redo_edit();assert app._selection_bounds()==pytest.approx(expected,abs=.01)
    assert not app.playback_seek_dragging and app._wave_selection.drag is None


def test_left_grip_move_preserves_length_tap_keeps_cursor_and_shift_over_grip_selects(session):
    app=session.app
    select(app,1,3)
    grip=app._wave_selection.grip();x,y=(grip[0]+grip[2])/2,(grip[1]+grip[3])/2
    drag(app,x,x+app.wave_canvas.winfo_width()/6,y)
    assert app._selection_bounds()==pytest.approx((2,4),abs=.01)
    cursor=app.playback_position_var.get()
    click(app,3,y=round(y))
    assert app.playback_position_var.get()==cursor
    assert app._selection_bounds()==pytest.approx((2,4),abs=.01)
    click(app,1)
    click(app,3,state=1,y=round(y))
    assert app._selection_bounds()==pytest.approx((1,3),abs=.01)


def test_small_motion_on_handle_does_not_edit_or_seek(session):
    app=session.app
    select(app,1,5)
    click(app,3)
    drag(app,x_at(app,1),x_at(app,1)+1)
    assert app._selection_bounds()==(1,5)
    assert app.playback_position_var.get()==3
    assert app._wave_selection.left_action is None


def test_body_drag_stays_seek_when_crossing_a_boundary_and_updates_shift_anchor(session):
    app=session.app
    select(app,1,5)
    drag(app,x_at(app,2),x_at(app,5.5))
    assert app._selection_bounds()==(1,5)
    assert app.playback_position_var.get()==pytest.approx(5.5,abs=.01)
    click(app,4,state=1)
    assert app._selection_bounds()==pytest.approx((4,5.5),abs=.01)


def test_left_handle_drag_pans_zoomed_view_and_releases_cleanly(session):
    app=session.app
    select(app,1.5,2.5,(1,3))
    canvas=app.wave_canvas
    canvas.event_generate("<ButtonPress-1>",x=x_at(app,2.5),y=50)
    canvas.event_generate("<B1-Motion>",x=canvas.winfo_width()+60,y=50)
    pump_until(app,lambda:app.view_start>1.1)
    canvas.event_generate("<ButtonRelease-1>",x=canvas.winfo_width()+60,y=50)
    assert app._selection_bounds()[0]==1.5 and app._selection_bounds()[1]>3
    assert app._wave_selection.pan_after is None and app._wave_selection.left_action is None


def test_busy_empty_and_modifier_clicks_do_not_start_selection(session):
    app=session.app
    select(app,1,5)
    app.busy=True;click(app,3,state=1);assert app._selection_bounds()==(1,5)
    app.busy=False
    with patch.object(app,"duration_seconds",0):
        click(app,0,state=1)
    assert app._selection_bounds()==(1,5)
    click(app,2,state=5)  # Ctrl+Shift retains ordinary seek behavior.
    assert app._selection_bounds()==(1,5)


@pytest.mark.parametrize("inputs",(1,4))
def test_shift_click_while_playing_retains_stream_and_uses_fixed_seek_anchor(session,monkeypatch,inputs):
    app=session.app;prepare(app,monkeypatch)
    if inputs==4:
        app.stem_paths={stem:app.source_wav for stem in app.stem_vars}
        app.stem_range=(0,6)
    click(app,1)
    app._refresh_action_states();app.toggle_playback()
    pump_until(app,lambda:app.realtime_processes and app.realtime_processes.position_seconds()>.2)
    owner=app.realtime_processes
    click(app,4,state=1)
    assert app._selection_bounds()==pytest.approx((1,4),abs=.01)
    clock=owner.position_seconds()
    pump_until(app,lambda:owner.position_seconds()>clock+.2)
    click(app,5,state=1)
    assert app._selection_bounds()==pytest.approx((1,5),abs=.01)
    assert app.preview_playing and app.realtime_processes is owner
    assert owner.player.poll() is None and owner._settings["fade_bounds"]==(0,6)
    app.toggle_playback();app.toggle_playback()
    pump_until(app,lambda:app.realtime_processes and app.realtime_processes is not owner)
    assert app.realtime_processes._settings["fade_bounds"]==app._selection_bounds()
    assert not session.callback_errors
