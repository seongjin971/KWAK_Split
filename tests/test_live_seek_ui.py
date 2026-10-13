"""Waveform gestures through real Tk with generated audio and SDL dummy."""
import time
import pytest

from test_audit_audio import session
from test_spectrum_ui import current_frame, prepare, pump_until


def pump(app, seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.update();time.sleep(.005)


def click(app, seconds):
    x=round(app.wave_canvas.winfo_width()*seconds/app.duration_seconds)
    app.wave_canvas.event_generate("<Button-1>",x=x,y=40)
    app.wave_canvas.event_generate("<ButtonRelease-1>",x=x,y=40)
    return app._event_to_seconds(type("Point",(),{"x":x})())


def test_click_and_held_left_drag_seek_before_release_without_restart(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes;player=owner.player
    selected=app._selection_bounds()
    target=click(app,3)
    assert app.playback_position_var.get()==target
    pump_until(app,lambda:app.playback_start_seconds==target)
    assert owner.playback_position().revision==1 and app.realtime_processes is owner
    canvas=app.wave_canvas;width=canvas.winfo_width()
    canvas.event_generate("<Button-1>",x=round(width*.2),y=40)
    for step in range(20):
        x=round(width*(.2+.018*step))
        canvas.event_generate("<B1-Motion>",x=x,y=40)
        pump(app,.045)
    assert app.playback_seek_dragging
    assert owner.applied_seek_revision>=3  # Actual handoffs while still held.
    assert app.realtime_processes is owner and owner.player is player and player.poll() is None
    canvas.event_generate("<ButtonRelease-1>",x=x,y=40)
    target=app._event_to_seconds(type("Point",(),{"x":x})())
    pump_until(app,lambda:not owner.playback_position().seeking)
    pump_until(app,lambda:app.playback_start_seconds==target)
    assert app._selection_bounds()==selected
    assert not app.live_restart_after_id and not session.callback_errors
    assert not owner.error and not owner.take_seek_error()


def test_seek_keeps_latest_eq_solo_gain_and_selection_fades(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
    app.stem_range=(0,app.duration_seconds)
    app.selection_start_var.set(1);app.selection_end_var.set(5.5)
    app.fade_in_var.set(.2);app.fade_out_var.set(.3)
    app.stem_vars["vocals"]["solo"].set(True);app.stem_vars["vocals"]["volume"].set(50)
    app.eq_mid_var.set(-6);app._refresh_action_states();app.toggle_playback()
    flat=max(current_frame(app).levels);owner=app.realtime_processes
    target=click(app,3.2)
    pump_until(app,lambda:app.playback_start_seconds==target)
    pump_until(app,lambda:(f:=owner.spectrum_frame()) and abs(max(f.levels)-flat)<.25)
    assert app.realtime_processes is owner
    assert owner._settings["fade_bounds"]==(1,5.5)
    assert owner.eq_controller._mixer_desired==(.5,0,0,0)
    assert owner.eq_controller._desired[("equalizer@kw_mid","g")]==-6
    # Changes suppressed by the held-seek guard must flush on release.
    canvas=app.wave_canvas;x=round(canvas.winfo_width()*.5)
    canvas.event_generate("<Button-1>",x=x,y=40)
    app.eq_mid_var.set(-9);app.stem_vars["vocals"]["volume"].set(25)
    canvas.event_generate("<ButtonRelease-1>",x=x,y=40)
    pump_until(app,lambda:not owner.playback_position().seeking and
               owner.eq_controller._current[("equalizer@kw_mid","g")]==-9 and
               owner.eq_controller._mixer_current==(.25,0,0,0))
    # Existing out-of-selection behavior returns to selection start.
    click(app,.1);pump_until(app,lambda:app.playback_start_seconds==1)
    app.stop_preview(False);position=app.playback_position_var.get()
    pump(app,.15)
    assert not app.preview_playing and app.playback_position_var.get()==position
    assert all(not t.is_alive() for t in owner._threads) and not session.callback_errors


def test_paused_seek_and_right_drag_selection_keep_current_position(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    target=click(app,2)
    assert not app.preview_playing and app.playback_position_var.get()==target
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    before=owner.playback_position().position_seconds;revision=owner.applied_seek_revision
    canvas=app.wave_canvas;width=canvas.winfo_width()
    canvas.event_generate("<Button-3>",x=round(width*.2),y=40)
    canvas.event_generate("<B3-Motion>",x=round(width*.8),y=40)
    canvas.event_generate("<ButtonRelease-3>",x=round(width*.8),y=40)
    assert app.realtime_processes is owner
    pump_until(app,lambda:owner.applied_seek_revision>revision and not owner.playback_position().seeking)
    app._update_playback_position()
    start,end=app._selection_bounds()
    assert start==pytest.approx(1.2,abs=.01) and end==pytest.approx(4.8,abs=.01)
    assert app.playback_position_var.get()>=before-.03
    assert app.playback_start_seconds+app.playback_duration_seconds==pytest.approx(end,abs=.01)
    assert not session.callback_errors
