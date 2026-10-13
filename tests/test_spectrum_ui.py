"""Real Tk and real silent playback: edits, seeks, loops and mixer changes."""
import time
from unittest.mock import patch

import pytest

from backend.audio_processing.ffmpeg_tools import ToolMissingError
from test_audit_audio import session


def pump_until(app, predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.update()
        value=predicate()
        if value:return value
        time.sleep(.01)
    raise AssertionError("No live spectrum state before timeout")


def current_frame(app, previous=None):
    def ready():
        frame=app.eq_editor._spectrum_frame
        return frame if (app.preview_playing and app.eq_editor._spectrum_owner is app.realtime_processes
                         and app.realtime_processes is not previous and frame and frame.seconds>.22) else None
    return pump_until(app,ready)


def prepare(app,monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER","dummy")
    app.loop_var.set(False)
    app.fade_in_var.set(0);app.fade_out_var.set(0)
    app.limiter_enabled_var.set(False)
    app.eq_mid_freq_var.set(440)
    app.update()


def test_eq_edits_keep_stream_then_pause_seek_and_source_change_clear_spectrum(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();flat=current_frame(app)
    assert app.eq_editor.find_withtag("spectrum")
    assert set(app.eq_editor.handles)=={"low","mid","high"}
    previous=app.realtime_processes
    def changed(delta):
        def ready():
            frame=app.eq_editor._spectrum_frame
            return frame if frame and abs(max(frame.levels)-max(flat.levels)-delta)<.15 else None
        return pump_until(app,ready)
    app.eq_mid_var.set(12);boost=changed(12)
    assert max(boost.levels)-max(flat.levels)==pytest.approx(12,abs=.15)
    assert app.realtime_processes is previous and all(process.poll() is None for process in previous)
    app.eq_mid_var.set(-12);cut=changed(-12)
    assert max(cut.levels)-max(flat.levels)==pytest.approx(-12,abs=.15)
    assert app.realtime_processes is previous and not app.live_restart_after_id
    app.toggle_playback()
    assert not app.eq_editor.find_withtag("spectrum")
    assert app.eq_editor._spectrum_frame is None
    app.toggle_playback();current_frame(app)
    previous=app.realtime_processes
    player=previous.player
    app.playback_cursor_manual=True
    app._set_playback_position(3);app._restart_preview_from_cursor()
    pump_until(app,lambda:app.playback_start_seconds==pytest.approx(3))
    current_frame(app)
    assert app.realtime_processes is previous and previous.player is player
    assert not previous.playback_position().seeking
    assert app.playback_start_seconds==pytest.approx(3)
    app.load_audio_path(session.source);session.wait_idle()
    assert not app.preview_playing and app.eq_editor._spectrum_frame is None
    assert not session.callback_errors


def test_mixer_mute_solo_and_gain_change_the_spectrum(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    # Four identical generated stems make the expected mix-level changes exact.
    app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
    app.stem_range=(0,app.duration_seconds)
    for values in app.stem_vars.values():values["volume"].set(100)
    app._refresh_action_states();app.toggle_playback();full=current_frame(app)
    owner=app.realtime_processes
    def changed(delta):
        def ready():
            frame=app.eq_editor._spectrum_frame
            return frame if frame and abs(max(frame.levels)-max(full.levels)-delta)<.15 else None
        result=pump_until(app,ready)
        assert app.realtime_processes is owner and not app.live_restart_after_id
        return result
    app.stem_vars["vocals"]["solo"].set(True)
    solo=changed(-12.0412)
    assert max(solo.levels)-max(full.levels)==pytest.approx(-12.0412,abs=.15)
    app.stem_vars["vocals"]["volume"].set(50)
    quiet=changed(-18.0618)
    assert max(quiet.levels)-max(solo.levels)==pytest.approx(-6.0206,abs=.15)
    app.stem_vars["vocals"]["solo"].set(False)
    app.stem_vars["vocals"]["volume"].set(100)
    app.stem_vars["vocals"]["mute"].set(True)
    muted=changed(-2.4988)
    assert max(muted.levels)-max(full.levels)==pytest.approx(-2.4988,abs=.15)
    assert all(p.poll() is None for p in owner) and not owner.eq_controller.error


def test_loop_replaces_analyzer_and_fallback_uses_rendered_file(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.selection_start_var.set(1);app.selection_end_var.set(1.7);app.loop_var.set(True)
    app.toggle_playback();current_frame(app)
    first=app.realtime_processes
    pump_until(app,lambda:app.preview_playing and app.realtime_processes is not first,timeout=4)
    assert all(process.poll() is not None for process in first)
    app.stop_preview(False)
    app.loop_var.set(False);app.selection_start_var.set(0);app.selection_end_var.set(4)
    with patch("StemSamplePrep.start_realtime_mix",side_effect=ToolMissingError("test fallback")), \
            patch("StemSamplePrep.winsound.PlaySound"):
        app.playback_cursor_manual=False;app.toggle_playback();session.wait_idle()
        pump_until(app,lambda:app.eq_editor._spectrum_frame)
        assert app.current_preview_file.is_file() and app._file_spectrum is not None
        decoder=app._file_spectrum
        app.stop_preview(False)
        assert app._file_spectrum is None and all(p.poll() is not None for p in decoder)
        assert not app.eq_editor.find_withtag("spectrum")


def test_close_during_playback_releases_audio_and_fft_threads(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();current_frame(app)
    playback=app.realtime_processes
    # The same nonblocking close used by on_close must release all workers.
    playback.close(wait=False)
    pump_until(app,lambda:all(p.poll() is not None for p in playback))
    pump_until(app,lambda:all(not t.is_alive() for t in playback._threads)
               and not playback.spectrum._thread.is_alive())
    pump_until(app,lambda:not playback.eq_controller._thread.is_alive())


def test_continuous_eq_drag_applies_before_release_and_pause_cancels_pending(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    app._begin_edit_drag()
    for i in range(16):
        app.eq_mid_var.set(i*.5)
        app.eq_mid_freq_var.set(440+i*8)
        app.eq_mid_q_var.set(.8+i*.025)
        until=time.monotonic()+.025
        while time.monotonic()<until:app.update();time.sleep(.004)
        assert app.realtime_processes is owner and not app.live_restart_after_id
    assert owner.eq_controller.revision >= 10
    assert owner.eq_controller._current[("equalizer@kw_mid","g")] > 0
    app._end_edit_drag()
    pump_until(app,lambda:owner.eq_controller.applied_revision==owner.eq_controller.revision)
    app.eq_mid_var.set(0)
    assert app._live_eq_after_id
    app.stop_preview(False)
    assert not app._live_eq_after_id and not app.live_restart_after_id
    assert not owner.eq_controller._thread.is_alive()
    app.update()
    assert not app.preview_playing and not session.callback_errors


def test_eq_control_failure_reapplies_latest_values_once(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    def fail(*args):raise TimeoutError("injected live EQ failure")
    monkeypatch.setattr(owner.eq_controller,"_command",fail)
    app.eq_mid_var.set(6)
    current_frame(app,owner)
    assert not owner.eq_controller._thread.is_alive()
    assert app.realtime_processes.eq_controller._current[("equalizer@kw_mid","g")] == 6
    assert not session.callback_errors


def test_missing_optional_command_client_uses_existing_restart_path(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    monkeypatch.setattr("backend.audio_processing.ffmpeg_tools.live_eq_available",lambda:False)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    assert owner.eq_controller is None
    app.eq_mid_var.set(6)
    current_frame(app,owner)
    assert all(p.poll() is not None for p in owner)
    assert not session.callback_errors


@pytest.mark.parametrize("band,index,mode",[("low",0,"High Pass"),("high",1,"Low Pass")])
def test_mode_menu_slope_knob_and_ctrl_reset_keep_playback(session,monkeypatch,band,index,mode):
    app=session.app;prepare(app,monkeypatch)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    clock=owner.position_seconds()
    combo=app.eq_shape_widgets[index];shelf=combo.get()
    knob=app.compact_knobs[band]

    def settled(previous):
        pump_until(app,lambda:owner.eq_controller.revision>previous
                   and owner.eq_controller.applied_revision==owner.eq_controller.revision)
        assert app.realtime_processes is owner and not app.live_restart_after_id
        assert all(p.poll() is None for p in owner) and not owner.eq_controller.error

    revision=owner.eq_controller.revision
    combo.set(mode);combo.event_generate("<<ComboboxSelected>>")
    settled(revision)
    for delta,expected in ((120,36),(120,48),(-120,36),(-120,24),(-120,12)):
        revision=owner.eq_controller.revision
        knob.event_generate("<MouseWheel>",delta=delta)
        settled(revision)
        assert app._band_value(band)==expected
    revision=owner.eq_controller.revision
    knob.event_generate("<Button-1>",state=0x4,x=10,y=10)
    knob.event_generate("<ButtonRelease-1>",state=0x4,x=10,y=10)
    settled(revision)
    assert app._band_value(band)==24
    revision=owner.eq_controller.revision
    combo.set(shelf);combo.event_generate("<<ComboboxSelected>>")
    settled(revision)
    assert owner.position_seconds()>clock and not session.callback_errors
