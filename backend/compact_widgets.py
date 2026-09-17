"""Drawn controls for the accepted compact desktop design (no web runtime)."""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
from tkinter import ttk

from backend.compact_model import position_to_volume, volume_to_position
from backend.audio_processing.equalizer import effect_biquads, response_db
from backend.audio_processing.ffmpeg_tools import AudioProcessingError

BG = "#0b1018"
PANEL = "#141c28"
INSET = "#0c131e"
TEXT = "#e3eaf5"
MUTED = "#99a8bd"
LINE = "#283446"
BLUE = "#69a9ff"


def enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def display_metrics(window):
    """Read the window's monitor work area; never change display settings."""
    try:
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
        api = ctypes.windll.user32
        api.MonitorFromWindow.restype = ctypes.c_void_p
        monitor = api.MonitorFromWindow(ctypes.c_void_p(window.winfo_id()), 2)
        info = MonitorInfo(); info.size = ctypes.sizeof(info)
        if not api.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
            raise OSError("Monitor work area unavailable")
        dpi = api.GetDpiForWindow(ctypes.c_void_p(window.winfo_id())) or 96
        return (info.work.left, info.work.top, info.work.right, info.work.bottom), dpi/96
    except (AttributeError, OSError):
        return (0, 0, window.winfo_screenwidth(), window.winfo_screenheight()), float(window.tk.call("tk", "scaling"))/(96/72)


def rounded(canvas, x1, y1, x2, y2, radius, **kwargs):
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return canvas.create_polygon(x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
                                 x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
                                 x1,y2, x1,y2-r, x1,y1+r, x1,y1,
                                 smooth=True, splinesteps=16, **kwargs)


def icon(canvas, name, x, y, scale, color):
    def line(*points, **kw):
        canvas.create_line(*[coord*scale + (x if n%2 == 0 else y) for n,coord in enumerate(points)],
                           fill=color, width=max(1, 1.2*scale), capstyle="round", joinstyle="round", **kw)
    if name == "play":
        line(-4,-6, 5,0, -4,6, -4,-6)
    elif name == "pause":
        line(-3,-5, -3,5); line(3,-5, 3,5)
    elif name == "folder":
        line(-7,5, -7,-5, -2,-5, 0,-3, 7,-3, 7,5, -7,5)
        line(-6,-1, 6,-1)
    elif name == "export":
        line(0,-6, 0,3, -3,0); line(0,3, 3,0); line(-6,2, -6,6, 6,6, 6,2)
    elif name in ("settings", "sliders"):
        for yy, xx in ((-4,2),(1,-3),(6,3)):
            line(-6,yy, 6,yy)
            canvas.create_oval(x+(xx-1.5)*scale,y+(yy-1.5)*scale,
                               x+(xx+1.5)*scale,y+(yy+1.5)*scale, fill=BG, outline=color, width=max(1,scale))
    elif name == "split":
        line(-5,6, -5,-5, -1,-5); line(-3,-7,-1,-5,-3,-3)
        line(4,6, 4,0, 0,-4); line(4,0, 7,-3)
    elif name == "close":
        line(-4,-4,4,4); line(-4,4,4,-4)
    elif name == "wave":
        for xx,hh in ((-6,2),(-3,5),(0,7),(3,4),(6,2)):
            line(xx,-hh,xx,hh)


class CompactButton(tk.Canvas):
    def __init__(self, parent, app, text="", command=None, width=74, icon_name=None, primary=False, toggle=None, active_color=BLUE):
        self.app, self.label, self.command = app, text, command
        self.base_width, self.icon_name, self.primary = width, icon_name, primary
        self.toggle, self.active_color, self.enabled, self.hover = toggle, active_color, True, False
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, takefocus=1)
        self.bind("<Configure>", lambda e:self.draw())
        self.bind("<Enter>", lambda e:self._hover(True)); self.bind("<Leave>", lambda e:self._hover(False))
        self.bind("<Button-1>", self._click)
        # Space belongs to the editor transport, including after Tab navigation.
        self.bind("<Return>", self._key_activate)
        self.bind("<FocusIn>", lambda e:self.draw()); self.bind("<FocusOut>", lambda e:self.draw())
        if toggle:
            toggle.trace_add("write", lambda *a:self.draw())
        self.rescale()

    def rescale(self):
        super().configure(width=self.app.px(self.base_width), height=self.app.px(30))
        self.draw()

    def _hover(self, value):
        self.hover = value; self.draw()

    def _click(self, _event=None):
        if self.enabled:
            # A mouse click finishes text editing without leaving this button
            # selected. Keyboard navigation can still focus it and use Enter.
            self.winfo_toplevel().focus_set()
            try:
                self.invoke()
            finally:
                # A native file dialog can consume the matching mouse release.
                self.app._end_edit_drag()
        return "break"

    def _key_activate(self, _event=None):
        self.invoke()
        return "break"

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def configure(self, cnf=None, **kwargs):
        if "text" in kwargs: self.label = kwargs.pop("text")
        if "state" in kwargs: self.enabled = kwargs.pop("state") != "disabled"
        if "command" in kwargs: self.command = kwargs.pop("command")
        result = super().configure(cnf, **kwargs)
        if hasattr(self, "app"): self.draw()
        return result

    config = configure

    def cget(self, key):
        if key == "text": return self.label
        if key == "state": return "normal" if self.enabled else "disabled"
        return super().cget(key)

    def set_enabled(self, enabled):
        self.enabled = enabled; self.draw()

    def draw(self):
        if not self.winfo_exists(): return
        self.delete("all")
        w,h,s = max(self.winfo_width(),self.winfo_reqwidth()), self.app.px(30), self.app.ui_scale
        selected = bool(self.toggle and self.toggle.get())
        fill = self.active_color if selected else BLUE if self.primary else "#1d2938" if self.hover else "#121c29"
        color = "#192235" if self.primary or (selected and self.active_color == "#edc653") else TEXT
        if not self.enabled: fill,color = "#111925", "#586679"
        border = BLUE if self.focus_get() == self else LINE
        rounded(self,1,1,w-1,h-1,4*s,fill=fill,outline=border,width=max(1,s*.7))
        if self.icon_name:
            ix = w/2 if not self.label else 14*s
            icon(self,self.icon_name,ix,h/2,s*.86,color)
        if self.label:
            tx = (w + (15*s if self.icon_name else 0))/2
            self.create_text(tx,h/2,text=self.label,font=self.app.fonts["body"],fill=color)


class CompactKnob(tk.Canvas):
    def __init__(self, parent, app, getter, setter, limits):
        self.app,self.getter,self.setter,self.limits = app,getter,setter,limits
        self.enabled=True
        super().__init__(parent,bg=PANEL,highlightthickness=0,bd=0,takefocus=1)
        self.bind("<Configure>",lambda e:self.draw())
        self.bind("<Button-1>",self.press); self.bind("<B1-Motion>",self.drag)
        self.bind("<Double-Button-1>",self.reset); self.bind("<MouseWheel>",self.wheel)
        self.bind("<Up>",lambda e:self.step(1)); self.bind("<Down>",lambda e:self.step(-1))
        self.bind("<Home>",self.reset)
        self.rescale()

    def rescale(self):
        self.configure(width=self.app.px(54),height=self.app.px(48)); self.draw()

    def set_enabled(self,value): self.enabled=value; self.draw()

    def value(self):
        try: return float(self.getter())
        except (tk.TclError,ValueError): return 0

    def set(self,value):
        if self.enabled:
            lo,hi,step,_ = self.limits()
            self.setter(round(max(lo,min(hi,round(value/step)*step)),4))
        return "break"

    def press(self,event): self.focus_set(); self.origin=(event.y_root,self.value())
    def drag(self,event):
        lo,hi,step,_ = self.limits()
        self.set(self.origin[1]+(self.origin[0]-event.y_root)/self.app.ui_scale*(hi-lo)/130)
    def step(self,direction): return self.set(self.value()+direction*self.limits()[2])
    def wheel(self,event): return self.step(1 if event.delta>0 else -1)
    def reset(self,_event=None): return self.set(self.limits()[3])

    def draw(self):
        self.delete("all")
        s=self.app.ui_scale; x=self.winfo_width()/2; y=24*s; r=17*s
        lo,hi,_,_=self.limits(); ratio=(self.value()-lo)/max(hi-lo,1)
        angle=math.radians(225-270*ratio)
        self.create_oval(x-r,y-r,x+r,y+r,fill=INSET,outline=LINE,width=max(1,s))
        self.create_line(x+math.cos(angle)*r*.45,y-math.sin(angle)*r*.45,
                         x+math.cos(angle)*r*.86,y-math.sin(angle)*r*.86,
                         fill=BLUE if self.enabled else MUTED,width=max(1,1.4*s))


class CompactFader(tk.Canvas):
    def __init__(self,parent,app,variable):
        self.app,self.variable,self.enabled=app,variable,True
        super().__init__(parent,bg=INSET,highlightthickness=0,bd=0,takefocus=1)
        self.bind("<Configure>",lambda e:self.draw()); self.bind("<Button-1>",self.set_from_event)
        self.bind("<B1-Motion>",self.set_from_event); self.bind("<Double-Button-1>",self.reset)
        self.bind("<MouseWheel>",self.wheel)
        self.bind("<Up>",lambda e:self.step(.005)); self.bind("<Down>",lambda e:self.step(-.005))
        self.bind("<Home>",self.reset)
        variable.trace_add("write",lambda *a:self.draw())

    def set_enabled(self,value): self.enabled=value; self.draw()
    def bounds(self): return self.app.px(10),max(self.app.px(20),self.winfo_height()-self.app.px(10))
    def set_from_event(self,event):
        if self.enabled:
            self.focus_set(); a,b=self.bounds()
            self.variable.set(position_to_volume((b-event.y)/max(1,b-a)))
    def reset(self,_event=None):
        if self.enabled: self.variable.set(100)
        return "break"
    def step(self,delta):
        if self.enabled: self.variable.set(position_to_volume(volume_to_position(self.variable.get())+delta))
        return "break"
    def wheel(self,event): return self.step(.01 if event.delta>0 else -.01)
    def draw(self):
        self.delete("all")
        s=self.app.ui_scale; x=self.winfo_width()*.6; top,bottom=self.bounds()
        color=TEXT if self.enabled else "#596778"
        self.create_line(x,top,x,bottom,fill=LINE,width=max(2,3*s))
        for db,pos in ((12,1),(6,.835),(0,.67),(-12,.536),(-24,.402),(-48,.134),(None,0)):
            y=bottom-pos*(bottom-top)
            text="−∞" if db is None else f"+{db}" if db>0 else str(db).replace("-","−")
            self.create_text(x-14*s,y,text=text,anchor="e",font=self.app.fonts["bold" if db==0 else "small"],fill=color if db==0 else MUTED)
            self.create_line(x-5*s,y,x,y,fill=color if db==0 else LINE,width=max(1,s))
        try: pos=volume_to_position(self.variable.get())
        except tk.TclError: pos=.67
        y=bottom-pos*(bottom-top)
        rounded(self,x-11*s,y-5*s,x+11*s,y+5*s,1.5*s,fill="#b8c6d8" if self.enabled else "#637286",outline="#65778d")
        self.create_line(x-10*s,y,x+10*s,y,fill="#37485d",width=max(1,s))


class CompactEq(tk.Canvas):
    def __init__(self,parent,app):
        self.app,self.enabled,self.drag_band=app,True,None
        super().__init__(parent,bg=INSET,highlightbackground=LINE,highlightthickness=1,bd=0,takefocus=1)
        self.bind("<Configure>",lambda e:self.draw()); self.bind("<Button-1>",self.press)
        self.bind("<B1-Motion>",self.drag); self.bind("<Double-Button-1>",self.reset)
        self.bind("<ButtonRelease-1>",lambda e:setattr(self,"drag_band",None))
        for key in ("Up","Down","Left","Right"):
            self.bind("<"+key+">",lambda e,k=key:self.key(k))
    def set_enabled(self,value): self.enabled=value; self.draw()
    def bounds(self):
        s=self.app.ui_scale
        return 28*s,19*s,max(35*s,self.winfo_width()-12*s),max(30*s,self.winfo_height()-25*s)
    def xy(self,freq,gain):
        l,t,r,b=self.bounds()
        return l+math.log10(max(20,min(20000,freq))/20)/3*(r-l), t+(24-max(-24,min(24,gain)))/48*(b-t)
    def draw(self):
        self.delete("all"); self.handles={}
        l,t,r,b=self.bounds(); s=self.app.ui_scale
        for freq in (20,50,100,200,500,1000,2000,5000,10000,20000):
            x,_=self.xy(freq,0); self.create_line(x,t,x,b,fill=LINE,width=max(1,s*.6))
        for db in (24,12,0,-12,-24):
            _,y=self.xy(20,db); self.create_line(l,y,r,y,fill="#405371" if db==0 else LINE,width=max(1,s*.6))
            self.create_text(l-4*s,y,text=f"+{db}" if db>0 else str(db).replace("-","−"),anchor="e",fill=MUTED,font=self.app.fonts["small"])
        for freq,label in ((20,"20 Hz"),(100,"100"),(1000,"1k"),(10000,"10k"),(20000,"20k")):
            x,_=self.xy(freq,0)
            self.create_text(x,b+12*s,text=label,anchor="w" if freq==20 else "e" if freq==20000 else "center",fill=MUTED,font=self.app.fonts["small"])
        self.create_text(4*s,7*s,text="dB",anchor="w",fill=MUTED,font=self.app.fonts["small"])
        sections=None
        try:
            effects=self.app._build_audio_effects(); sections=effect_biquads(effects)
            points=[]
            for i in range(181):
                freq=20*10**(3*i/180)
                points.extend(self.xy(freq,response_db(sections,freq,effects.sample_rate)))
            self.create_line(*points,fill=BLUE,width=max(1.5,2*s))
            self.app._set_eq_validation_error("")
        except AudioProcessingError as exc:
            self.app._set_eq_validation_error(str(exc))
        except (ValueError,tk.TclError):
            pass
        try:
            # Keep the frequency handles reachable while an invalid pass pair
            # is being corrected; no response curve is drawn for invalid audio.
            for index,band in enumerate(("low","mid","high"),1):
                freq=getattr(self.app,"eq_"+band+"_freq_var").get()
                if self.app._band_is_pass(band):
                    gain=response_db(sections,freq,effects.sample_rate) if sections is not None else 0
                else:gain=getattr(self.app,"eq_"+band+"_var").get()
                x,y=self.xy(freq,gain); self.handles[band]=(x,y)
                self.create_oval(x-9*s,y-9*s,x+9*s,y+9*s,fill=BLUE if self.enabled else "#536e92",outline="")
                self.create_text(x,y,text=str(index),fill="#12233b",font=self.app.fonts["small"])
        except (ValueError,tk.TclError):
            pass
    def nearest(self,event):
        if not self.handles: return None
        return min(self.handles,key=lambda k:(self.handles[k][0]-event.x)**2+(self.handles[k][1]-event.y)**2)
    def press(self,event):
        if not self.enabled: return
        self.focus_set(); self.drag_band=self.nearest(event); self.selected_band=self.drag_band
        if self.drag_band:
            self.origin=(event.y,self.app._band_value(self.drag_band))
    def drag(self,event):
        if not self.enabled or not self.drag_band: return
        band=self.drag_band; l,t,r,b=self.bounds()
        lo,hi=self.app._band_frequency_limits(band)
        freq=round(max(lo,min(hi,20*10**(3*max(0,min(1,(event.x-l)/max(1,r-l)))))))
        getattr(self.app,"eq_"+band+"_freq_var").set(freq)
        if self.app._band_is_pass(band): value=self.origin[1]+round((self.origin[0]-event.y)/(16*self.app.ui_scale))*12
        else: value=round((24-48*(event.y-t)/max(1,b-t))*2)/2
        self.app._set_band_value(band,value)
    def reset(self,event):
        if self.enabled:
            band=self.nearest(event)
            if band:self.app._set_band_value(band,24 if self.app._band_is_pass(band) else 0)
        return "break"
    def key(self,key):
        band=getattr(self,"selected_band","mid")
        if not self.enabled:return "break"
        if key in ("Up","Down"):
            self.app._set_band_value(band,self.app._band_value(band)+(1 if key=="Up" else -1)*(12 if self.app._band_is_pass(band) else .5))
        else:
            variable=getattr(self.app,"eq_"+band+"_freq_var"); lo,hi=self.app._band_frequency_limits(band)
            variable.set(round(max(lo,min(hi,variable.get()*(1.03 if key=="Right" else 1/1.03)))))
        return "break"


class EditorViewport(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG)
        self.columnconfigure(0,weight=1);self.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=0,bd=0)
        self.canvas.grid(row=0,column=0,sticky="nsew")
        self.bar=ttk.Scrollbar(self,orient="vertical",command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.content=tk.Frame(self.canvas,bg=BG)
        self.window_id=self.canvas.create_window(0,0,window=self.content,anchor="nw")
    def layout(self,height):
        width=self.canvas.winfo_width()
        self.canvas.itemconfigure(self.window_id,width=width,height=height)
        self.canvas.configure(scrollregion=(0,0,width,height))
        if height>self.canvas.winfo_height()+2:self.bar.grid(row=0,column=1,sticky="ns")
        else:self.bar.grid_remove();self.canvas.yview_moveto(0)
