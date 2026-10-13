"""Vertical scrubbing and wheel editing without losing normal text entry."""
import math
import tkinter as tk


class NumericGestures:
    def __init__(self, app, widget, getter, setter, limits, step, quantum, commit=None, enabled=None, default=None):
        self.app, self.widget = app, widget
        self.getter, self.setter = getter, setter
        self.limits, self.step, self.quantum = limits, step, quantum
        self.commit, self.enabled = commit, enabled
        self.default = default
        self.origin = None
        self.resetting = False
        app._track_edit_widget(widget)
        widget.bind("<ButtonPress-1>", self.press, add="+")
        widget.bind("<B1-Motion>", self.drag, add="+")
        widget.bind("<ButtonRelease-1>", self.release, add="+")
        widget.bind("<MouseWheel>", self.wheel)
        if default is not None:
            widget.bind("<Control-ButtonPress-1>", self.reset)

    def available(self):
        return (not self.app.busy and (self.enabled is None or self.enabled())
                and (not hasattr(self.widget, "instate") or not self.widget.instate(("disabled",))))

    def increment(self, event):
        return max(self.quantum, self.step() * (.1 if event.state & 1 else 1))

    def apply(self, value):
        lo, hi = self.limits()
        value = round(round(value / self.quantum) * self.quantum, 6)
        self.setter(max(lo, min(hi, value)))

    def press(self, event):
        self.origin = None
        self.resetting = False
        if not self.available():return
        if hasattr(self.widget, "identify") and "arrow" in self.widget.identify(event.x, event.y):
            return  # Keep native spin arrows and combo dropdowns.
        try:value = float(self.getter())
        except (ValueError, tk.TclError):return
        if math.isfinite(value):
            self.origin = (event.x_root, event.y_root, value, self.increment(event), False)
            if hasattr(self.widget,"instate") and self.widget.instate(("readonly",)):
                self.widget.focus_set()
                return "break"

    def reset(self, _event):
        self.origin = None
        self.resetting = True
        if self.available():
            self.apply(self.default)
            self.widget.focus_set()
        return "break"

    def drag(self, event):
        # Keep consuming this gesture even if Ctrl is released before the mouse.
        if self.resetting:return "break"
        if self.origin is None or not self.available():return
        x, y, value, step, moved = self.origin
        dy = (y - event.y_root) / self.app.ui_scale
        dx = abs(x - event.x_root) / self.app.ui_scale
        if not moved and (abs(dy) < 3 or abs(dy) < dx):return
        self.origin = (x, y, value, step, True)
        self.apply(value + round(dy / 3) * step)
        if hasattr(self.widget, "selection_clear"):self.widget.selection_clear()
        return "break"

    def release(self, _event):
        moved = self.resetting or (self.origin is not None and self.origin[-1])
        self.origin = None
        self.resetting = False
        self.app._end_edit_drag()
        if moved:
            if self.available():
                if self.commit:self.commit()
                self.app._commit_edit()
                self.widget.winfo_toplevel().focus_set()
            return "break"

    def wheel(self, event):
        if not self.available() or not event.delta:return "break"
        try:value = float(self.getter())
        except (ValueError, tk.TclError):return "break"
        if not math.isfinite(value):return "break"
        notches = event.delta / 120 if abs(event.delta) >= 120 else (1 if event.delta > 0 else -1)
        self.app._begin_edit_drag()
        self.apply(value + notches * self.increment(event))
        self.app._end_edit_drag()
        if self.commit:self.commit()
        return "break"
