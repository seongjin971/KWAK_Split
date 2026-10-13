"""Real Tk gesture regressions using isolated, generated-audio workspaces."""
import itertools
import re
import tkinter as tk
from tkinter import ttk

import pytest

import test_workspace


_times = itertools.count(100000, 1000)


@pytest.fixture
def session():
    case = test_workspace.WorkspaceTests()
    case.setUp()
    try:
        yield case
        assert not case.callback_errors, case.callback_errors
    finally:
        case.tearDown()


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


def entry_for(app, variable):
    return next(widget for widget, _, value, _ in app._numeric_fields if value is variable)


def drag(app, widget, dy, *, shift=False):
    """Positive dy means up; send two motions to exercise grouped history."""
    app.update()
    x, y = min(12, widget.winfo_width() // 2), max(3, widget.winfo_height() // 2)
    rx, ry = widget.winfo_rootx() + x, widget.winfo_rooty() + y
    stamp = next(_times)
    state = 1 if shift else 0
    widget.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx, rooty=ry,
                          state=state, time=stamp)
    for offset, amount in ((50, round(dy / 2)), (100, dy)):
        widget.event_generate("<B1-Motion>", x=x, y=y-amount, rootx=rx, rooty=ry-amount,
                              state=state | 0x100, time=stamp+offset)
        app.update()
    widget.event_generate("<ButtonRelease-1>", x=x, y=y-dy, rootx=rx, rooty=ry-dy,
                          state=state, time=stamp+150)
    app.update()


def click(app, widget, *, double=False, arrow=False, ctrl=False, numlock=False):
    app.update()
    x = widget.winfo_width()-5 if arrow else min(12, widget.winfo_width() // 2)
    y = max(3, widget.winfo_height() // 2)
    stamp = next(_times)
    state = (4 if ctrl else 0) | (8 if numlock else 0)
    for offset in ((0, 100) if double else (0,)):
        widget.event_generate("<ButtonPress-1>", x=x, y=y, state=state, time=stamp+offset)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y, state=state, time=stamp+offset+20)
    app.update()


def wheel(app, widget, delta, *, shift=False):
    widget.event_generate("<MouseWheel>", delta=delta, state=1 if shift else 0,
                          x=8, y=max(3, widget.winfo_height() // 2), time=next(_times))
    app.update()


def test_time_wheel_tracks_zoom_delta_shift_and_two_decimal_display(session):
    app = session.app
    start = app.start_spinbox
    app.view_start, app.view_end = 0, app.duration_seconds
    app.selection_start_var.set(1)
    app.update()
    wheel(app, start, 120)
    coarse = app.selection_start_var.get() - 1
    app.selection_start_var.set(1)
    wheel(app, start, 240)
    assert app.selection_start_var.get() == pytest.approx(1 + 2 * coarse)
    app.selection_start_var.set(1)
    wheel(app, start, 120, shift=True)
    shifted = app.selection_start_var.get() - 1
    assert .01 <= shifted + 1e-9 < coarse
    app.view_start, app.view_end = 1, 1.25
    app.selection_start_var.set(1)
    wheel(app, start, 120)
    fine = app.selection_start_var.get() - 1
    assert fine == pytest.approx(.01)
    assert fine < coarse
    wheel(app, start, -240)
    assert app.selection_start_var.get() == pytest.approx(.99)
    wheel(app, start, 120, shift=True)
    assert app.selection_start_var.get() == pytest.approx(1)
    for widget in (app.start_spinbox, app.end_spinbox):
        assert re.fullmatch(r"\d+\.\d{2}", widget.get())


def test_all_numeric_fields_drag_with_one_undo_and_clamp_bounds(session):
    app = session.app
    app.selection_start_var.set(1)
    app.selection_end_var.set(5)
    variables = [app.selection_start_var, app.selection_end_var,
                 app.eq_low_freq_var, app.eq_mid_freq_var, app.eq_high_freq_var,
                 app.tempo_percent_var, app.pitch_semitones_var,
                 app.fade_in_var, app.fade_out_var]
    for variable in variables:
        widget = entry_for(app, variable)
        app._commit_edit()
        original, index = variable.get(), app.history.index
        drag(app, widget, 12)
        changed = variable.get()
        assert changed > original, str(widget)
        assert app.history.index == index + 1, str(widget)
        app.undo_edit()
        assert variable.get() == pytest.approx(original), str(widget)
        app.redo_edit()
        assert variable.get() == pytest.approx(changed), str(widget)
        drag(app, widget, 30000)
        assert variable.get() == pytest.approx(float(widget.cget("to")))
        drag(app, widget, -30000)
        assert variable.get() == pytest.approx(float(widget.cget("from")))
        variable.set(original)
        app.update()

    app.open_advanced()
    app.update()
    for variable in (app.eq_mid_q_var, app.high_pass_q_var, app.low_pass_q_var):
        widget = entry_for(app, variable)
        app._commit_edit()
        original, index = variable.get(), app.history.index
        drag(app, widget, 12)
        changed = variable.get()
        assert changed > original
        assert app.history.index == index + 1
        app.undo_edit()
        assert variable.get() == pytest.approx(original)
        app.redo_edit()
        assert variable.get() == pytest.approx(changed)
        drag(app, widget, 30000)
        assert variable.get() == pytest.approx(float(widget.cget("to")))
        drag(app, widget, -30000)
        assert variable.get() == pytest.approx(float(widget.cget("from")))
        variable.set(original)
    app._close_render_settings()


def test_stem_range_clamps_typed_wheel_and_drag_edits_with_single_undo(session):
    from test_split_scope import attach_selected_stems

    app = session.app
    attach_selected_stems(session)
    app.selection_start_var.set(2.5)
    app.selection_end_var.set(3.5)
    app._commit_edit()
    before = app.history.index
    drag(app, app.end_spinbox, 30000)
    assert app._selection_bounds() == (2.5, 4)
    assert app.history.index == before + 1
    app.undo_edit()
    assert app._selection_bounds() == (2.5, 3.5)
    app.redo_edit()
    assert app._selection_bounds() == (2.5, 4)
    wheel(app, app.start_spinbox, -120000)
    assert app._selection_bounds() == (2, 4)
    display = next(display for widget, display, *_ in app._numeric_fields if widget == app.end_spinbox)
    display.set("100")
    app._commit_numeric(app.end_spinbox)
    assert app._selection_bounds() == (2, 4)
    assert app.end_spinbox.get() == "4.00"


def test_normal_click_typing_and_double_click_remain_text_editing(session):
    app, entry = session.app, session.app.fade_in_spinbox
    original = entry.get()
    click(app, entry)
    assert entry.get() == original
    # Focus belongs only to this synthetic fixture, never the running release.
    app.focus_force()
    entry.focus_set()
    entry.delete(0, "end")
    for key in ("0", "period", "0", "4"):
        entry.event_generate(f"<KeyPress-{key}>")
        entry.event_generate(f"<KeyRelease-{key}>")
        app.update()
    entry.event_generate("<Return>")
    app.update()
    assert entry.get() == "0.04"
    assert app.fade_in_var.get() == .04
    click(app, entry, double=True)
    assert entry.get() == "0.04"
    assert entry.selection_present()
    assert not app._history_dragging


def test_disabled_numeric_and_readout_controls_do_not_change_before_load(session):
    app = session.app
    app.cleanup_current_temp()
    app._refresh_action_states()
    app.update()
    variables = (app.selection_start_var, app.selection_end_var, app.eq_low_freq_var,
                 app.tempo_percent_var, app.pitch_semitones_var, app.fade_in_var)
    for variable in variables:
        widget = entry_for(app, variable)
        assert widget.instate(("disabled",))
        original = variable.get()
        wheel(app, widget, 240)
        drag(app, widget, 30)
        assert variable.get() == original
    readout = next(w for w in children(app.stem_cards)
                   if hasattr(w, "numeric_gestures"))
    original = app.stem_vars["vocals"]["volume"].get()
    wheel(app, readout, 240)
    drag(app, readout, 30)
    assert app.stem_vars["vocals"]["volume"].get() == original


def test_settings_choices_scrub_supported_values_and_keep_arrow_dropdown(session):
    app = session.app
    app.open_render_settings()
    app.update()
    choices = [w for w in children(app._dialog)
               if isinstance(w, ttk.Combobox) and hasattr(w, "numeric_gestures")]
    assert len(choices) == 3
    for choice in choices:
        supported = sorted(map(int, choice.cget("values")))
        click(app, choice)
        popdown = app.tk.call("ttk::combobox::PopdownWindow", str(choice))
        assert not int(app.tk.call("winfo", "ismapped", popdown))
        drag(app, choice, -12)
        assert int(choice.get()) == supported[0]
        wheel(app, choice, 120)
        assert int(choice.get()) == supported[1]
        drag(app, choice, 30000)
        assert int(choice.get()) == supported[-1]
        click(app, choice, arrow=True)
        assert int(app.tk.call("winfo", "ismapped", popdown))
        app.tk.call("ttk::combobox::Unpost", str(choice))
        app.update()
    app._save_compact_settings()
    assert app._dialog is None


def test_fade_markers_and_envelope_follow_duration_zoom_and_zero(session):
    app = session.app
    canvas = app.wave_canvas
    # A synthetic long timeline makes 20 ms smaller than one display pixel.
    app.duration_seconds = 300
    app._configure_selection_limits(300)
    app.selection_start_var.set(0)
    app.selection_end_var.set(300)
    app.view_start, app.view_end = 0, 300
    app.fade_in_var.set(.02)
    app.fade_out_var.set(.02)
    app.update()
    assert len(canvas.find_withtag("fade-marker")) == 2
    assert len(canvas.find_withtag("fade-envelope")) == 8
    marker = canvas.find_withtag("fade-marker")[0]
    assert canvas.bbox(marker)[2] - canvas.bbox(marker)[0] >= 8
    envelope = canvas.coords(canvas.find_withtag("fade-envelope")[0])
    assert 0 < envelope[2] - envelope[0] < 1
    app.view_start, app.view_end = 0, 1
    app.draw_waveform()
    before = [canvas.coords(item) for item in canvas.find_withtag("wave-sample")]
    app.fade_in_var.set(.5)
    app.update()
    after = [canvas.coords(item) for item in canvas.find_withtag("wave-sample")]
    assert any(abs(b[3]-b[1]) < abs(a[3]-a[1]) for a, b in zip(before, after))
    envelope = canvas.coords(canvas.find_withtag("fade-envelope")[0])
    assert envelope[2] == pytest.approx(canvas.winfo_width() / 2)
    app.view_start, app.view_end = 299, 300
    app.fade_out_var.set(.5)
    app.update()
    assert canvas.find_withtag("fade-out")
    assert not canvas.find_withtag("fade-in")
    app.fade_in_var.set(0)
    app.fade_out_var.set(0)
    app.update()
    assert not canvas.find_withtag("fade-envelope")
    assert not canvas.find_withtag("fade-marker")
    app.view_start, app.view_end = 59.97, 60.03
    app.draw_waveform()
    labels = [canvas.itemcget(item, "text") for item in canvas.find_withtag("timeline-tick")]
    assert len(labels) == len(set(labels))
    assert "01:00.00" in labels
    assert not any(label.startswith("00:60") for label in labels)


def test_active_knob_and_fader_readouts_drag_undo_and_reset(session):
    app = session.app
    app.stem_paths = {stem: app.source_wav for stem in app.stem_vars}
    app.stem_range = (0, app.duration_seconds)
    app._refresh_action_states()
    app.update()
    knob_label = next(w for w in children(app.bands)
                      if isinstance(w, tk.Label) and str(w.cget("textvariable")) == str(app.band_values["mid"]))
    app._commit_edit()
    drag(app, knob_label, 65)
    assert app.eq_mid_var.get() == 24
    app.undo_edit()
    assert app.eq_mid_var.get() == 0
    app.redo_edit()
    assert app.eq_mid_var.get() == 24
    click(app, knob_label, ctrl=True)
    assert app.eq_mid_var.get() == 0
    fader_label = next(w for w in children(app.stem_cards)
                       if isinstance(w, tk.Label) and str(w.cget("textvariable")) == str(app.stem_volume_label_vars["vocals"]))
    app._commit_edit()
    drag(app, fader_label, 12)
    assert app.stem_vars["vocals"]["volume"].get() > 100
    app.undo_edit()
    assert app.stem_vars["vocals"]["volume"].get() == 100
    app.redo_edit()
    assert app.stem_vars["vocals"]["volume"].get() > 100
    click(app, fader_label, ctrl=True)
    assert app.stem_vars["vocals"]["volume"].get() == 100


def reset_controls(app):
    controls=[]
    for band,knob in app.compact_knobs.items():
        label=next(w for w in children(app.bands) if isinstance(w,tk.Label)
                   and str(w.cget("textvariable"))==str(app.band_values[band]))
        controls.extend((widget,getattr(app,"eq_"+band+"_var"),8,0) for widget in (knob,label))
    for stem,widgets in app.stem_widgets.items():
        label=next(w for w in children(app.stem_cards) if isinstance(w,tk.Label)
                   and str(w.cget("textvariable"))==str(app.stem_volume_label_vars[stem]))
        controls.extend((widget,app.stem_vars[stem]["volume"],50,100) for widget in (widgets[0],label))
    return controls


def test_ctrl_reset_is_one_undo_step_and_does_not_start_a_drag(session):
    app=session.app
    app.stem_paths={stem:app.source_wav for stem in app.stem_vars}
    app.stem_range=(0,app.duration_seconds)
    app._refresh_action_states();app.update()
    for widget,variable,changed,default in reset_controls(app):
        variable.set(changed);app.update();app._commit_edit()
        before=app._edit_snapshot()
        x,y=widget.winfo_width()//2,widget.winfo_height()//2
        stamp=next(_times)
        widget.event_generate("<ButtonPress-1>",x=x,y=y,state=4,time=stamp)
        app.update()
        assert variable.get()==default
        # Releasing Ctrl while still holding the mouse must not jump a fader
        # to the click position or continue a stale knob/readout drag.
        widget.event_generate("<B1-Motion>",x=x,y=y-20,state=0x100,time=stamp+50)
        widget.event_generate("<ButtonRelease-1>",x=x,y=y-20,state=0,time=stamp+80)
        app.update()
        assert variable.get()==default
        assert not app._history_dragging
        app.undo_edit()
        assert app._edit_snapshot()==before
        app.redo_edit()
        assert variable.get()==default
        variable.set(changed);app.update();app._commit_edit()
        click(app,widget,double=True)
        assert variable.get()!=default  # Ordinary clicks, with no reset shortcut.


def test_ctrl_reset_pass_slope_defaults_and_disabled_controls(session):
    app=session.app
    for band,shape,slope in (("low","High Pass",app.high_pass_slope_var),
                             ("high","Low Pass",app.low_pass_slope_var)):
        getattr(app,"eq_"+band+"_shape_var").set(shape)
        getattr(app,"eq_"+band+"_freq_var").set(240 if band=="low" else 6000)
        knob=app.compact_knobs[band]
        label=next(w for w in children(app.bands) if isinstance(w,tk.Label)
                   and str(w.cget("textvariable"))==str(app.band_values[band]))
        for widget in (knob,label):
            slope.set(48);app.update();app._commit_edit()
            before=app._edit_snapshot()
            click(app,widget,ctrl=True)
            assert slope.get()==24
            assert getattr(app,"eq_"+band+"_freq_var").get()==(240 if band=="low" else 6000)
            app.undo_edit();assert app._edit_snapshot()==before
    # Stem controls without separated audio, then all controls during a job.
    for widget,variable,changed,default in reset_controls(app)[6:]:
        variable.set(changed);app.update()
        click(app,widget,ctrl=True)
        assert variable.get()==changed
    app.stem_paths={stem:app.source_wav for stem in app.stem_vars}
    app.stem_range=(0,app.duration_seconds)
    app.busy=True;app._refresh_action_states();app.update()
    before=app._edit_snapshot()
    for widget,*_ in reset_controls(app):click(app,widget,ctrl=True)
    assert app._edit_snapshot()==before
    app.busy=False;app._refresh_action_states()


def numeric_reset_controls(app):
    from backend.project_store import EDIT_DEFAULTS
    for key, changed in (("eq_low_freq",1150),("eq_mid_freq",2400),("eq_high_freq",6000),
                         ("tempo_percent",162),("pitch_semitones",-4),("fade_in",.8),("fade_out",1.2)):
        variable=getattr(app,key+"_var")
        yield entry_for(app,variable),variable,changed,EDIT_DEFAULTS[key]


@pytest.mark.parametrize("lock_state",[0,8])
def test_numeric_ctrl_reset_one_undo_and_no_drag_after_releasing_ctrl(session,lock_state):
    app=session.app
    app.playback_cursor_seconds=2;app.playback_cursor_manual=True
    for widget,variable,changed,default in numeric_reset_controls(app):
        variable.set(changed);app.update();app._commit_edit()
        before,index=app._edit_snapshot(),app.history.index
        x,y=12,widget.winfo_height()//2
        stamp=next(_times)
        widget.event_generate("<ButtonPress-1>",x=x,y=y,state=4|lock_state,time=stamp)
        app.update()
        assert variable.get()==default
        widget.event_generate("<B1-Motion>",x=x,y=y-30,state=0x100|lock_state,time=stamp+50)
        widget.event_generate("<ButtonRelease-1>",x=x,y=y-30,state=lock_state,time=stamp+80)
        app.update()
        assert variable.get()==default and float(widget.get())==default
        assert app.history.index==index+1 and not app._history_dragging
        assert app.playback_cursor_seconds==2
        after=app._edit_snapshot()
        app.undo_edit();assert app._edit_snapshot()==before
        app.redo_edit();assert app._edit_snapshot()==after
        click(app,widget,ctrl=True,numlock=bool(lock_state))
        assert app.history.index==index+1  # Resetting a default adds no history entry.


def test_numeric_ctrl_reset_consumes_spin_arrows_and_repairs_incomplete_text(session):
    app=session.app
    for widget,variable,changed,default in numeric_reset_controls(app):
        variable.set(changed);app.update();app._commit_edit()
        click(app,widget,arrow=True,ctrl=True,numlock=True)
        assert variable.get()==default and float(widget.get())==default
        click(app,widget,arrow=True,numlock=True)
        assert variable.get()!=default  # Unmodified native arrows still step.
        variable.set(changed);app.update();app._commit_edit()
        click(app,widget,double=True,numlock=True)
        assert variable.get()==changed and widget.selection_present()
        widget.delete(0,"end");widget.insert(0,"-")
        click(app,widget,ctrl=True,numlock=True)
        assert variable.get()==default and float(widget.get())==default
    assert app.fade_in_spinbox.get()==app.fade_out_spinbox.get()=="0.02"


def test_numeric_ctrl_reset_ignores_busy_and_disabled_fields(session):
    app=session.app
    for widget,variable,changed,_ in numeric_reset_controls(app):variable.set(changed)
    app.update();app._commit_edit()
    before,index=app._edit_snapshot(),app.history.index
    app.busy=True;app._refresh_action_states();app.update()
    for widget,*_ in numeric_reset_controls(app):
        click(app,widget,ctrl=True,numlock=True)
        click(app,widget,arrow=True,ctrl=True,numlock=True)
    assert app._edit_snapshot()==before and app.history.index==index
    app.busy=False;app._refresh_action_states();app.update()
    widget=app.tempo_spinbox;widget.state(("disabled",))
    click(app,widget,ctrl=True,numlock=True)
    assert app._edit_snapshot()==before and app.history.index==index
    assert not app._history_dragging
