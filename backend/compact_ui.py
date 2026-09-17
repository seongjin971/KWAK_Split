"""Approved compact Tkinter surface, wired to the existing audio/workspace engine."""
from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

from backend.compact_model import (EQ_GAIN_LIMIT, TIME_QUANTUM, initial_window,
    position_to_volume, selection_step, volume_label, volume_to_position)
from backend.numeric_gestures import NumericGestures
from backend.compact_widgets import (BG, PANEL, INSET, TEXT, MUTED, LINE, BLUE,
    CompactButton, CompactKnob, CompactFader, CompactEq, EditorViewport, display_metrics, icon)
from backend.project_store import EDIT_DEFAULTS, EditHistory
from backend.workspace_features import StemRangeError
from backend.ui_helpers import ToolTip


class CompactInterface:
    def open_audio(self): self.load_file()

    def px(self,value): return max(1,round(value*self.ui_scale))

    def _configure_theme(self):
        _,scale=display_metrics(self)
        self.ui_scale=self._ui_scale_override or scale
        self.fonts={name:font.Font(self,family="Segoe UI",size=-self.px(size),weight=weight)
                    for name,size,weight in (("body",12,"normal"),("small",10,"normal"),
                                             ("bold",11,"bold"),("title",14,"bold"))}
        self.configure(bg=BG)
        style=ttk.Style(self);style.theme_use("clam")
        style.configure("TEntry",fieldbackground=INSET,foreground=TEXT,insertcolor=TEXT,
                        bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=self.px(4),font=self.fonts["body"])
        for name in ("TSpinbox","TCombobox"):
            style.configure(name,fieldbackground=INSET,background=INSET,foreground=TEXT,arrowcolor=MUTED,
                            bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=self.px(3),font=self.fonts["body"])
            style.map(name,fieldbackground=[("readonly",INSET),("disabled",INSET)],
                      foreground=[("disabled","#5e6c7e"),("readonly",TEXT)],selectbackground=[("!disabled","#25446b")],
                      selectforeground=[("!disabled",TEXT)])
        style.configure("Vertical.TScrollbar",background=LINE,troughcolor=BG,arrowcolor=MUTED,borderwidth=0)
        style.configure("Horizontal.TProgressbar",background=BLUE,troughcolor=INSET,borderwidth=0)
        self.option_add("*TCombobox*Listbox.background",INSET)
        self.option_add("*TCombobox*Listbox.foreground",TEXT)
        self.option_add("*TCombobox*Listbox.font",self.fonts["body"])

    def _label(self,parent,text="",variable=None,kind="body",color=TEXT,**kwargs):
        options=dict(bg=parent.cget("bg"),fg=color,font=self.fonts[kind],anchor="w",bd=0)
        options.update(kwargs)
        if variable is not None:options["textvariable"]=variable
        else:options["text"]=text
        return tk.Label(parent,**options)

    def _button(self,parent,text="",command=None,**kwargs):
        widget=CompactButton(parent,self,text,command,**kwargs)
        self._track_edit_widget(widget)
        self.compact_buttons.append(widget)
        return widget

    def _track_edit_widget(self,widget):
        # Tk dispatches a widget's binding before the global binding. Take the
        # initial snapshot first, before a fader jump/spin arrow/toggle mutates it.
        tag="KwakEditStart"
        if not getattr(self,"_edit_tag_bound",False):
            for button in (1,3):
                self.bind_class(tag,f"<ButtonPress-{button}>",self._begin_edit_drag)
            self._edit_tag_bound=True
        tags=widget.bindtags()
        if tag not in tags:widget.bindtags((tag,*tags))

    def _spin(self,parent,variable,minimum,maximum,step=1,width=6,fmt=None):
        display=tk.StringVar(value=(fmt % variable.get()) if fmt else f"{variable.get():g}")
        updating=[False]
        options=dict(from_=minimum,to=maximum,increment=step,textvariable=display,width=width,
                     justify="left",font=self.fonts["body"])
        if fmt: options["format"]=fmt
        widget=ttk.Spinbox(parent,**options)
        self._track_edit_widget(widget)
        def to_model(*_args):
            if updating[0] or not widget.winfo_exists():return
            try:value=float(display.get())
            except ValueError:return
            if not math.isfinite(value):return
            updating[0]=True
            try:variable.set(value)
            finally:updating[0]=False
        def to_display(*_args):
            if updating[0] or not widget.winfo_exists():return
            updating[0]=True
            try:
                value=variable.get();display.set(fmt % value if fmt else f"{value:g}")
            except (ValueError,tk.TclError):pass
            finally:updating[0]=False
        display.trace_add("write",to_model)
        display_trace=variable.trace_add("write",to_display)
        widget.bind("<Destroy>",lambda event:variable.trace_remove("write",display_trace) if event.widget==widget else None)
        self._numeric_fields.append((widget,display,variable,fmt))
        widget.bind("<Return>",lambda e:self._commit_numeric(widget))
        widget.bind("<FocusOut>",lambda e:self._commit_numeric(widget))
        time_field=variable in (self.selection_start_var,self.selection_end_var)
        quantum=TIME_QUANTUM if time_field else 10**-int(fmt.split(".")[1][:-1]) if fmt and "." in fmt else step
        def increment():
            if time_field:
                start,end=self._wave_view_bounds()
                return selection_step(end-start)
            return step
        widget.numeric_gestures=NumericGestures(self,widget,variable.get,variable.set,
            lambda:(float(widget.cget("from")),float(widget.cget("to"))),increment,quantum,
            commit=lambda:self._commit_numeric(widget))
        return widget

    def _edit_snapshot(self):
        for widget,display,variable,fmt in getattr(self,"_numeric_fields",[]):
            if not widget.winfo_exists():continue
            try:value=float(display.get())
            except ValueError:raise ValueError("Complete the numeric input before continuing.") from None
            if not math.isfinite(value) or not float(widget.cget("from"))<=value<=float(widget.cget("to")):
                raise ValueError("A numeric input is outside its allowed range.")
        return super()._edit_snapshot()

    def _commit_numeric(self,widget):
        if self.closing:return
        try:
            self._edit_snapshot()
        except (ValueError,tk.TclError) as exc:
            self.status_var.set(str(exc) if not isinstance(exc,tk.TclError) else "Enter a valid number.")
            return
        self._selection_changed();self._commit_edit()
        for entry,display,variable,fmt in self._numeric_fields:
            if entry==widget and fmt:display.set(fmt % variable.get())
        if self.preview_playing and widget in (self.start_spinbox,self.end_spinbox):
            self._restart_context_preview_from_cursor()

    def _build_ui(self):
        self.compact_buttons=[]; self.compact_knobs={}; self.band_values={};self._numeric_fields=[]
        self._layout_after=None;self._compact_after=None;self._dialog=None;self._log_window=None
        self._layout_mode=None
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        self.header=tk.Frame(self,bg=BG,highlightbackground=LINE,highlightthickness=1)
        self.header.grid(row=0,column=0,sticky="ew")
        self.header.columnconfigure(0,weight=1)
        brand_box=tk.Frame(self.header,bg=BG)
        brand_box.grid(row=0,column=0,sticky="w",padx=self.px(12))
        self.brand_icon=tk.Canvas(brand_box,bg=BG,highlightthickness=0,width=self.px(18),height=self.px(22))
        self.brand_icon.pack(side="left",padx=(0,self.px(6)))
        icon(self.brand_icon,"wave",self.px(9),self.px(11),self.ui_scale*.8,MUTED)
        self.brand=self._label(brand_box,"KWAK Split",kind="title");self.brand.pack(side="left")
        self.load_button=self._button(self.header,"Open Audio",self.open_audio,width=112,icon_name="folder")
        self.settings_button=self._button(self.header,command=self.open_render_settings,width=34,icon_name="settings")
        self.render_button=self._button(self.header,"WAV",self.render_wav,width=76,icon_name="export",primary=True)
        self.render_mp3_button=self._button(self.header,"MP3",self.render_mp3,width=76,icon_name="export",primary=True)
        for column,widget in enumerate((self.load_button,self.settings_button,self.render_button,self.render_mp3_button),1):
            widget.grid(row=0,column=column,padx=(0,self.px(7)),pady=self.px(7))
        self.tooltips.append(ToolTip(self.settings_button,"Settings"))
        self.workspace_scroll=EditorViewport(self)
        self.workspace_scroll.grid(row=1,column=0,sticky="nsew")
        body=self.workspace_scroll.content;body.columnconfigure(0,weight=1)
        self.timeline=tk.Frame(body,bg=BG)
        self.timeline.grid(row=0,column=0,sticky="nsew",padx=self.px(10),pady=(self.px(5),0))
        self.timeline.columnconfigure(0,weight=1);self.timeline.rowconfigure(1,weight=1)
        self.metadata=tk.Frame(self.timeline,bg=BG)
        self.metadata.grid(row=0,column=0,sticky="ew",pady=(0,self.px(6)))
        self.metadata.columnconfigure(0,weight=1)
        self.file_meta=tk.Frame(self.metadata,bg=BG)
        self.file_meta.grid(row=0,column=0,sticky="ew")
        self.display_file_var=tk.StringVar(value="No file")
        self.file_name_label=self._label(self.file_meta,variable=self.display_file_var,kind="bold")
        self.file_name_label.pack(side="left")
        self.audio_meta_var=tk.StringVar(value="")
        self._label(self.file_meta,variable=self.audio_meta_var,kind="small",color=MUTED).pack(side="left",padx=self.px(7))
        self.selection_controls=tk.Frame(self.metadata,bg=BG)
        self.selection_controls.grid(row=0,column=1,sticky="e")
        self._label(self.selection_controls,"Start",kind="small",color=MUTED).pack(side="left",padx=(0,self.px(4)))
        self.start_spinbox=self._spin(self.selection_controls,self.selection_start_var,0,1,.01,6,"%.2f")
        self.start_spinbox.pack(side="left")
        self._label(self.selection_controls,"End",kind="small",color=MUTED).pack(side="left",padx=self.px(5))
        self.end_spinbox=self._spin(self.selection_controls,self.selection_end_var,0,1,.01,6,"%.2f")
        self.end_spinbox.pack(side="left")
        self.selection_label=self._label(self.selection_controls,"0.00s",kind="small",color=MUTED,width=7)
        self.selection_label.pack(side="left",padx=self.px(3))
        self.play_button=self._button(self.selection_controls,"Play",self.toggle_playback,width=76,icon_name="play")
        self.play_button.pack(side="left")
        self.wave_canvas=tk.Canvas(self.timeline,bg=INSET,highlightbackground=LINE,highlightthickness=1,bd=0,takefocus=1)
        self._track_edit_widget(self.wave_canvas)
        self.wave_canvas.grid(row=1,column=0,sticky="nsew",pady=(0,self.px(8)))
        self.wave_canvas.bind("<Configure>",self._schedule_waveform_resize_draw)
        self.wave_canvas.bind("<Button-1>",self._wave_seek_to_event)
        self.wave_canvas.bind("<Button-3>",self._wave_mouse_down)
        self.wave_canvas.bind("<B3-Motion>",self._wave_mouse_drag)
        self.wave_canvas.bind("<ButtonRelease-3>",self._wave_mouse_up)
        self.wave_canvas.bind("<MouseWheel>",self._wave_zoom_at_pointer)
        for key in ("plus","equal","minus","0"):
            self.wave_canvas.bind("<Key-"+key+">",lambda e,k=key:self._wave_key(k))
        self.editors=tk.Frame(body,bg=BG)
        self.editors.grid(row=1,column=0,sticky="nsew",padx=self.px(10),pady=(0,self.px(10)))
        self.eq_panel=tk.Frame(self.editors,bg=PANEL,highlightbackground=LINE,highlightthickness=1)
        self.mixer_panel=tk.Frame(self.editors,bg=PANEL,highlightbackground=LINE,highlightthickness=1)
        self._build_compact_eq();self._build_compact_mixer()
        self.status_frame=tk.Frame(self,bg=BG)
        self.status_frame.columnconfigure(0,weight=1)
        self.status_label=self._label(self.status_frame,variable=self.status_var,kind="small",color=MUTED,wraplength=self.px(750))
        self.status_label.grid(row=0,column=0,sticky="w",padx=self.px(10),pady=self.px(5))
        self.status_label.bind("<Button-1>",lambda e:self.open_result_folder() if self.result_files else None)
        self.cancel_button=self._button(self.status_frame,"Cancel",self.cancel_current_operation,width=70)
        self.cancel_button.grid(row=0,column=1,padx=self.px(8))
        self.progressbar=ttk.Progressbar(self.status_frame,variable=self.progress_var,maximum=100)
        self.progressbar.grid(row=1,column=0,columnspan=2,sticky="ew")
        self.status_var.trace_add("write",self._status_changed)
        self.file_label_var.trace_add("write",lambda *a:self._schedule_compact_layout())
        self.workspace_scroll.canvas.bind("<Configure>",self._schedule_compact_layout)
        self.bind("<Configure>",self._root_configured,add="+")
        self.bind_all("<MouseWheel>",self._scroll_editor,add="+")
        self._set_initial_compact_window()
        self._schedule_compact_layout()

    def _set_initial_compact_window(self):
        area,_=display_metrics(self);l,t,r,b=area
        width,height=initial_window(r-l,b-t,self.ui_scale)
        self.minsize(min(self.px(640),width),min(self.px(480),height))
        self.geometry(f"{width}x{height}+{l+max(0,(r-l-width)//2)}+{t+max(0,(b-t-height)//3)}")

    def _build_compact_eq(self):
        panel=self.eq_panel;panel.columnconfigure(0,weight=1);panel.rowconfigure(1,weight=1)
        heading=tk.Frame(panel,bg=PANEL);heading.grid(row=0,column=0,sticky="ew",padx=self.px(8),pady=self.px(7))
        self._label(heading,"EQUALIZER",kind="bold",color=MUTED).pack(side="left")
        self.advanced_button=self._button(heading,"Advanced",self.open_advanced,width=94,icon_name="sliders")
        self.advanced_button.pack(side="right")
        self.eq_editor=CompactEq(panel,self)
        self.eq_editor.grid(row=1,column=0,sticky="nsew",padx=self.px(8))
        self.bands=tk.Frame(panel,bg=PANEL)
        self.bands.grid(row=2,column=0,sticky="ew",padx=self.px(8),pady=self.px(5))
        self.eq_shape_widgets=[]
        for index,band in enumerate(("low","mid","high")):
            self.bands.columnconfigure(index,weight=1,uniform="bands")
            box=tk.Frame(self.bands,bg=PANEL);box.grid(row=0,column=index,sticky="nsew",padx=self.px(4))
            box.columnconfigure(0,weight=1)
            box.rowconfigure(0,minsize=self.px(28))
            name=tk.Frame(box,bg=PANEL);name.grid(row=0,column=0,sticky="ew")
            self._label(name,str(index+1),kind="small",color=MUTED).pack(side="left",padx=(0,self.px(5)))
            if band=="mid":self._label(name,"Mid Bell",kind="small").pack(side="left")
            else:
                combo=ttk.Combobox(name,textvariable=getattr(self,"eq_"+band+"_shape_var"),state="readonly",width=10,
                                   values=("Low Shelf","High Pass") if band=="low" else ("High Shelf","Low Pass"),font=self.fonts["small"])
                combo.pack(side="left",fill="x",expand=True);self.effect_widgets.append(combo);self.eq_shape_widgets.append(combo)
                combo.bind("<<ComboboxSelected>>",lambda e,b=band:self._mode_changed(b))
            knob=CompactKnob(box,self,lambda b=band:self._band_value(b),lambda v,b=band:self._set_band_value(b,v),
                              lambda b=band:(12,48,12,24) if self._band_is_pass(b) else (-EQ_GAIN_LIMIT,EQ_GAIN_LIMIT,.5,0))
            knob.grid(row=1,column=0);self.compact_knobs[band]=knob;self.effect_widgets.append(knob)
            value=tk.StringVar(value="0 dB");self.band_values[band]=value
            readout=self._label(box,variable=value,kind="small",anchor="center",cursor="sb_v_double_arrow")
            readout.grid(row=2,column=0,pady=(0,self.px(3)))
            self._track_edit_widget(readout)
            readout.bind("<Button-1>",knob.press);readout.bind("<B1-Motion>",knob.drag)
            readout.bind("<MouseWheel>",knob.wheel);readout.bind("<Double-Button-1>",knob.reset)
            frequency=tk.Frame(box,bg=PANEL);frequency.grid(row=3,column=0)
            lo,hi=self._band_frequency_limits(band)
            entry=self._spin(frequency,getattr(self,"eq_"+band+"_freq_var"),lo,hi,10 if band=="low" else 50 if band=="mid" else 100,6,"%.0f")
            entry.pack(side="left");self.effect_widgets.append(entry)
            self._label(frequency,"Hz",kind="small",color=MUTED).pack(side="left",padx=self.px(3))
        self.timing=tk.Frame(panel,bg=PANEL,highlightbackground=LINE,highlightthickness=0)
        self.timing.grid(row=3,column=0,sticky="ew",padx=self.px(8),pady=(self.px(4),self.px(8)))
        self.timing_cells=[]
        for label,name,variable,lo,hi,step,unit,fmt in (
            ("Speed","tempo_spinbox",self.tempo_percent_var,50,200,1,"%","%.0f"),
            ("Pitch","pitch_spinbox",self.pitch_semitones_var,-12,12,1,"st","%.0f"),
            ("Fade in","fade_in_spinbox",self.fade_in_var,0,10,.01,"s","%.2f"),
            ("Fade out","fade_out_spinbox",self.fade_out_var,0,10,.01,"s","%.2f")):
            cell=tk.Frame(self.timing,bg=PANEL);self.timing_cells.append(cell)
            self._label(cell,label,kind="small",color=MUTED).pack(side="left",padx=(0,self.px(3)))
            entry=self._spin(cell,variable,lo,hi,step,4,fmt);entry.configure(font=self.fonts["small"])
            entry.pack(side="left");setattr(self,name,entry);self.effect_widgets.append(entry)
            self._label(cell,unit,kind="small",color=MUTED).pack(side="left",padx=(self.px(3),0))

    def _build_compact_mixer(self):
        panel=self.mixer_panel;panel.columnconfigure(0,weight=1);panel.rowconfigure(1,weight=1)
        heading=tk.Frame(panel,bg=PANEL);heading.grid(row=0,column=0,sticky="ew",padx=self.px(8),pady=self.px(7))
        self._label(heading,"STEM MIXER",kind="bold",color=MUTED).pack(side="left")
        self.separate_button=self._button(heading,"Split Stems",self.separate_stems,width=106,icon_name="split")
        self.separate_button.pack(side="right")
        self.stem_cards=tk.Frame(panel,bg=PANEL)
        self.stem_cards.grid(row=1,column=0,sticky="nsew",padx=self.px(8),pady=(0,self.px(8)))
        self.stem_cards.rowconfigure(0,weight=1);self.stem_name_labels={}
        for index,(stem,color) in enumerate(zip(("vocals","drums","bass","other"),("#73b9ff","#dbb875","#b193d9","#8dcfc4"))):
            self.stem_cards.columnconfigure(index,weight=1,uniform="stems")
            card=tk.Frame(self.stem_cards,bg=INSET);card.grid(row=0,column=index,sticky="nsew",padx=(0,self.px(4) if index<3 else 0))
            card.columnconfigure(0,weight=1);card.rowconfigure(3,weight=1)
            tk.Frame(card,bg=color,height=self.px(2)).grid(row=0,column=0,sticky="ew")
            label=self._label(card,stem.title(),kind="small",anchor="center")
            label.grid(row=1,column=0,sticky="ew",pady=(self.px(10),self.px(7)));self.stem_name_labels[stem]=label
            volume=tk.DoubleVar(value=100);mute=tk.BooleanVar(value=False);solo=tk.BooleanVar(value=False)
            self.stem_vars[stem]={"volume":volume,"mute":mute,"solo":solo}
            text=tk.StringVar(value="0.0 dB");self.stem_volume_label_vars[stem]=text
            readout=self._label(card,variable=text,kind="small",anchor="center",cursor="sb_v_double_arrow")
            readout.grid(row=2,column=0)
            readout.numeric_gestures=NumericGestures(self,readout,
                lambda v=volume:volume_to_position(v.get()),lambda value,v=volume:v.set(position_to_volume(value)),
                lambda:(0,1),lambda:.005,.001,enabled=lambda name=stem:name in self.stem_paths)
            readout.bind("<Double-Button-1>",lambda e,v=volume,name=stem:v.set(100) if name in self.stem_paths else None)
            fader=CompactFader(card,self,volume);fader.grid(row=3,column=0,sticky="nsew",pady=self.px(2))
            buttons=tk.Frame(card,bg=INSET);buttons.grid(row=4,column=0,pady=(0,self.px(8)))
            m=self._button(buttons,"M",lambda v=mute:v.set(not v.get()),width=28,toggle=mute,active_color="#edc653")
            so=self._button(buttons,"S",lambda v=solo:v.set(not v.get()),width=28,toggle=solo,active_color="#ba343c")
            m.pack(side="left",padx=(0,self.px(3)));so.pack(side="left")
            self.stem_widgets[stem]=[fader,m,so]
            volume.trace_add("write",lambda *a,b=stem:self._on_stem_volume_changed(b))
            for v in (mute,solo):v.trace_add("write",self._mixer_changed)
            self.tooltips.extend((ToolTip(m,"Mute "+stem+". Mute takes precedence over Solo."),ToolTip(so,"Solo "+stem)))

    def _band_is_pass(self,band):
        return band!="mid" and getattr(self,"eq_"+band+"_shape_var").get() in ("High Pass","Low Pass")
    def _band_frequency_limits(self,band): return {"low":(20,2000),"mid":(250,8000),"high":(1000,20000)}[band]
    def _band_value_var(self,band):
        return getattr(self,("high_pass_slope_var" if band=="low" else "low_pass_slope_var") if self._band_is_pass(band) else "eq_"+band+"_var")
    def _band_value(self,band): return self._band_value_var(band).get()
    def _set_band_value(self,band,value):
        self._band_value_var(band).set(int(max(12,min(48,round(value/12)*12))) if self._band_is_pass(band) else max(-EQ_GAIN_LIMIT,min(EQ_GAIN_LIMIT,value)))
    def _mode_changed(self,band):
        # Clear a legacy independent cut only when the user explicitly changes its mode.
        getattr(self,"high_pass_var" if band=="low" else "low_pass_var").set(0)
        self._schedule_compact_render();self._schedule_live_preview_restart()
    def _mixer_changed(self,*_args):
        self._schedule_live_preview_restart();self._schedule_compact_render()

    def _finish_workspace(self):
        self._history_suspended=False;self.history=EditHistory(self._edit_snapshot())
        for widget in (self.eq_editor,*self.effect_widgets,
                       *(widgets[0] for widgets in self.stem_widgets.values())):
            self._track_edit_widget(widget)
        for variable in self._edit_variables():
            variable.trace_add("write",self._queue_edit)
            variable.trace_add("write",self._schedule_compact_render)
        for variable in (self.selection_start_var,self.selection_end_var):variable.trace_add("write",self._queue_selection_display)
        for name in EDIT_DEFAULTS:
            if name.startswith(("eq_","high_pass","low_pass","pitch_","tempo_","limiter")):
                getattr(self,name+"_var").trace_add("write",lambda *a:self._schedule_live_preview_restart())
        for variable in (self.fade_in_var,self.fade_out_var):
            variable.trace_add("write",lambda *a:self._schedule_fade_live_preview_restart())
            variable.trace_add("write",lambda *a:self._schedule_fade_waveform_draw())
        for button in (1,3):
            self.bind_all(f"<ButtonRelease-{button}>",self._end_edit_drag,add="+")
        for chord,action in (("<Control-z>",self.undo_edit),("<Control-y>",self.redo_edit),("<Control-Shift-Z>",self.redo_edit),
                              ("<Control-o>",self.open_audio),("<Control-s>",self.save_current_project),
                              ("<Control-Shift-O>",self.open_project),("<Control-Shift-R>",self.restore_last_session)):
            self.bind(chord,lambda e,a=action:self._shortcut(a),add="+")
        self.tooltips.append(ToolTip(self.wave_canvas,"Click to seek; right-drag to select. Wheel: zoom at pointer. Shift+wheel: pan. + / −: zoom; 0: fit."))
        self._schedule_compact_render()
        self.after_idle(self._compact_environment_status)

    def _text_focus(self):
        widget=self.focus_get()
        return widget is not None and widget.winfo_class() in ("TEntry","Entry","TSpinbox","Spinbox","TCombobox","Text")
    def _shortcut(self,action):
        if self._text_focus() or self._dialog is not None:return
        action();return "break"
    def _bind_space_shortcut(self,_widget): pass
    def _space_toggle_playback(self,_event=None):
        if self._text_focus() or self._dialog is not None:return
        self.toggle_playback();return "break"
    def _compact_environment_status(self):
        self._check_environment_status()
        if self.status_var.get().startswith("Ready"):self.status_var.set("")

    def _root_configured(self,event):
        if event.widget!=self:return
        if self._ui_scale_override is None:
            area,scale=display_metrics(self)
            if abs(scale-self.ui_scale)>.03:
                ratio=scale/self.ui_scale
                def rescale_spacing(parent):
                    for child in parent.winfo_children():
                        manager=child.winfo_manager()
                        if manager in ("grid","pack"):
                            data=child.grid_info() if manager=="grid" else child.pack_info()
                            spacing={}
                            for key in ("padx","pady","ipadx","ipady"):
                                value=data.get(key,0)
                                numbers=value if isinstance(value,tuple) else (value,)
                                spacing[key]=tuple(round(float(v)*ratio) for v in numbers)
                            (child.grid_configure if manager=="grid" else child.pack_configure)(**spacing)
                        rescale_spacing(child)
                rescale_spacing(self)
                self.ui_scale=scale
                for name,size in (("body",12),("small",10),("bold",11),("title",14)):self.fonts[name].configure(size=-self.px(size))
                for widget in self.compact_buttons:
                    if widget.winfo_exists():widget.rescale()
                for widget in self.compact_knobs.values():widget.rescale()
                for child in self.bands.winfo_children():child.rowconfigure(0,minsize=self.px(28))
                self.brand_icon.configure(width=self.px(18),height=self.px(22));self.brand_icon.delete("all")
                icon(self.brand_icon,"wave",self.px(9),self.px(11),self.ui_scale*.8,MUTED)
                l,t,r,b=area
                available=initial_window(r-l,b-t,self.ui_scale)
                self.minsize(min(self.px(640),available[0]),min(self.px(480),available[1]))
                if self.winfo_width()>r-l-20 or self.winfo_height()>b-t-50:
                    self.geometry(f"{min(self.winfo_width(),r-l-20)}x{min(self.winfo_height(),b-t-50)}+{l+10}+{t+10}")
        self._schedule_compact_layout()
    def _schedule_compact_layout(self,*_args):
        if self.closing or self._layout_after:return
        self._layout_after=self.after_idle(self._layout_compact)
    def _layout_compact(self):
        self._layout_after=None
        if self.closing:return
        canvas=self.workspace_scroll.canvas;s=self.ui_scale
        width=max(1,canvas.winfo_width())/s;height=max(1,canvas.winfo_height())/s
        narrow=width<740;self._layout_mode="stacked" if narrow else "side-by-side"
        timeline=174 if width>=600 else 205
        self.timeline.configure(height=self.px(timeline));self.timeline.grid_propagate(False)
        if width<600:
            self.selection_controls.grid(row=1,column=0,sticky="e",pady=self.px(4));self.metadata.columnconfigure(1,weight=0)
        else:self.selection_controls.grid(row=0,column=1,sticky="e",pady=0)
        eq_height=max(332,height-timeline-19) if not narrow else 332
        total=timeline+eq_height+19 if not narrow else timeline+eq_height+348+25
        self.editors.configure(height=self.px(total-timeline-15));self.editors.grid_propagate(False)
        for row in (0,1):self.editors.rowconfigure(row,weight=0,minsize=0)
        for column in (0,1):self.editors.columnconfigure(column,weight=0,minsize=0,uniform="")
        self.eq_panel.grid_propagate(False);self.mixer_panel.grid_propagate(False)
        self.eq_panel.configure(width=1,height=self.px(eq_height))
        self.mixer_panel.configure(width=1,height=self.px(348 if narrow else eq_height))
        if narrow:
            self.editors.columnconfigure(0,weight=1)
            self.editors.rowconfigure(0,minsize=self.px(eq_height));self.editors.rowconfigure(1,minsize=self.px(348))
            self.eq_panel.grid(row=0,column=0,sticky="nsew",padx=0,pady=(0,self.px(8)))
            self.mixer_panel.grid(row=1,column=0,sticky="nsew",padx=0,pady=0)
        else:
            self.editors.columnconfigure(0,weight=56,uniform="editor");self.editors.columnconfigure(1,weight=44,uniform="editor")
            self.editors.rowconfigure(0,weight=1)
            self.eq_panel.grid(row=0,column=0,sticky="nsew",padx=(0,self.px(8)),pady=0)
            self.mixer_panel.grid(row=0,column=1,sticky="nsew",padx=0,pady=0)
        eq_width=(width-22 if narrow else (width-30)*.56)
        wrap=eq_width<385
        for i,cell in enumerate(self.timing_cells):
            cell.grid(row=i//2 if wrap else 0,column=i%2 if wrap else i,sticky="w",padx=(0,self.px(4)),pady=self.px(2))
        for i in range(4):self.timing.columnconfigure(i,weight=1 if i<(2 if wrap else 4) else 0)
        self.workspace_scroll.layout(self.px(total))
        self.status_label.configure(wraplength=max(self.px(200),self.winfo_width()-self.px(115)))
        self._update_file_metadata();self.draw_waveform();self.eq_editor.draw()

    def _update_file_metadata(self):
        if self.duration_seconds:
            channels=getattr(self,"source_channels",2)
            self.audio_meta_var.set(self._format_duration(self.duration_seconds)+" · "+("Mono" if channels==1 else "Stereo"))
        else:self.audio_meta_var.set("")
        full=self.file_label_var.get();available=max(self.px(70),self.file_meta.winfo_width()-self.px(102))
        short=full
        while len(short)>5 and self.fonts["bold"].measure(short)>available:short=short[:-2]
        self.display_file_var.set(short+"…" if short!=full else full)

    def _schedule_compact_render(self,*_args):
        if self.closing or self._compact_after:return
        self._compact_after=self.after_idle(self._render_compact)
    def _render_compact(self):
        self._compact_after=None
        if self.closing:return
        try:
            for band,value in self.band_values.items():
                number=self._band_value(band)
                value.set(f"{number:g} dB/oct" if self._band_is_pass(band) else f"{number:+g} dB" if number else "0 dB")
                self.compact_knobs[band].draw()
            any_solo=any(v["solo"].get() for v in self.stem_vars.values())
            for stem,values in self.stem_vars.items():
                audible=not values["mute"].get() and (not any_solo or values["solo"].get())
                self.stem_name_labels[stem].configure(fg=TEXT if audible else "#617086")
                self._update_volume_label(stem)
            self.eq_editor.draw()
        except (ValueError,tk.TclError):pass

    def _set_eq_validation_error(self,error):
        previous=getattr(self,"_eq_validation_error","")
        message=f"EQ: {error}" if error else ""
        self._eq_validation_error=message
        if message:
            if self.status_var.get()!=message:self.status_var.set(message)
        elif previous and self.status_var.get()==previous:self.status_var.set("")

    def _status_changed(self,*_args):
        message=self.status_var.get()
        routine=message.startswith(("Loaded:","Preview playing:","Realtime preview:","Playing:","Playback stopped.","Playback complete.","Playback finished.","Stem Split complete.","Stem Split already ready.","Ready"))
        if (message and not routine) or self.busy:self.status_frame.grid(row=2,column=0,sticky="ew")
        else:self.status_frame.grid_remove()
        if self.busy:self.progressbar.grid();self.cancel_button.grid()
        else:self.progressbar.grid_remove();self.cancel_button.grid_remove()
        self._schedule_compact_layout()

    def _refresh_action_states(self):
        if not hasattr(self,"load_button"):return
        idle=not self.busy;source=self.source_wav is not None
        for widget,enabled in ((self.load_button,idle),(self.settings_button,idle),(self.advanced_button,idle),
                               (self.separate_button,idle and source),(self.play_button,(idle and source) or self.preview_playing),
                               (self.render_button,idle and source),(self.render_mp3_button,idle and source),
                               (self.start_spinbox,idle and source),(self.end_spinbox,idle and source)):
            self._set_state(widget,enabled)
        for widget in self.effect_widgets:self._set_state(widget,idle and source)
        self.eq_editor.set_enabled(idle and source)
        for stem,widgets in self.stem_widgets.items():
            for widget in widgets:self._set_state(widget,idle and stem in self.stem_paths)
        self.play_button.icon_name="pause" if self.preview_playing else "play"
        self.play_button.configure(text="Pause" if self.preview_playing else "Play")
        self._set_state(self.cancel_button,self.busy)
        self._status_changed();self._update_workspace_summary();self._schedule_compact_render();self._sync_stem_range_notice()

    def _sync_stem_range_notice(self):
        if self.busy:return
        previous=getattr(self,"_stem_coverage_notice","")
        message=""
        try:self._validate_stem_range(*self._selection_bounds_no_error())
        except StemRangeError as exc:message=str(exc)
        self._stem_coverage_notice=message
        if message:
            if self.status_var.get()!=message:self.status_var.set(message)
        elif previous and self.status_var.get()==previous:self.status_var.set("")

    def _configure_selection_limits(self,limit):
        # Entries display centiseconds; the rounded last frame must remain a
        # valid display value. Actual audio bounds still use the exact duration.
        display_limit=math.ceil(limit/TIME_QUANTUM)*TIME_QUANTUM
        for widget in (self.start_spinbox,self.end_spinbox):widget.configure(to=display_limit)
    def _update_selection_label(self):
        try:
            start,end=self._selection_bounds_no_error();self.selection_label.configure(text=f"{max(0,end-start):.2f}s")
            self._sync_stem_range_notice()
        except tk.TclError:pass
    def _update_volume_label(self,stem):
        try:self.stem_volume_label_vars[stem].set(volume_label(self.stem_vars[stem]["volume"].get()))
        except tk.TclError:pass

    def _scroll_editor(self,event):
        if self._dialog is not None:return
        if event.widget==self.wave_canvas or isinstance(event.widget,(CompactFader,CompactKnob,CompactEq)):return
        if event.widget.winfo_class() in ("TSpinbox","TCombobox","TEntry","Text"):return
        if self.workspace_scroll.bar.winfo_ismapped():self.workspace_scroll.canvas.yview_scroll(-int(event.delta/120),"units")
    def _wave_zoom_at_pointer(self,event):
        if not self.duration_seconds or self.busy:return "break"
        start,end=self._wave_view_bounds();span=end-start
        if event.state&1:
            new_span=span;new_start=start+span*(-.1 if event.delta>0 else .1)
        else:
            fraction=max(0,min(1,event.x/max(1,self.wave_canvas.winfo_width())))
            new_span=max(min(.05,self.duration_seconds),min(self.duration_seconds,span*(.8 if event.delta>0 else 1.25)))
            new_start=start+span*fraction-new_span*fraction
        self.view_start=max(0,min(self.duration_seconds-new_span,new_start));self.view_end=self.view_start+new_span
        self.draw_waveform();return "break"
    def _wave_key(self,key):
        if key=="0":self.reset_wave_view()
        else:self.zoom_wave(1.25 if key=="minus" else .8)
        return "break"
    def draw_waveform(self):
        canvas=self.wave_canvas;canvas.delete("all")
        w,h=canvas.winfo_width(),canvas.winfo_height();s=self.ui_scale
        if w<3 or h<3:return
        if not self.peaks or not self.duration_seconds:
            canvas.create_text(w/2,h/2,text="Open Audio or drop a file here",fill=MUTED,font=self.fonts["body"])
            return
        start,end=self._wave_view_bounds();span=max(.001,end-start);plot=h-23*s
        selected_start,selected_end=self._selection_bounds_no_error()
        x1=max(0,min(w,(selected_start-start)/span*w));x2=max(0,min(w,(selected_end-start)/span*w))
        if x2>x1:canvas.create_rectangle(x1,0,x2,plot,fill="#203c5d",outline="")
        for channel,center in enumerate((plot*.26,plot*.74)):
            canvas.create_line(0,center,w,center,fill=LINE)
            canvas.create_text(8*s,center,text="L" if channel==0 else "R",fill=MUTED,font=self.fonts["small"])
            for x in range(round(22*s),w,max(2,self.px(2))):
                index=min(len(self.peaks)-1,int((start+span*x/w)/self.duration_seconds*len(self.peaks)))
                peak=self.peaks[index]
                value=peak[channel] if isinstance(peak,(tuple,list)) else peak
                seconds=start+span*x/w
                try:gain=self._fade_display_gain(seconds,selected_start,selected_end)
                except (ValueError,tk.TclError):gain=1
                amp=max(0,min(1,value)*gain*plot*.2)
                canvas.create_line(x,center-amp,x,center+amp,fill="#7ab2fb" if x1<=x<=x2 else "#5486c5",width=max(1,s*.75),tags="wave-sample")
        for x in (x1,x2):canvas.create_line(x,0,x,plot,fill=BLUE,width=max(1,s))
        self._draw_compact_fades(start,end,selected_start,selected_end,plot)
        count=max(2,min(8,int(w/(100*s))))
        previous_label=None
        for i in range(count+1):
            x=w*i/count;seconds=start+span*i/count
            centiseconds=round(seconds*100)
            label=f"{centiseconds//6000:02}:{centiseconds%6000/100:05.2f}" if span<10 else f"{int(seconds)//60:02}:{int(seconds)%60:02}"
            if label==previous_label:continue
            previous_label=label
            canvas.create_text(max(8*s,min(w-8*s,x)),h-10*s,text=label,
                               anchor="w" if i==0 else "e" if i==count else "center",fill=MUTED,font=self.fonts["small"],tags="timeline-tick")
        self._draw_playback_cursor()

    def _draw_compact_fades(self,start,end,selected_start,selected_end,plot):
        if selected_end<=selected_start:return
        try:
            half=(selected_end-selected_start)/2
            fades=(min(max(self.fade_in_var.get(),0),half),min(max(self.fade_out_var.get(),0),half))
        except (ValueError,tk.TclError):return
        canvas=self.wave_canvas;w=canvas.winfo_width();s=self.ui_scale;span=max(.001,end-start)
        for direction,duration in zip(("in","out"),fades):
            if duration<=0:continue
            a,b=(selected_start,selected_start+duration) if direction=="in" else (selected_end-duration,selected_end)
            if b<start or a>end:continue
            left,right=max(start,a),min(end,b)
            x0,x1=(left-start)/span*w,(right-start)/span*w
            g0,g1=(left-a)/duration,(right-a)/duration
            if direction=="out":g0,g1=1-g0,1-g1
            for center in (plot*.26,plot*.74):
                for sign in (-1,1):
                    canvas.create_line(x0,center+sign*g0*plot*.2,x1,center+sign*g1*plot*.2,
                        fill="#e7bb75",width=max(1.5,s),tags=("fade-envelope","fade-"+direction))
            # A small endpoint marker stays visible even when a 20 ms fade is
            # narrower than one pixel. Its width is a handle, not a fake duration.
            endpoint=b if direction=="in" else a
            if start<=endpoint<=end:
                x=max(5*s,min(w-5*s,(endpoint-start)/span*w))
                canvas.create_polygon(x-4*s,3*s,x+4*s,3*s,x,10*s,
                    fill="#e7bb75",outline="",tags=("fade-marker","fade-"+direction))
    def _draw_playback_cursor(self):
        canvas=self.wave_canvas;canvas.delete("playhead")
        if not self.duration_seconds:return
        start,end=self._wave_view_bounds();pos=float(self.playback_position_var.get())
        if start<=pos<=end:
            x=(pos-start)/max(.001,end-start)*canvas.winfo_width()
            canvas.create_line(x,0,x,canvas.winfo_height()-self.px(23),fill="#e2edff",width=max(1,self.ui_scale),tags="playhead")
    def _draw_fade_overlay_only(self):self.draw_waveform()

    def _show_results(self,paths):
        self.result_files=[Path(path) for path in paths]
        if self.result_files:
            self.status_var.set("Saved: "+str(self.result_files[0])+(f" (+{len(paths)-1} files)" if len(paths)>1 else ""))
            self.status_label.configure(cursor="hand2")
    def _selected_result(self):return self.result_files[0] if self.result_files else None
    def _confirm_render(self,individual=False):return True

    def _new_dialog(self,title,width,height):
        if self._dialog and self._dialog.winfo_exists():self._close_render_settings()
        window=tk.Toplevel(self,bg=PANEL);self._dialog=window
        window.title(title);window.transient(self);window.resizable(True,True)
        l,t,r,b=display_metrics(self)[0];ww=min(self.px(width),r-l-self.px(24));hh=min(self.px(height),b-t-self.px(70))
        x=max(l,min(r-ww,self.winfo_rootx()+(self.winfo_width()-ww)//2))
        y=max(t,min(b-hh-self.px(35),self.winfo_rooty()+(self.winfo_height()-hh)//2))
        window.geometry(f"{ww}x{hh}+{x}+{y}");window.minsize(min(self.px(360),ww),min(self.px(220),hh))
        window.protocol("WM_DELETE_WINDOW",self._close_render_settings)
        viewport=EditorViewport(window);viewport.pack(fill="both",expand=True)
        content=viewport.content;content.configure(bg=PANEL)
        def fit(_event=None):
            if not window.winfo_exists():return
            viewport.layout(max(content.winfo_reqheight(),viewport.canvas.winfo_height()))
        content.bind("<Configure>",fit);viewport.canvas.bind("<Configure>",fit)
        content.columnconfigure(0,weight=1)
        window.bind("<Escape>",lambda e:self._close_render_settings())
        window.bind("<MouseWheel>",lambda e:viewport.canvas.yview_scroll(-int(e.delta/120),"units"))
        window.grab_set();window.after_idle(fit)
        return window,content

    def _group(self,parent,title,row):
        box=tk.Frame(parent,bg=PANEL);box.grid(row=row,column=0,sticky="ew",padx=self.px(16),pady=self.px(8))
        box.columnconfigure(0,weight=1)
        self._label(box,title,kind="bold",color=MUTED).grid(row=0,column=0,sticky="w",pady=(0,self.px(7)))
        return box
    def _check(self,parent,text,variable,row):
        check=tk.Checkbutton(parent,text=text,variable=variable,bg=PANEL,fg=TEXT,selectcolor=INSET,
                             activebackground=PANEL,activeforeground=TEXT,font=self.fonts["body"],anchor="w",bd=0,highlightthickness=0)
        self._track_edit_widget(check)
        check.grid(row=row,column=0,sticky="w",pady=self.px(3));return check

    def open_render_settings(self):
        window,content=self._new_dialog("Settings",530,475);self.render_settings_window=window
        group=self._group(content,"Save folder",0)
        row=tk.Frame(group,bg=PANEL);row.grid(row=1,column=0,sticky="ew");row.columnconfigure(0,weight=1)
        self.settings_folder_var=tk.StringVar(value=str(self.output_dir))
        self.folder_entry=ttk.Entry(row,textvariable=self.settings_folder_var,font=self.fonts["body"])
        self.folder_entry.grid(row=0,column=0,sticky="ew")
        self._button(row,"Browse",self._browse_save_folder,width=84,icon_name="folder").grid(row=0,column=1,padx=(self.px(8),0))
        group=self._group(content,"Output",1)
        formats=tk.Frame(group,bg=PANEL);formats.grid(row=1,column=0,sticky="ew")
        for i,(name,variable,values) in enumerate((("Sample rate (Hz)",self.sample_rate_var,(48000,44100)),
                                                  ("WAV depth (bit)",self.bit_depth_var,(24,16)),
                                                  ("MP3 rate (kbps)",self.mp3_bitrate_var,(320,256,192,128)))):
            formats.columnconfigure(i,weight=1,uniform="format")
            cell=tk.Frame(formats,bg=PANEL);cell.grid(row=0,column=i,sticky="ew",padx=(0,self.px(8)))
            self._label(cell,name,kind="small",color=MUTED).pack(anchor="w",pady=(0,self.px(4)))
            choice=ttk.Combobox(cell,values=values,textvariable=variable,state="readonly",width=10,font=self.fonts["body"])
            choice.pack(fill="x")
            ordered=tuple(sorted(values))
            choice.numeric_gestures=NumericGestures(self,choice,
                lambda v=variable,items=ordered:items.index(v.get()),
                lambda value,v=variable,items=ordered:v.set(items[int(value)]),
                lambda items=ordered:(0,len(items)-1),lambda:1,1)
        self._check(group,"Peak Normalize on export",self.peak_normalize_var,2)
        self._check(group,"Delete working audio after export",self.delete_temp_var,3)
        group=self._group(content,"Playback & editing",2)
        self._check(group,"Loop playback",self.loop_var,1)
        self._check(group,"Keep adjustments when opening new audio",self.keep_adjustments_var,2)
        scope=tk.Frame(group,bg=PANEL);scope.grid(row=3,column=0,sticky="w",pady=self.px(6))
        self._label(scope,"Split Stems",kind="small",color=MUTED).pack(side="left",padx=(0,self.px(8)))
        ttk.Combobox(scope,values=("Selection","Full track"),textvariable=self.split_scope_var,
                     state="readonly",width=14,font=self.fonts["body"]).pack(side="left")
        self._label(group,"Full track takes longer once; later selections need no new split.",
                    kind="small",color=MUTED,wraplength=self.px(460)).grid(row=4,column=0,sticky="w")
        helpbox=tk.Frame(content,bg=PANEL);helpbox.grid(row=3,column=0,sticky="ew",padx=self.px(16),pady=self.px(4))
        self.help_content=tk.Frame(helpbox,bg=PANEL)
        helptext=("Space: play / pause. Ctrl+O: open audio.\nRight-drag: select. Wheel: zoom; Shift+wheel: pan.\n"
                  "Numbers: drag up/down or turn the wheel. Shift: finer steps.\n"
                  "Start/End steps follow zoom; time display stays at 0.01 s.\n"
                  "Amber lines/markers show fades on the waveform.\n"
                  "Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z: undo / redo.\nDouble-click a fader: 0 dB. Q controls resonance.\n"
                  "Selection times use the original audio timeline.\nNormalize is applied on export only.\n"
                  "Ctrl+S: save session; Ctrl+Shift+O: open session.\nCtrl+Shift+R: restore the last session.")
        self._label(self.help_content,helptext,kind="small",color=MUTED,justify="left",wraplength=self.px(450)).pack(anchor="w",pady=self.px(6))
        self._button(self.help_content,"Environment Check",self.environment_details,width=145).pack(anchor="w")
        def toggle_help():
            if self.help_content.winfo_ismapped():self.help_content.pack_forget()
            else:self.help_content.pack(fill="x")
        self._button(helpbox,"Help",toggle_help,width=58).pack(anchor="w")
        self.settings_error_var=tk.StringVar()
        self._label(content,variable=self.settings_error_var,kind="small",color="#ffc1ac",wraplength=self.px(480)).grid(row=4,column=0,sticky="ew",padx=self.px(16))
        actions=tk.Frame(content,bg=PANEL);actions.grid(row=5,column=0,sticky="ew",padx=self.px(16),pady=self.px(12))
        self._button(actions,"View Log",lambda:self.set_log_visible(True),width=85).pack(side="left")
        self._button(actions,"Done",self._save_compact_settings,width=70,primary=True).pack(side="right")
        self.folder_entry.focus_set()

    def _browse_save_folder(self):
        current=self.settings_folder_var.get()
        picked=filedialog.askdirectory(parent=self._dialog,title="Choose Save Folder",initialdir=current if Path(current).is_dir() else str(self.output_dir))
        if picked:self.settings_folder_var.set(picked)
    def _save_compact_settings(self):
        raw=self.settings_folder_var.get().strip()
        if not raw:self.settings_error_var.set("Choose a save folder.");self.folder_entry.focus_set();return
        try:
            self._edit_snapshot();folder=Path(raw).expanduser().resolve()
            if folder.exists() and not folder.is_dir():raise ValueError("Choose a folder, not a file.")
            self.output_dir=folder;self.settings["output_dir"]=str(folder)
            self._save_output_preferences();self.paths.write_settings(self.settings)
        except (ValueError,OSError,tk.TclError) as exc:self.settings_error_var.set(str(exc));return
        self._close_render_settings()
    def _save_output_preferences(self):
        for name,variable in (("loop",self.loop_var),("sample_rate",self.sample_rate_var),("bit_depth",self.bit_depth_var),
                               ("mp3_bitrate",self.mp3_bitrate_var),("peak_normalize",self.peak_normalize_var),
                               ("keep_adjustments",self.keep_adjustments_var),("delete_temp_after_render",self.delete_temp_var),
                               ("split_scope",self.split_scope_var)):
            self.settings[name]=variable.get()
    def open_advanced(self):
        _,content=self._new_dialog("Advanced Effects",420,305)
        box=self._group(content,"Q",0)
        fields=tk.Frame(box,bg=PANEL);fields.grid(row=1,column=0,sticky="ew")
        for i,(label,variable,lo,hi,step) in enumerate((("Mid Q",self.eq_mid_q_var,.3,6,.1),
                                                      ("Low filter Q",self.high_pass_q_var,.3,4,.01),
                                                      ("High filter Q",self.low_pass_q_var,.3,4,.01))):
            cell=tk.Frame(fields,bg=PANEL);cell.grid(row=i//2,column=i%2,sticky="w",padx=(0,self.px(18)),pady=self.px(5))
            self._label(cell,label,kind="small",color=MUTED).pack(anchor="w")
            self._spin(cell,variable,lo,hi,step,9,"%.2f").pack(anchor="w",pady=self.px(4))
        self._check(box,"Limiter",self.limiter_enabled_var,2)
        self.advanced_error_var=tk.StringVar()
        self._label(content,variable=self.advanced_error_var,kind="small",color="#ffc1ac",wraplength=self.px(380)).grid(row=1,column=0,sticky="ew",padx=self.px(16))
        self._button(content,"Done",self._close_render_settings,width=70,primary=True).grid(row=2,column=0,sticky="e",padx=self.px(16),pady=self.px(10))
    def _close_render_settings(self):
        if self._dialog and self._dialog.winfo_exists():
            # Dialog fields disappear from validation when destroyed; never
            # leave an invalid Q accepted in the model after dismissing Advanced.
            for widget,display,variable,fmt in self._numeric_fields:
                if not widget.winfo_exists() or widget.winfo_toplevel()!=self._dialog:continue
                try:
                    value=float(display.get())
                    if not math.isfinite(value) or not float(widget.cget("from"))<=value<=float(widget.cget("to")):
                        raise ValueError()
                except ValueError:
                    self.advanced_error_var.set(f"Enter a Q value from {widget.cget('from')} to {widget.cget('to')}.")
                    widget.focus_set();return
            self._commit_edit()
            self._dialog.grab_release();self._dialog.destroy()
        self._dialog=None;self.render_settings_window=None
        self.compact_buttons=[w for w in self.compact_buttons if w.winfo_exists()]
        self._numeric_fields=[item for item in self._numeric_fields if item[0].winfo_exists()]
        self.focus_set()
        self._sync_stem_range_notice()
    def set_log_visible(self,visible):
        if self._log_window and self._log_window.winfo_exists():
            if visible:self._log_window.lift()
            else:
                self._log_window.grab_release();self._log_window.destroy();self._log_window=None;self.log_visible=False
                if self._dialog and self._dialog.winfo_exists():self._dialog.grab_set()
            return
        if not visible:return
        window=tk.Toplevel(self,bg=PANEL);self._log_window=window;window.title("KWAK Split · Log");window.transient(self)
        l,t,r,b=display_metrics(self)[0];window.geometry(f"{min(self.px(700),r-l-40)}x{min(self.px(420),b-t-70)}")
        self.log_text=tk.Text(window,bg=INSET,fg=TEXT,font=self.fonts["small"],wrap="word",bd=0)
        self.log_text.pack(fill="both",expand=True,padx=self.px(10),pady=self.px(10))
        self.log_text.insert("end","\n".join(self.log_messages[-500:]));self.log_text.configure(state="disabled")
        self.log_visible=True;window.protocol("WM_DELETE_WINDOW",lambda:self.set_log_visible(False))
        if self._dialog:window.grab_set()
        window.bind("<Escape>",lambda event:self.set_log_visible(False))
