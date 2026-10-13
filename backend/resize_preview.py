"""Scale an in-memory editor snapshot only during native border dragging."""
import time
import tkinter as tk
import os

try:
    from PIL import Image, ImageTk, ImageWin
except ImportError:
    Image = ImageTk = ImageWin = None

from backend.compact_widgets import BG
from backend.window_snapshot import BitmapWindow


class ResizePreview:
    def __init__(self, app, surface):
        self.app, self.surface = app, surface
        self.canvas = tk.Canvas(app, bg=BG, bd=0, highlightthickness=0, takefocus=0)
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.active = False
        self.snapshot = self.photo = None
        self.frame_after = self.watch_after = self.finish_after = None
        self.last_paint = 0.0
        self.last_size = None
        self.native_image = None
        app.bind("<Destroy>", self._destroyed, add="+")

    def begin(self):
        if self.active:return True
        native=self.app._window_constraints
        frame=native.resize_frame if native else None
        if Image is None or frame is None or not self.surface.winfo_ismapped():return False
        native.resize_frame=None
        try:
            size,data=frame
            self.snapshot = Image.frombytes("RGB",size,data,"raw","BGRX")
            if os.name=="nt":
                if self.native_image is None:self.native_image=BitmapWindow(int(self.canvas.winfo_id()))
                self.native_image.bitmap=ImageWin.Dib(self.snapshot)
        except (OSError, ValueError, MemoryError, tk.TclError):
            self.snapshot = None
            return False
        if self.finish_after is not None:
            self.app.after_cancel(self.finish_after);self.finish_after=None
        self.active = True
        self.last_size = None
        # Allocate and display the image before hiding any live controls.
        if not self.draw():return False
        self.surface.place_forget()
        self.watch_after = self.app.after(16, self._watch)
        return True

    def request(self):
        if not self.active or self.app.closing:return
        size=(self.app.winfo_width(),self.app.winfo_height())
        self.canvas.place(x=0,y=0,width=size[0],height=size[1])
        self.app.tk.call("raise",self.canvas._w)
        if self.frame_after is None:
            delay=max(0,round(16-(time.monotonic()-self.last_paint)*1000))
            self.frame_after=self.app.after(delay,self.draw)

    def draw(self):
        self.frame_after=None
        if not self.active or self.app.closing:return False
        size=(self.app.winfo_width(),self.app.winfo_height())
        try:
            self.canvas.place(x=0,y=0,width=size[0],height=size[1])
            self.app.tk.call("raise",self.canvas._w)
            if self.native_image is not None:
                self.native_image.show(*size)
                self.last_size=size
            elif size!=self.last_size:
                resized=self.snapshot.resize(size,Image.Resampling.BILINEAR)
                photo=ImageTk.PhotoImage(resized,master=self.app)
                self.canvas.itemconfigure(self.item,image=photo)
                self.photo=photo;self.last_size=size
        except (OSError, MemoryError, tk.TclError):
            self.finish()
            return False
        self.last_paint=time.monotonic()
        return True

    def _watch(self):
        self.watch_after=None
        if self.app.closing:return
        native=self.app._window_constraints
        if not native or not native.interactive_resize:
            self.finish()
        else:self.watch_after=self.app.after(16,self._watch)

    def finish(self):
        if not self.active:return
        self.active=False
        for name in ("frame_after","watch_after"):
            token=getattr(self,name)
            if token is not None:self.app.after_cancel(token);setattr(self,name,None)
        # Keep the preview above the controls while their final geometry settles.
        self.app._last_compact_layout=None
        try:self.app._layout_compact()
        finally:self.finish_after=self.app.after_idle(self._reveal)

    def _reveal(self):
        self.finish_after=None
        if self.active or self.app.closing:return
        self.surface.place(x=0,y=0,width=self.app.winfo_width(),height=self.app.winfo_height())
        self.canvas.place_forget()
        self.canvas.itemconfigure(self.item,image="")
        if self.native_image is not None:self.native_image.bitmap=None
        self.snapshot=self.photo=None;self.last_size=None

    def _destroyed(self,event):
        if event.widget is not self.app:return
        for name in ("frame_after","watch_after","finish_after"):
            token=getattr(self,name)
            if token is not None:
                try:self.app.after_cancel(token)
                except tk.TclError:pass
                setattr(self,name,None)
        self.snapshot=self.photo=None;self.active=False
        if self.native_image is not None:self.native_image.close()
