"""Policy and actual Win32 sizing messages on isolated QA windows."""
import ctypes
from ctypes import wintypes
from unittest.mock import patch

import pytest
import test_workspace
from backend.window_bounds import MinMaxInfo,WindowLimits,sizing_rectangle,window_limits


@pytest.mark.parametrize("work",((1920,1040),(2560,1400),(3840,2120),(1024,660)))
@pytest.mark.parametrize("dpi",(1,1.25,1.5,1.75,2))
def test_limits_fit_work_area_at_each_dpi(work,dpi):
    decoration=(round(16*dpi),round(48*dpi))
    limits=window_limits(*work,dpi,decoration)
    for width,height in (limits.minsize,limits.initial_size,limits.maxsize):
        assert width*7==height*10
        assert width+decoration[0]+round(24*dpi)<=work[0]
        assert height+decoration[1]+round(24*dpi)<=work[1]
        assert width<=1400*dpi
    assert limits.minimum<=limits.initial<=limits.maximum
    assert limits.minsize[0]>=760*dpi or limits.minimum==limits.maximum


def test_programmatic_width_and_height_changes_drive_the_other_axis():
    limits=WindowLimits(76,140,100)
    assert limits.constrain(1300,700,(1000,700))==(1300,910)
    assert limits.constrain(1000,840,(1000,700))==(1200,840)
    assert limits.constrain(20,20)==(760,532)
    assert limits.constrain(5000,4000)==(1400,980)


@pytest.mark.parametrize("edge",range(1,9))
@pytest.mark.parametrize("client",((300,200),(1234,880),(5000,4000)))
def test_all_edges_anchor_the_opposite_corner_and_stay_bounded(edge,client):
    decoration=(16,48);limits=WindowLimits(76,140,100)
    original=(100,100,100+client[0]+16,100+client[1]+48)
    rect=sizing_rectangle(original,edge,decoration,limits,(1000,700))
    width,height=rect[2]-rect[0]-16,rect[3]-rect[1]-48
    assert width*7==height*10
    assert 760<=width<=1400
    assert rect[2 if edge in (1,4,7) else 0]==original[2 if edge in (1,4,7) else 0]
    assert rect[3 if edge in (3,4,5) else 1]==original[3 if edge in (3,4,5) else 1]


def test_installed_native_messages_maximize_and_dialogs():
    case=test_workspace.WorkspaceTests();case.setUp();app=case.app
    native=app._window_constraints
    try:
        assert native and native.old_proc
        assert native.hwnd==int(app.frame(),0)
        assert native.hwnd not in app._drop_old_wndprocs
        api=ctypes.windll.user32
        api.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        api.SendMessageW.restype=ctypes.c_ssize_t
        edits=app._edit_snapshot()
        for edge in range(1,9):
            for width,height in ((300,200),(1200,800),(4000,3000)):
                dw,dh=native.decoration
                rect=wintypes.RECT(32,32,32+width+dw,32+height+dh)
                result=api.SendMessageW(wintypes.HWND(native.hwnd),0x0214,edge,ctypes.addressof(rect))
                assert result==1
                width,height=rect.right-rect.left-dw,rect.bottom-rect.top-dh
                assert width*7==height*10
                assert app.minsize()[0]<=width<=app.maxsize()[0]
        data=MinMaxInfo()
        api.SendMessageW(wintypes.HWND(native.hwnd),0x0024,0,ctypes.addressof(data))
        assert (data.min_track.x,data.min_track.y)==tuple(n+d for n,d in zip(app.minsize(),native.decoration))
        assert (data.max_track.x,data.max_track.y)==tuple(n+d for n,d in zip(app.maxsize(),native.decoration))
        app.state("zoomed");app.update()
        assert app.winfo_width()*7==app.winfo_height()*10
        assert (app.winfo_width(),app.winfo_height())==app._fixed_limits.maxsize
        app.state("normal");app.update()
        app.geometry("1100x700");app.update()
        assert (app.winfo_width(),app.winfo_height())==(1100,770)
        app.geometry("1100x840");app.update()
        assert (app.winfo_width(),app.winfo_height())==(1200,840)
        app.open_render_settings();app.update()
        dialog=app._dialog;dialog.geometry("600x450");app.update()
        assert (dialog.winfo_width(),dialog.winfo_height())==(600,450)
        app._close_render_settings()
        assert app._edit_snapshot()==edits
        assert not app.workspace_scroll.bar.winfo_ismapped()
        assert not case.callback_errors
    finally:case.tearDown()
    assert native.hwnd==0


def test_monitor_change_reduces_limits_and_preserves_aspect():
    case=test_workspace.WorkspaceTests();case.setUp();app=case.app
    try:
        app._ui_scale_override=None
        with patch("backend.compact_ui.display_metrics",return_value=((0,0,1024,660),2)):
            app.geometry("1400x980");app.update()
            assert app.winfo_width()*7==app.winfo_height()*10
            assert app.minsize()==app.maxsize()
            assert app.winfo_height()+app._fixed_decoration[1]<660
            assert not app.workspace_scroll.bar.winfo_ismapped()
        assert not case.callback_errors
    finally:case.tearDown()
