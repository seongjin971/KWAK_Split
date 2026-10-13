"""Copy one client HWND before sizing, without entering Tk or sending paint messages."""
import ctypes
from ctypes import wintypes
import os


class BitmapInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG),
                ("height", wintypes.LONG), ("planes", wintypes.WORD),
                ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG),
                ("yppm", wintypes.LONG), ("used", wintypes.DWORD),
                ("important", wintypes.DWORD), ("color", wintypes.DWORD)]


def capture_client(hwnd):
    """Return (size, BGRX bytes), or None; all GDI handles are released here."""
    if os.name != "nt" or not hwnd:
        return None
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    handle = wintypes.HWND(hwnd)
    rect = wintypes.RECT()
    if not user.IsWindowVisible(handle) or not user.GetClientRect(handle, ctypes.byref(rect)):
        return None
    width, height = rect.right, rect.bottom
    if width <= 0 or height <= 0 or width * height > 32_000_000:
        return None
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    source = user.GetDC(handle)
    if not source:
        return None
    memory = bitmap = previous = None
    try:
        memory = gdi.CreateCompatibleDC(source)
        if not memory:
            return None
        info = BitmapInfo(size=40, width=width, height=-height, planes=1, bits=32)
        pixels = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(source, ctypes.byref(info), 0, ctypes.byref(pixels), None, 0)
        if not bitmap or not pixels.value:
            return None
        previous = gdi.SelectObject(memory, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value:
            return None
        if not gdi.BitBlt(memory, 0, 0, width, height, source, 0, 0, 0x00CC0020):
            return None
        gdi.GdiFlush()
        return (width, height), ctypes.string_at(pixels, width * height * 4)
    finally:
        if previous and previous != ctypes.c_void_p(-1).value:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        user.ReleaseDC(handle, source)


class PaintInfo(ctypes.Structure):
    _fields_ = [("dc", wintypes.HDC), ("erase", wintypes.BOOL),
                ("rect", wintypes.RECT), ("restore", wintypes.BOOL),
                ("incremental", wintypes.BOOL), ("reserved", ctypes.c_byte * 32)]


class BitmapWindow:
    """A native child paints the same DIB at each size, avoiding Tk image copies.

    The STATIC procedure and this callback never enter Tk. The enclosing Tk
    canvas owns placement/visibility; destroying it also destroys this child.
    """
    def __init__(self, parent_hwnd):
        self.api = ctypes.windll.user32
        self.bitmap = None
        self.error = None
        self.hwnd = 0
        self.api.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        self.api.CreateWindowExW.restype = wintypes.HWND
        self.api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self.api.SetWindowLongPtrW.restype = ctypes.c_void_p
        self.api.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.api.CallWindowProcW.restype = ctypes.c_ssize_t
        self.api.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintInfo)]
        self.api.BeginPaint.restype = wintypes.HDC
        self.api.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintInfo)]
        self.api.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
        self.api.UpdateWindow.argtypes = [wintypes.HWND]
        self.api.DestroyWindow.argtypes = [wintypes.HWND]
        self.api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        hwnd = self.api.CreateWindowExW(0, "STATIC", "", 0x40000000 | 0x08000000,
                                       0, 0, 1, 1, wintypes.HWND(parent_hwnd), None, None, None)
        if not hwnd:
            raise ctypes.WinError()
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM)
        self.callback = callback_type(self._message)
        self.old_proc = self.api.SetWindowLongPtrW(hwnd, -4, ctypes.cast(self.callback, ctypes.c_void_p))
        if not self.old_proc:
            self.api.DestroyWindow(hwnd)
            raise ctypes.WinError()
        self.hwnd = hwnd

    def _paint(self, dc):
        if self.bitmap is None:
            return
        rect = wintypes.RECT()
        self.api.GetClientRect(wintypes.HWND(self.hwnd), ctypes.byref(rect))
        # Pillow's DIB draws directly into a Windows device context and scales
        # from the original image every time. No cumulative bitmap scaling.
        gdi = ctypes.windll.gdi32
        gdi.SaveDC.argtypes = [wintypes.HDC]
        gdi.RestoreDC.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi.SetBrushOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        saved = gdi.SaveDC(dc)
        try:
            gdi.SetStretchBltMode(dc, 4)  # HALFTONE preserves thin text while shrinking.
            gdi.SetBrushOrgEx(dc, 0, 0, None)
            self.bitmap.draw(int(dc), (0, 0, rect.right, rect.bottom))
        finally:
            if saved:gdi.RestoreDC(dc, saved)

    def _message(self, hwnd, message, wparam, lparam):
        if message == 0x14:  # WM_ERASEBKGND; the image covers the entire client.
            return 1
        if message == 0x0f:  # WM_PAINT
            info = PaintInfo()
            dc = self.api.BeginPaint(hwnd, ctypes.byref(info))
            try:
                if dc:self._paint(dc)
            except Exception as exc:self.error = exc
            finally:self.api.EndPaint(hwnd, ctypes.byref(info))
            return 0
        if message == 0x318:  # WM_PRINTCLIENT, for window-only QA capture.
            try:self._paint(wparam)
            except Exception as exc:self.error = exc
            return 0
        result = self.api.CallWindowProcW(self.old_proc, hwnd, message, wparam, lparam)
        if message == 0x82:self.hwnd = 0  # WM_NCDESTROY
        return result

    def show(self, width, height):
        if not self.hwnd:
            raise OSError("Resize image window is unavailable")
        self.error = None
        if not self.api.SetWindowPos(wintypes.HWND(self.hwnd), None, 0, 0, width, height, 0x50):
            raise ctypes.WinError()
        self.api.InvalidateRect(wintypes.HWND(self.hwnd), None, False)
        self.api.UpdateWindow(wintypes.HWND(self.hwnd))
        if self.error is not None:raise OSError("Resize image could not be painted") from self.error

    def close(self):
        if self.hwnd:self.api.DestroyWindow(wintypes.HWND(self.hwnd))
        self.hwnd = 0
        self.bitmap = None
