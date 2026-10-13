"""Check actual Tk geometry and editing state while fitting a small client area."""
from unittest.mock import patch

import pytest
import test_workspace


@pytest.mark.parametrize("size",((1000,700),(900,630),(760,532),(480,360)))
def test_audio_load_and_status_changes_keep_the_same_composition(size):
    case=test_workspace.WorkspaceTests();case.setUp();app=case.app
    try:
        app.geometry(f"{size[0]}x{size[1]}");app.status_var.set("");app.update()
        size=(app.winfo_width(),app.winfo_height())
        assert size[0]*7==size[1]*10
        def composition():
            widgets=(app.header,app.wave_canvas,app.eq_panel,app.mixer_panel,app.timing)
            return (app.ui_scale,app.fonts["body"].cget("size"),
                    tuple((w.winfo_x(),w.winfo_y(),w.winfo_width(),w.winfo_height()) for w in widgets))
        original=composition()
        for busy,message in ((True,"Loading audio..."),(True,"Downloading the stem model..."),
                             (False,"Export saved to the chosen folder."),(False,"")):
            app.busy=busy;app.status_var.set(message);app.update()
            assert composition()==original
            assert not app.workspace_scroll.bar.winfo_ismapped()
        app.busy=False
        scales=[]
        original_rescale=app._rescale_compact
        def record_scale(scale):
            scales.append(scale);original_rescale(scale)
        with patch.object(app,"_rescale_compact",side_effect=record_scale):
            app.load_audio_path(case.source);case.wait_idle();app.update()
        assert scales==[]
        assert composition()==original
        assert (app.winfo_width(),app.winfo_height())==size
        assert not case.callback_errors
    finally:
        app.busy=False;case.tearDown()


@pytest.mark.parametrize("dpi", (1, 1.25, 1.5, 1.75, 2))
def test_fit_and_roundtrip_preserve_geometry_and_edits(dpi):
    case=test_workspace.WorkspaceTests();case.ui_scale=dpi;case.setUp()
    app=case.app
    try:
        normal=(round(1000*dpi),round(700*dpi))
        app.geometry(f"{normal[0]}x{normal[1]}");app.update()
        app.eq_mid_var.set(6);app._commit_edit()
        before=app._edit_snapshot()
        spacing=app.load_button.grid_info()["padx"]
        font_size=app.fonts["body"].cget("size")
        for size in ((640,480),(480,360),(1000,420),normal)*2:
            app.geometry(f"{size[0]}x{size[1]}");app.update()
            actual=(app.winfo_width(),app.winfo_height())
            assert actual[0]*7==actual[1]*10
            assert app.minsize()[0]<=actual[0]<=app.maxsize()[0]
            assert app._layout_mode=="side-by-side"
            assert not app.workspace_scroll.bar.winfo_ismapped()
            assert app.workspace_scroll.canvas.yview()==(0,1)
            for widget in (app.play_button,app.eq_editor,app.fade_out_spinbox,
                           app.export_stems_button,*app.stem_widgets["other"]):
                assert widget.winfo_ismapped()
                assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+actual[0]+1
                assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+actual[1]+1
            assert app._edit_snapshot()==before
        assert app.ui_scale==dpi
        assert app.load_button.grid_info()["padx"]==spacing
        assert app.fonts["body"].cget("size")==font_size
        app.undo_edit();assert app.eq_mid_var.get()==0
        app.redo_edit();assert app.eq_mid_var.get()==6
        assert not case.callback_errors
    finally:case.tearDown()


def test_context_status_and_dpi_change_still_fit():
    case=test_workspace.WorkspaceTests();case.setUp();app=case.app
    try:
        app.geometry("760x532");app.update()
        app.busy=True
        app.status_var.set("Preparing stem separation. Downloading the model...")
        app.update()
        assert app.status_label.winfo_ismapped() and app.cancel_button.winfo_ismapped()
        assert not app.workspace_scroll.bar.winfo_ismapped()
        assert app.mixer_panel.winfo_rooty()+app.mixer_panel.winfo_height()<=app.status_frame.winfo_rooty()+1
        assert app.cancel_button.winfo_rooty()+app.cancel_button.winfo_height()<=app.winfo_rooty()+app.winfo_height()
        app.busy=False;app.status_var.set("")
        app._ui_scale_override=None
        with patch("backend.compact_ui.display_metrics",return_value=((0,0,1920,1040),2)):
            app.geometry("640x480");app.update()
            assert app._display_scale==2
            assert app.winfo_width()*7==app.winfo_height()*10 and not app.workspace_scroll.bar.winfo_ismapped()
            app.geometry("1800x1000");app.update()
            assert app.ui_scale>1 and not app.workspace_scroll.bar.winfo_ismapped()
        assert not case.callback_errors
    finally:case.tearDown()
