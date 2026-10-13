"""Mixer gestures, silent transport and error recovery in isolated real Tk."""
import time

import pytest

from test_audit_audio import session
from test_spectrum_ui import prepare, current_frame, pump_until


def prepare_stems(app,monkeypatch):
    prepare(app,monkeypatch)
    app.stem_paths={name:app.source_wav for name in app.stem_vars}
    app.stem_range=(0,app.duration_seconds)
    app._refresh_action_states();app.update()


def wait_weights(app,owner,expected):
    pump_until(app,lambda:owner.eq_controller._mixer_current==expected
               and owner.eq_controller.mixer_applied_revision==owner.eq_controller.mixer_revision)
    assert app.realtime_processes is owner and not app.live_restart_after_id
    assert all(p.poll() is None for p in owner) and not owner.eq_controller.error


def test_all_muted_start_unmute_solo_precedence_and_pause(session,monkeypatch):
    app=session.app;prepare_stems(app,monkeypatch)
    for values in app.stem_vars.values():values["mute"].set(True)
    app.toggle_playback();frame=current_frame(app);owner=app.realtime_processes
    assert max(frame.levels)<=-89.9
    clock=owner.position_seconds()
    app.stem_vars["vocals"]["mute"].set(False)
    wait_weights(app,owner,(1,0,0,0))
    pump_until(app,lambda:app.eq_editor._spectrum_frame and max(app.eq_editor._spectrum_frame.levels)>-25)
    # A muted Solo track silences the mix, as before; transport now continues.
    app.stem_vars["drums"]["solo"].set(True)
    wait_weights(app,owner,(0,0,0,0))
    pump_until(app,lambda:app.eq_editor._spectrum_frame and max(app.eq_editor._spectrum_frame.levels)<=-89.9)
    app.stem_vars["drums"]["mute"].set(False)
    wait_weights(app,owner,(0,1,0,0))
    assert owner.position_seconds()>clock
    app.stem_vars["drums"]["volume"].set(25)
    assert app._live_mixer_after_id
    app.stop_preview(False)
    assert not app._live_mixer_after_id and not app.live_restart_after_id
    assert not owner.eq_controller._thread.is_alive() and not session.callback_errors


def test_fader_held_drag_and_ctrl_reset_apply_without_restart(session,monkeypatch):
    app=session.app;prepare_stems(app,monkeypatch)
    app.deiconify();app.geometry("1000x700");app.update()
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    fader=app.stem_widgets["vocals"][0]
    x,y=fader.winfo_width()//2,round(fader.winfo_height()*.5)
    fader.event_generate("<ButtonPress-1>",x=x,y=y)
    for i in range(16):
        fader.event_generate("<B1-Motion>",x=x,y=y+i*3)
        until=time.monotonic()+.025
        while time.monotonic()<until:app.update();time.sleep(.004)
        assert app.realtime_processes is owner and not app.live_restart_after_id
    assert fader.dragging and owner.eq_controller.mixer_revision>=10
    assert owner.eq_controller._mixer_current[0]!=1
    fader.event_generate("<ButtonRelease-1>",x=x,y=y+45)
    fader.event_generate("<ButtonPress-1>",state=4,x=x,y=y)
    fader.event_generate("<ButtonRelease-1>",state=4,x=x,y=y)
    wait_weights(app,owner,(1,1,1,1))
    assert app.stem_vars["vocals"]["volume"].get()==100
    assert not session.callback_errors


@pytest.mark.parametrize("missing_client",[False,True])
def test_mixer_control_failure_and_missing_client_use_recovery(session,monkeypatch,missing_client):
    app=session.app;prepare_stems(app,monkeypatch)
    if missing_client:
        monkeypatch.setattr("backend.audio_processing.ffmpeg_tools.live_eq_available",lambda:False)
        # Idle playback may already be prepared with an available EQ client.
        # Apply the injected environment to a fresh decoder, including workers
        # that started before this patch was installed.
        app._warm_transport.cancel(wait=True)
    app.toggle_playback();current_frame(app);owner=app.realtime_processes
    if missing_client:assert owner.eq_controller is None
    if not missing_client:
        def fail(*args):raise TimeoutError("injected mixer command failure")
        monkeypatch.setattr(owner.eq_controller,"_command",fail)
    app.stem_vars["vocals"]["solo"].set(True)
    app.stem_vars["vocals"]["volume"].set(50)
    current_frame(app,owner)
    assert all(p.poll() is not None for p in owner)
    assert [s.gain for s in app.last_preview_stems]==[.5,0,0,0]
    assert not session.callback_errors
