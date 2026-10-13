"""Space controls real audio without an unrelated layout/effect redraw."""
from unittest.mock import patch

from test_audit_audio import assert_empty_header, session
from test_spectrum_ui import current_frame,prepare,pump_until


def test_play_pause_updates_transport_without_relayout_and_retains_resume_position(session,monkeypatch):
    app=session.app;prepare(app,monkeypatch)
    app.deiconify();app.focus_force();app.update()
    app.eq_mid_var.set(-6)
    app.stem_paths={name:app.source_wav for name in ("vocals","drums","bass","other")}
    app.stem_range=(0,app.duration_seconds)
    app.stem_vars["vocals"]["solo"].set(True);app.stem_vars["vocals"]["volume"].set(50)
    app._refresh_action_states();app._commit_edit();app.update()
    pump_until(app,lambda:not app.waveform_resize_after_id and not app.waveform_fade_after_id
               and not app._layout_after and not app._compact_after)
    selection=app._selection_bounds();edits=app._edit_snapshot()
    with patch.object(app,"_layout_compact",wraps=app._layout_compact) as layout, \
         patch.object(app,"draw_waveform",wraps=app.draw_waveform) as waveform, \
         patch.object(app.eq_editor,"draw",wraps=app.eq_editor.draw) as eq:
        def space():
            app.event_generate("<KeyPress-space>");app.event_generate("<KeyRelease-space>");app.update()
        space();current_frame(app);owner=app.realtime_processes
        assert app.play_button.cget("text")=="Pause"
        assert app.play_button.icon_name=="pause"
        pump_until(app,lambda:owner.position_seconds()>.45)
        space();cursor=app.playback_position_var.get()
        assert not app.preview_playing and app.play_button.cget("text")=="Play"
        assert cursor>0 and owner.player.poll() is None and owner.player.paused
        assert not app.eq_editor.find_withtag("spectrum")
        space();current_frame(app)
        assert app.realtime_processes is owner and not owner.player.paused
        assert app.playback_position_var.get()>=cursor
        assert app._selection_bounds()==selection and app._edit_snapshot()==edits
        assert app.realtime_processes.eq_controller._mixer_desired==(.5,0,0,0)
        assert app.realtime_processes.eq_controller._desired[("equalizer@kw_mid","g")]==-6
        layout.assert_not_called();waveform.assert_not_called();eq.assert_not_called()
    assert not session.callback_errors


def test_context_errors_and_progress_remain_visible_without_editor_relayout(session):
    app=session.app;app.deiconify();app.update()
    widgets=(app.wave_canvas,app.eq_panel,app.mixer_panel)
    shape=lambda:tuple((w.winfo_x(),w.winfo_y(),w.winfo_width(),w.winfo_height()) for w in widgets)
    original=shape()
    with patch.object(app,"_layout_compact",wraps=app._layout_compact) as layout:
        app.status_var.set("Could not read the selected audio.");app.update()
        assert app.status_label.winfo_ismapped() and shape()==original
        app.busy=True;app.status_var.set("Preparing audio...");app._refresh_action_states();app.update()
        assert app.cancel_button.winfo_ismapped() and app.status_label.winfo_ismapped()
        assert shape()==original
        app.busy=False;app.status_var.set("");app._refresh_action_states();app.update()
        assert not app.cancel_button.winfo_ismapped()
        assert app.status_label.winfo_ismapped()
        assert_empty_header(app)
        assert app.play_button.enabled and shape()==original
        layout.assert_not_called()
