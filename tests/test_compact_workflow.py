from pathlib import Path
from unittest.mock import patch

import pytest

import test_workspace
from backend.compact_model import MAX_STEM_PERCENT


@pytest.fixture
def session():
    case=test_workspace.WorkspaceTests();case.setUp()
    try:yield case
    finally:case.tearDown()


def test_direct_exports_preserve_existing_files_and_do_not_prompt(session):
    app=session.app
    app.selection_start_var.set(1);app.selection_end_var.set(2)
    with patch("tkinter.filedialog.asksaveasfilename") as save_as:
        app.render_wav();session.wait_idle()
        first=app.result_files[0];original=first.read_bytes()
        app.render_wav();session.wait_idle();second=app.result_files[0]
        assert second!=first and second.exists() and first.read_bytes()==original
        app.render_mp3();session.wait_idle();mp3=app.result_files[0]
        assert mp3.suffix==".mp3" and mp3.stat().st_size>100
        save_as.assert_not_called()
    assert first.parent==app.output_dir


def test_browse_cancel_keep_path_and_done_persists_preferences(session):
    app=session.app;original=app.output_dir
    app.open_render_settings();app.update()
    with patch("tkinter.filedialog.askdirectory",return_value=""):
        app._browse_save_folder()
        assert Path(app.settings_folder_var.get())==original
    picked=session.paths.root/"saved audio"
    with patch("tkinter.filedialog.askdirectory",return_value=str(picked)):
        app._browse_save_folder()
    app.sample_rate_var.set(44100);app.bit_depth_var.set(16);app.loop_var.set(False)
    app._save_compact_settings()
    assert app.output_dir==picked
    saved=app.paths.read_settings()
    assert saved["output_dir"]==str(picked) and saved["sample_rate"]==44100 and saved["loop"] is False
    assert app._dialog is None


def test_numeric_text_is_readable_validated_and_fades_are_undoable(session):
    app=session.app
    assert app.tempo_spinbox.get()=="100"
    assert app.fade_in_spinbox.get()=="0.02"
    app._begin_edit_drag()
    app.fade_in_spinbox.delete(0,"end");app.fade_in_spinbox.insert(0,"0.04")
    app._end_edit_drag();app._commit_edit()
    assert app.fade_in_var.get()==.04 and app.fade_in_spinbox.get()=="0.04"
    app.undo_edit();assert app.fade_in_spinbox.get()=="0.02"
    app.redo_edit();assert app.fade_in_spinbox.get()=="0.04"
    app.fade_in_spinbox.delete(0,"end")
    with pytest.raises(ValueError):app._build_audio_effects()
    app.fade_in_spinbox.insert(0,"0.02")


def test_pass_slope_q_mute_solo_and_fader_history(session):
    app=session.app
    app.eq_low_shape_var.set("High Pass");app.eq_high_shape_var.set("Low Pass")
    app._set_band_value("low",48);app.high_pass_q_var.set(1.1)
    effects=app._build_audio_effects()
    assert effects.high_pass_slope==48 and effects.high_pass_q==1.1 and effects.high_pass_hz==120
    app.stem_paths={stem:app.source_wav for stem in app.stem_vars};app.stem_range=(0,app.duration_seconds)
    app._refresh_action_states()
    app._begin_edit_drag();app.stem_vars["vocals"]["volume"].set(MAX_STEM_PERCENT)
    app._end_edit_drag();app._commit_edit()
    assert app._build_mix_stems()[0].gain==pytest.approx(MAX_STEM_PERCENT/100)
    app.undo_edit();assert app.stem_vars["vocals"]["volume"].get()==100
    app.redo_edit();assert app.stem_vars["vocals"]["volume"].get()==MAX_STEM_PERCENT
    app.stem_vars["vocals"]["solo"].set(True);app.stem_vars["vocals"]["mute"].set(True)
    assert app._build_mix_stems()==[]
    app.stem_vars["vocals"]["mute"].set(False)
    assert [stem.name for stem in app._build_mix_stems()]==["vocals"]
    app.stem_widgets["vocals"][0].reset()
    assert app.stem_vars["vocals"]["volume"].get()==100


def test_space_and_history_do_not_hijack_numeric_input(session):
    app=session.app
    with patch.object(app,"focus_get",return_value=app.fade_in_spinbox),patch.object(app,"toggle_playback") as play:
        app._space_toggle_playback()
        play.assert_not_called()
    app.preview_playing=True;app._refresh_action_states()
    assert app.play_button.label=="Pause" and app.play_button.icon_name=="pause"
    app.preview_playing=False;app._refresh_action_states()
    assert app.play_button.label=="Play" and app.play_button.icon_name=="play"


@pytest.mark.parametrize("scale",(1,1.25,1.5,1.75,2))
def test_initial_window_and_minimum_fit_1080p_work_area(session,scale):
    app=session.app;app._ui_scale_override=scale;app._display_scale=scale
    with patch("backend.compact_ui.display_metrics",return_value=((0,0,1920,1040),scale)):
        app._set_initial_compact_window();app.update()
    assert app.winfo_rootx()+app.winfo_width()<=1920
    assert app.winfo_rooty()+app.winfo_height()<=1040
    assert app.minsize()[1]<=app.winfo_height()
