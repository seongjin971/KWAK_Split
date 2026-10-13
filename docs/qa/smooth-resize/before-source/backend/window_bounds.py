"""10:7 client geometry and Windows sizing messages, independent of audio."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import os


@dataclass(frozen=True)
class WindowLimits:
    minimum: int  # One unit is 10x7 client pixels.
    maximum: int
    initial: int

    def size(self, units):
        units=max(self.minimum,min(self.maximum,round(units)))
        return units*10,units*7

    @property
    def minsize(self):return self.size(self.minimum)
    @property
    def maxsize(self):return self.size(self.maximum)
    @property
    def initial_size(self):return self.size(self.initial)

    def constrain(self,width,height,previous=None,axis=None):
        if axis is None and previous:
            dw,dh=abs(width-previous[0]),abs(height-previous[1])
            if dw and not dh:axis="width"
            elif dh and not dw:axis="height"
        units=width/10 if axis=="width" else height/7 if axis=="height" else (10*width+7*height)/149
        return self.size(units)


def window_limits(work_width,work_height,scale=1,decoration=(0,0)):
    """DPI-scaled 760..1400 logical width, reduced to the monitor work area."""
    margin=round(12*scale)
    available_width=max(10,work_width-2*margin-decoration[0])
    available_height=max(7,work_height-2*margin-decoration[1])
    maximum=max(1,min(math.floor(140*scale),available_width//10,available_height//7))
    minimum=min(maximum,max(1,math.ceil(76*scale)))
    return WindowLimits(minimum,maximum,max(minimum,min(maximum,round(100*scale))))


def sizing_rectangle(rect,edge,decoration,limits,previous=None):
    """Keep the opposite edge/corner anchored while constraining a WM_SIZING RECT."""
    left,top,right,bottom=rect
    width,height=right-left-decoration[0],bottom-top-decoration[1]
    axis="width" if edge in (1,2) else "height" if edge in (3,6) else None
    if axis is None and previous:
        axis="width" if abs(width/previous[0]-1)>=abs(height/previous[1]-1) else "height"
    width,height=limits.constrain(width,height,axis=axis)
    width+=decoration[0];height+=decoration[1]
    if edge in (1,4,7):left=right-width
    else:right=left+width
    if edge in (3,4,5):top=bottom-height
    else:bottom=top+height
    return left,top,right,bottom


def window_decoration(window):
    if os.name=="nt":
        api=ctypes.windll.user32;hwnd=wintypes.HWND(int(window.frame(),0))
        outer,client=wintypes.RECT(),wintypes.RECT()
        if api.GetWindowRect(hwnd,ctypes.byref(outer)) and api.GetClientRect(hwnd,ctypes.byref(client)):
            return max(0,outer.right-outer.left-client.right),max(0,outer.bottom-outer.top-client.bottom)
    return 0,0


class MinMaxInfo(ctypes.Structure):
    _fields_=[(name,wintypes.POINT) for name in
             ("reserved","max_size","max_position","min_track","max_track")]


class NativeWindowBounds:
    """Subclass only the top-level wrapper; leave the file-drop widget hooks alone.

    The callback uses cached policy and Win32 calls only, never the Tk event loop.
    """
    def __init__(self,window,limits,area,decoration):
        self.window=window;self.update(limits,area,decoration)
        self.hwnd=int(window.frame(),0);self.old_proc=None;self.callback=None
        if os.name!="nt":return
        self.api=ctypes.windll.user32
        self.api.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_void_p]
        self.api.SetWindowLongPtrW.restype=ctypes.c_void_p
        self.api.CallWindowProcW.argtypes=[ctypes.c_void_p,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.api.CallWindowProcW.restype=ctypes.c_ssize_t
        self.api.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
        self.callback=callback_type(self._message)
        ctypes.set_last_error(0)
        self.old_proc=self.api.SetWindowLongPtrW(wintypes.HWND(self.hwnd),-4,ctypes.cast(self.callback,ctypes.c_void_p))
        if not self.old_proc:raise ctypes.WinError()
        window.bind("<Destroy>",self._destroyed,add="+")

    def update(self,limits,area,decoration):
        self.limits,self.area,self.decoration=limits,area,decoration

    def _message(self,hwnd,message,wparam,lparam):
        old_proc=self.old_proc
        result=0;forwarded=False
        try:
            if message==0x0214 and lparam:  # WM_SIZING
                rect=ctypes.cast(lparam,ctypes.POINTER(wintypes.RECT)).contents
                client=wintypes.RECT()
                self.api.GetClientRect(hwnd,ctypes.byref(client))
                previous=(max(1,client.right),max(1,client.bottom))
                rect.left,rect.top,rect.right,rect.bottom=sizing_rectangle(
                    (rect.left,rect.top,rect.right,rect.bottom),int(wparam),self.decoration,self.limits,previous)
                return 1
            forwarded=True
            result=self.api.CallWindowProcW(old_proc,hwnd,message,wparam,lparam) if old_proc else 0
            if message==0x0024 and lparam:  # WM_GETMINMAXINFO
                data=ctypes.cast(lparam,ctypes.POINTER(MinMaxInfo)).contents
                dw,dh=self.decoration
                low,high=self.limits.minsize,self.limits.maxsize
                data.min_track.x,data.min_track.y=low[0]+dw,low[1]+dh
                data.max_track.x,data.max_track.y=high[0]+dw,high[1]+dh
                data.max_size.x,data.max_size.y=high[0]+dw,high[1]+dh
                # Maximized position is relative to the monitor origin, not its
                # work-area origin (which can move with the taskbar).
                monitor=monitor_origin(self.api,hwnd)
                l,t,r,b=self.area
                data.max_position.x=l-monitor[0]+(r-l-data.max_size.x)//2
                data.max_position.y=t-monitor[1]+(b-t-data.max_size.y)//2
            if message==0x0082:self.hwnd=0  # WM_NCDESTROY
            return result
        except Exception:
            # Keep the original window procedure available if native sizing
            # cannot be handled. The root Configure guard still constrains size.
            return result if forwarded else self.api.CallWindowProcW(old_proc,hwnd,message,wparam,lparam) if old_proc else 0

    def resize(self,width,height,position=None):
        if not self.hwnd or not self.old_proc:return False
        self.api.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                      ctypes.c_int,ctypes.c_int,wintypes.UINT]
        flags=0x0004|0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
        if position is None:position=(0,0);flags|=0x0002
        return bool(self.api.SetWindowPos(wintypes.HWND(self.hwnd),None,*position,
                                         width+self.decoration[0],height+self.decoration[1],flags))

    def _destroyed(self,event):
        if event.widget==self.window:self.close()

    def close(self):
        if self.hwnd and self.old_proc and os.name=="nt":
            self.api.SetWindowLongPtrW(wintypes.HWND(self.hwnd),-4,ctypes.c_void_p(self.old_proc))
        self.hwnd=0
        # Keep the callback alive until the owner is released: close can run
        # while the original procedure is processing a Destroy event.


def monitor_origin(api,hwnd):
    class Info(ctypes.Structure):
        _fields_=[("size",wintypes.DWORD),("monitor",wintypes.RECT),("work",wintypes.RECT),("flags",wintypes.DWORD)]
    api.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
    api.MonitorFromWindow.restype=ctypes.c_void_p
    api.GetMonitorInfoW.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    info=Info();info.size=ctypes.sizeof(info)
    monitor=api.MonitorFromWindow(hwnd,2)
    if monitor and api.GetMonitorInfoW(ctypes.c_void_p(monitor),ctypes.byref(info)):
        return info.monitor.left,info.monitor.top
    return 0,0
