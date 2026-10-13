"""Prepared playback, paused edits and cancellation through real Tk and WinMM."""
import threading
import time

import pytest

from test_audit_audio import session
from test_spectrum_ui import current_frame,prepare,pump_until


def cached(app):
    item=app._warm_transport._cached
    return item[1] if item and item[0]==app._prepared_request() and item[1].player.queued_seconds>.05 else None


def test_paused_eq_mixer_seek_and_speed_use_fresh_pcm_on_the_same_device(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
    app.stem_range=(0,app.duration_seconds);app._refresh_action_states()
    app.toggle_playback();flat=max(current_frame(app).levels);first=app.realtime_processes
    device=app._warm_transport.device;handle=device.handle
    app.toggle_playback();cursor=app.playback_position_var.get()
    app.eq_mid_var.set(-9);app.stem_vars["vocals"]["solo"].set(True)
    app.stem_vars["vocals"]["volume"].set(50)
    prepared=pump_until(app,lambda:(p if (p:=cached(app)) and p is not first else None))
    assert not app.preview_playing and app.playback_position_var.get()==cursor
    assert prepared.player.position_seconds()==0 and prepared.player.paused
    app.toggle_playback();quiet=max(current_frame(app).levels)
    assert quiet-flat==pytest.approx(-27.0618,abs=.2)
    assert app._warm_transport.device is device and device.handle==handle
    assert all(p.poll() is not None for p in first)
    app.toggle_playback()
    app.playback_cursor_manual=True;app._set_playback_position(2.5)
    app.tempo_percent_var.set(200)
    app.toggle_playback();current_frame(app)
    assert app.playback_start_seconds==2.5 and app.playback_tempo_ratio==2
    assert app.realtime_processes._settings["stems"][0].gain==.5
    assert device.handle==handle and not session.callback_errors


def test_play_and_cancel_during_preparation_never_blocks_or_starts_late_audio(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    entered=threading.Event();release=threading.Event();owners=[]
    original=app._warm_transport._factory
    def slow(**kwargs):
        entered.set();assert release.wait(3)
        owner=original(**kwargs);owners.append(owner);return owner
    monkeypatch.setattr(app._warm_transport,"_factory",slow)
    app._warm_transport.cancel(wait=True)
    app.eq_mid_var.set(-6)
    started=time.perf_counter();app.toggle_playback();elapsed=time.perf_counter()-started
    assert elapsed<.08 and app._pending_playback and app.preview_playing
    pump_until(app,entered.is_set)
    cursor=app.playback_position_var.get()
    started=time.perf_counter();app.toggle_playback();elapsed=time.perf_counter()-started
    assert elapsed<.08 and not app.preview_playing and not app._pending_playback
    release.set()
    pump_until(app,lambda:cached(app))
    assert app.playback_position_var.get()==cursor
    assert all(p.player.paused or p.player.poll() is not None for p in owners)
    assert not session.callback_errors


def test_rapid_space_cycles_leave_one_silent_prepared_session(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    pump_until(app,lambda:cached(app));app.deiconify();app.focus_force();app.update()
    device=app._warm_transport.device;handle=device.handle
    for _ in range(20):
        app.event_generate("<KeyPress-space>");app.event_generate("<KeyRelease-space>");app.update()
    assert not app.preview_playing and not app._pending_playback
    owner=pump_until(app,lambda:cached(app));position=app.playback_position_var.get()
    deadline=time.monotonic()+.15
    pump_until(app,lambda:time.monotonic()>=deadline)
    assert app.playback_position_var.get()==position and owner.player.paused
    assert device.handle==handle and not session.callback_errors


def test_preparation_error_is_contextual_and_play_can_recover(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch);manager=app._warm_transport
    original=manager._factory
    def fail(**kwargs):raise OSError("injected preparation error")
    manager.cancel(wait=True);monkeypatch.setattr(manager,"_factory",fail)
    app.eq_mid_var.set(-3)
    pump_until(app,lambda:manager._failure)
    app.toggle_playback()  # Includes an already-failed idle preparation.
    assert not app.preview_playing and not app._pending_playback
    assert "Could not start playback" in app.status_var.get()
    assert app.status_label.winfo_ismapped() or not app.winfo_viewable()
    monkeypatch.setattr(manager,"_factory",original)
    app.eq_mid_var.set(-6);app.toggle_playback();current_frame(app)
    assert app.preview_playing and not session.callback_errors


def test_output_write_failure_closes_stream_and_reopens_device_on_next_play(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch);pump_until(app,lambda:cached(app))
    app.toggle_playback();current_frame(app)
    device=app._warm_transport.device
    def fail(_pcm):raise OSError("injected device write error")
    monkeypatch.setattr(device._driver,"write",fail)
    pump_until(app,lambda:not app.preview_playing)
    assert "failed" in app.status_var.get().lower()
    app.toggle_playback();current_frame(app)
    assert app._warm_transport.device is not device and device._closed
    assert not app.realtime_processes.error and not session.callback_errors


def test_new_project_releases_prepared_decoder_before_working_audio_cleanup(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch);owner=pump_until(app,lambda:cached(app))
    working=app.source_wav
    app.cleanup_current_temp();app.update()
    assert not working.exists() and app.source_wav is None and not app.preview_playing
    assert all(p.poll() is not None for p in owner)
    assert not app._warm_transport._cached and not session.callback_errors
