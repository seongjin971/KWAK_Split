"""Single-file audio editing and user-facing workspace features."""
from __future__ import annotations

import math
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from backend.edit_state import EDIT_DEFAULTS, EditHistory, validate_edits
from backend.ui_helpers import ScrollableFrame
from backend.audio_processing.ffmpeg_tools import AudioProcessingError, find_executable
from backend.audio_processing.separation import StemSeparator


class StemRangeError(AudioProcessingError):
    """An editable selection extends beyond the available separated audio."""


class WorkspaceFeatures:
    def _init_workspace(self):
        self.loop_var = tk.BooleanVar(value=bool(self.settings.get("loop", True)))
        self.sample_rate_var = tk.IntVar(value=self.settings.get("sample_rate", 48000))
        self.bit_depth_var = tk.IntVar(value=self.settings.get("bit_depth", 24))
        self.mp3_bitrate_var = tk.IntVar(value=self.settings.get("mp3_bitrate", 320))
        self.peak_normalize_var.set(bool(self.settings.get("peak_normalize", False)))
        scope=self.settings.get("split_scope","Selection")
        self.split_scope_var = tk.StringVar(value=scope if scope in ("Selection","Full track") else "Selection")
        stem_format = self.settings.get("stem_export_format", "WAV")
        self.stem_export_format_var = tk.StringVar(value=stem_format if stem_format in ("WAV", "MP3") else "WAV")
        self.mix_summary_var = tk.StringVar(value="Open audio to see the monitor source and export settings.")
        self.view_start = 0.0
        self.view_end = 0.0
        self.stem_range = (0.0, 0.0)
        self._history_suspended = True
        self._history_dragging = False
        self._history_after = None
        self._loop_after = None
        self._selection_ui_after = None
        self.result_files = []
        self._pending_audio = None
        self._owned_sessions = set()
        self._worker_thread = None
        self._close_cleanup_thread = None

    def _finish_workspace(self):
        self.workspace_scroll.canvas.bind("<Configure>", self._layout_eq_details, add="+")
        self._history_suspended = False
        self.history = EditHistory(self._edit_snapshot())
        for variable in self._edit_variables():
            variable.trace_add("write", self._queue_edit)
        for variable in (self.selection_start_var, self.selection_end_var):
            variable.trace_add("write", self._queue_selection_display)
        self.bind_all("<ButtonPress-1>", self._begin_edit_drag, add="+")
        self.bind_all("<ButtonPress-3>", self._begin_edit_drag, add="+")
        self.bind_all("<ButtonRelease-1>", self._end_edit_drag, add="+")
        self.bind_all("<ButtonRelease-3>", self._end_edit_drag, add="+")
        for chord, action in (("<Control-z>", self.undo_edit), ("<Control-y>", self.redo_edit),
                              ("<Control-o>", self.open_audio)):
            self.bind(chord, lambda _event, action=action: (action(), "break")[1])
        self._update_workspace_summary()
        self.after(0, self._check_environment_status)

    def _build_workspace_toolbar(self, actions, toolbar):
        for column, (label, command) in enumerate((("Undo", self.undo_edit), ("Redo", self.redo_edit)), start=2):
            ttk.Button(actions, text=label, command=command).grid(row=0, column=column, padx=3)
        ttk.Label(toolbar, textvariable=self.mix_summary_var, wraplength=680, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=4)

    def _build_range_tools(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(frame, text="Loop Selection", variable=self.loop_var).grid(row=0, column=0, padx=4)
        ttk.Label(frame, text="Split").grid(row=0, column=1, padx=6)
        ttk.Combobox(frame, values=("Full Track", "Selection"), textvariable=self.split_scope_var,
                     state="readonly", width=10).grid(row=0, column=2)
        for column, (label, command) in enumerate((("Zoom +", lambda: self.zoom_wave(0.5)),
                ("Zoom −", lambda: self.zoom_wave(2.0)), ("Fit All", self.reset_wave_view),
                ("Fit Selection", self.zoom_selection)), start=3):
            ttk.Button(frame, text=label, command=command).grid(row=0, column=column, padx=2)
        self.wave_toggle_button = ttk.Button(frame, text="Hide Waveform", command=self.toggle_waveform)
        self.wave_toggle_button.grid(row=0, column=7, padx=2)
        self.wave_scroll = ttk.Scrollbar(parent, orient="horizontal", command=self.pan_wave)
        self.wave_scroll.grid(row=3, column=0, sticky="ew", pady=(5, 0))

    def _build_result_area(self, parent):
        frame = ttk.LabelFrame(parent, text="Exported Files", padding=8)
        frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(4, 12))
        frame.columnconfigure(0, weight=1)
        self.result_list = tk.Listbox(frame, height=4, background="#101722", foreground="#d7dee8",
                                     selectbackground="#285178", exportselection=False)
        self.result_list.grid(row=0, column=0, sticky="ew")
        scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=self.result_list.xview)
        scrollbar.grid(row=1, column=0, sticky="ew")
        self.result_list.configure(xscrollcommand=scrollbar.set)
        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Button(actions, text="Play File", command=self.play_result_file).pack(side="left", padx=3)
        ttk.Button(actions, text="Open Folder", command=self.open_result_folder).pack(side="left", padx=3)
        ttk.Button(actions, text="Copy Path", command=self.copy_result_path).pack(side="left", padx=3)

    def _build_extra_render_settings(self, frame):
        for row, (label, variable, choices) in enumerate((
            ("WAV sample rate (Hz)", self.sample_rate_var, (44100, 48000)),
            ("WAV bit depth", self.bit_depth_var, (16, 24)),
            ("MP3 bitrate (kbps)", self.mp3_bitrate_var, (128, 192, 256, 320))), start=4):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Combobox(frame, textvariable=variable, values=choices, state="readonly", width=12).grid(row=row, column=1, sticky="w")
        presets = ttk.Frame(frame)
        presets.grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Button(presets, text="Standard WAV · 44.1k / 16bit", command=lambda: self._set_output_profile(44100, 16)).pack(side="left", padx=4)
        ttk.Button(presets, text="DAW WAV · 48k / 24bit", command=lambda: self._set_output_profile(48000, 24)).pack(side="left", padx=4)
        ttk.Button(frame, text="Environment Check / Setup", command=self.environment_details).grid(row=9, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(frame, text="Normalize is skipped during live monitoring and applied on export.",
                  wraplength=540, style="Muted.TLabel").grid(row=10, column=0, columnspan=3, sticky="w")

    def _set_output_profile(self, rate, depth):
        self.sample_rate_var.set(rate)
        self.bit_depth_var.set(depth)

    def _edit_variables(self):
        result = [getattr(self, name + "_var") for name in EDIT_DEFAULTS]
        for values in self.stem_vars.values():
            result.extend(values.values())
        return result

    def _edit_snapshot(self):
        values = {name: getattr(self, name + "_var").get() for name in EDIT_DEFAULTS}
        values["stems"] = {stem: {name: var.get() for name, var in variables.items()}
                           for stem, variables in self.stem_vars.items()}
        return validate_edits(values)

    def _apply_edits(self, snapshot):
        snapshot = validate_edits(snapshot)
        self._history_suspended = True
        try:
            for name in EDIT_DEFAULTS:
                getattr(self, name + "_var").set(snapshot[name])
            for stem, values in snapshot["stems"].items():
                for name, value in values.items():
                    self.stem_vars[stem][name].set(value)
            self._selection_changed()
        finally:
            self._history_suspended = False
        self._update_workspace_summary()
        self._update_stem_bypass_button()

    def _reset_edits(self):
        state = validate_edits({})
        # Output/playback preferences survive opening another audio file.
        for name in ("loop", "sample_rate", "bit_depth", "mp3_bitrate", "peak_normalize"):
            state[name] = getattr(self, name + "_var").get()
        state["selection_end"] = self.duration_seconds
        self._apply_edits(state)

    def _begin_edit_drag(self, _event=None):
        if not self._history_dragging:
            self._commit_edit()
        self._history_dragging = True

    def _end_edit_drag(self, _event=None):
        self._history_dragging = False
        self._queue_edit()

    def _queue_edit(self, *_args):
        if self._history_suspended or self.closing:
            return
        self._update_workspace_summary()
        if self._history_after:
            self.after_cancel(self._history_after)
            self._history_after = None
        if not self._history_dragging:
            self._history_after = self.after(300, self._commit_edit)

    def _queue_selection_display(self, *_args):
        if self.closing or self._selection_ui_after:
            return
        self._selection_ui_after = self.after_idle(self._refresh_selection_display)

    def _refresh_selection_display(self):
        self._selection_ui_after = None
        self._selection_changed()

    def _commit_edit(self):
        # Commit the displayed range, including any pending idle clamp, so a
        # rapid gesture/Undo cannot record an unavailable stem selection.
        self._selection_changed()
        if self._history_after:
            self.after_cancel(self._history_after)
            self._history_after = None
        if self._history_suspended or not hasattr(self, "history"):
            return
        try:
            snapshot = self._edit_snapshot()
        except (tk.TclError, ValueError):
            return
        self.history.push(snapshot)

    def undo_edit(self):
        if self.busy:
            return
        self.stop_preview(show_status=False)
        self._commit_edit()
        self._apply_edits(self.history.undo())
        # Normalize older, wider ranges without pushing and discarding Redo.
        self.history.states[self.history.index] = self._edit_snapshot()

    def redo_edit(self):
        if self.busy:
            return
        self.stop_preview(show_status=False)
        self._commit_edit()
        self._apply_edits(self.history.redo())
        self.history.states[self.history.index] = self._edit_snapshot()

    def _source_workspace_ready(self):
        for name in ("_history_after", "_selection_ui_after"):
            pending = getattr(self, name, None)
            if pending:
                self.after_cancel(pending)
                setattr(self, name, None)
        self._history_dragging = False
        self.view_start, self.view_end = 0.0, self.duration_seconds
        self.stem_range = (0.0, self.duration_seconds)
        self._reset_edits()
        self.history = EditHistory(self._edit_snapshot())
        self.result_files = []
        if hasattr(self, "result_list"):
            self.result_list.delete(0, "end")
        self._update_workspace_summary()
        self.draw_waveform()



    def _update_workspace_summary(self):
        if not self.source_wav:
            self.mix_summary_var.set("Open audio → Select range → Split stems → Adjust → Export")
            return
        try:
            start, end = self._selection_bounds_no_error()
            solo = [name for name, values in self.stem_vars.items() if values["solo"].get()]
            chosen = [name for name, values in self.stem_vars.items() if not values["mute"].get() and (not solo or name in solo)]
            mix = ", ".join(chosen) if self.stem_paths else "Original audio"
            monitor = "Original comparison (export uses the mix below)" if self.stem_bypass_var.get() else mix
            normalized = "On · skipped during live monitoring" if self.peak_normalize_var.get() else "Off"
            self.mix_summary_var.set(f"Monitor: {monitor}\nExport: {mix or 'No stems selected'} · {start:.2f}~{end:.2f}s · "
                f"Speed {self.tempo_percent_var.get():g}% · Pitch {self.pitch_semitones_var.get():+g}st\n"
                f"WAV {self.sample_rate_var.get()/1000:g}kHz/{self.bit_depth_var.get()}bit · "
                f"MP3 {self.mp3_bitrate_var.get()}kbps · Normalize {normalized}")
        except (tk.TclError, ValueError):
            self.mix_summary_var.set("Check the numeric inputs. Settings will be checked again before export.")

    def _confirm_render(self, individual=False):
        self._update_workspace_summary()
        summary = self.mix_summary_var.get()
        if individual:
            summary = "\n".join(line for line in summary.splitlines() if not line.startswith("Export:"))
            start, end = self._selection_bounds()
            summary += f"\nIndividual export: {', '.join(self.stem_paths)} · {start:.2f}~{end:.2f}s"
        effects = self._build_audio_effects()
        summary += (f"\nEQ Low/Mid/High: {effects.low_db:+g}/{effects.mid_db:+g}/{effects.high_db:+g} dB"
                    f" · HP {effects.high_pass_hz:g} / LP {effects.low_pass_hz:g} Hz"
                    f"\nFades: {self.fade_in_var.get():g}s / {self.fade_out_var.get():g}s · "
                    f"Limiter {'On' if effects.limiter_enabled else 'Off'}")
        rule = ("\n\nIndividual stems: exports every stem separately. Ignores Mute/Solo; applies each volume and the current EQ, pitch, speed, fades, and Normalize."
                if individual else "\n\nExports the current mix with EQ, pitch, speed, and fades. Original comparison monitoring does not affect export.")
        return messagebox.askokcancel("Confirm Export", summary + rule)

    def _stem_selection_limits(self):
        """Return usable coverage only when all four stems are available."""
        if not self._ready_stem_paths():
            return None
        try:
            start, end = (float(value) for value in self.stem_range)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (start, end)):
            return None
        start, end = max(0.0, start), min(self.duration_seconds, end)
        return (start, end) if end > start else None

    def _clamp_stem_selection(self, start, end):
        limits = self._stem_selection_limits()
        if limits is None:
            return start, end
        lower, upper = limits
        start, end = sorted((max(lower, min(upper, start)), max(lower, min(upper, end))))
        # Preserve a playable centisecond even when the whole gesture is
        # outside coverage. Extremely short stems use their exact full range.
        minimum = min(0.01, upper - lower)
        if end - start < minimum - 1e-9:
            start = max(lower, min(start, upper - minimum))
            end = min(upper, start + minimum)
        return start, end

    def _validate_stem_range(self, start, end):
        if self.stem_paths and (start < self.stem_range[0] - 0.001 or end > self.stem_range[1] + 0.001):
            raise StemRangeError(
                f"Stems cover {self.stem_range[0]:.2f}–{self.stem_range[1]:.2f}s. "
                + ("Click Split Stems to separate the full track." if self.split_scope_var.get()=="Full track"
                 else "Click Split Stems to separate the required range."))

    def _show_results(self, paths):
        self.result_files = [Path(path) for path in paths]
        self.result_list.delete(0, "end")
        for path in self.result_files:
            self.result_list.insert("end", str(path))
        if self.result_files:
            self.result_list.selection_set(0)
        self.workspace_scroll.canvas.update_idletasks()
        self.workspace_scroll.canvas.yview_moveto(1.0)

    def _selected_result(self):
        selected = self.result_list.curselection()
        return self.result_files[selected[0]] if selected else None

    def play_result_file(self):
        path = self._selected_result()
        if path and path.exists():
            self.stop_preview(show_status=False)
            try:
                os.startfile(path)
            except OSError as exc:
                messagebox.showerror("Play File", str(exc))

    def open_result_folder(self):
        path = self._selected_result()
        try:
            os.startfile(path.parent if path else self.output_dir)
        except OSError as exc:
            messagebox.showerror("Open Folder", str(exc))

    def copy_result_path(self):
        path = self._selected_result()
        if path:
            self.clipboard_clear()
            self.clipboard_append(str(path))

    def _wave_view_bounds(self):
        end = min(self.view_end or self.duration_seconds, self.duration_seconds)
        start = max(0.0, min(self.view_start, end))
        return start, max(end, start + 0.001)

    def toggle_waveform(self):
        if self.wave_canvas.winfo_manager():
            self.wave_canvas.grid_remove()
            self.wave_toggle_button.configure(text="Show Waveform")
        else:
            self.wave_canvas.grid()
            self.wave_toggle_button.configure(text="Hide Waveform")

    def zoom_wave(self, factor):
        if self.duration_seconds <= 0:
            return
        start, end = self._wave_view_bounds()
        span = min(self.duration_seconds, max(0.1, (end - start) * factor))
        center = (start + end) / 2
        self.view_start = max(0.0, min(center - span / 2, self.duration_seconds - span))
        self.view_end = self.view_start + span
        self.draw_waveform()

    def reset_wave_view(self):
        self.view_start, self.view_end = 0.0, self.duration_seconds
        self.draw_waveform()

    def zoom_selection(self):
        start, end = self._selection_bounds_no_error()
        if end > start:
            self.view_start, self.view_end = start, end
            self.draw_waveform()

    def pan_wave(self, action, value, units=None):
        start, end = self._wave_view_bounds()
        span = end - start
        target = float(value) * self.duration_seconds if action == "moveto" else start + float(value) * span * (0.8 if units == "pages" else 0.1)
        self.view_start = max(0.0, min(target, max(self.duration_seconds - span, 0.0)))
        self.view_end = self.view_start + span
        self.draw_waveform()

    def _loop_preview(self):
        self._loop_after = None
        if self.closing or self.busy or not self.loop_var.get() or not self.source_wav:
            return
        self.playback_cursor_manual = False
        try:
            self._start_context_preview()
        except (AudioProcessingError, ValueError, tk.TclError) as exc:
            self.status_var.set(f"Check loop playback settings: {exc}")

    def _check_environment_status(self):
        missing = []
        if not find_executable(self.paths, "ffmpeg"):
            missing.append("FFmpeg missing: Settings → Environment Check")
        if not StemSeparator(self.paths).available_command():
            missing.append("Stem engine missing: Settings → Environment Check")
        elif not self.paths.models_have_payload():
            missing.append("Model download required for the first split")
        self.status_var.set(" / ".join(missing) if missing else "Ready · Open audio to get started.")

    def environment_details(self):
        lines = [f"FFmpeg: {find_executable(self.paths, 'ffmpeg') or 'Missing'}",
                 f"FFplay: {find_executable(self.paths, 'ffplay') or 'Missing — preview uses a temporary WAV'}",
                 f"Demucs: {'Ready' if StemSeparator(self.paths).available_command() else 'Missing'}",
                 f"Model: {'Local files found' if self.paths.models_have_payload() else 'Download required for the first split'}",
                 "", "FFmpeg setup: scripts/download_ffmpeg.ps1", "Stem engine setup: scripts/prepare_demucs_runtime.ps1",
                 "Keep the package folders: bin / backend / models."]
        messagebox.showinfo("Environment Check", "\n".join(lines))

    def open_readme(self):
        try:
            os.startfile(str(self.paths.root / "README.txt"))
        except OSError as exc:
            self.status_var.set(f"Could not open README: {exc}")

    def _workspace_close(self):
        self._save_output_preferences()
        for name in ("_history_after", "_loop_after", "_selection_ui_after"):
            value = getattr(self, name, None)
            if value:
                self.after_cancel(value)
                setattr(self, name, None)
