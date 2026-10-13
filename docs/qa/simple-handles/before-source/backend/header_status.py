"""One-line task feedback that never changes the header's requested size."""
from __future__ import annotations

import tkinter as tk

from backend.compact_widgets import BG, MUTED


class HeaderStatus(tk.Frame):
    def __init__(self, parent, app, activate):
        super().__init__(parent, bg=BG, width=1, height=app.px(30))
        self.app = app
        self.prefix = self.suffix = ""
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.label = app._label(self, kind="body", color=MUTED, width=1,
                                wraplength=0, takefocus=0, cursor="hand2")
        self.label.grid(row=0, column=0, sticky="ew")
        self.label.bind("<Configure>", self.fit)
        self.label.bind("<Button-1>", activate)
        self.label.bind("<Return>", activate)
        self.cancel = app._button(self, "Cancel", app.cancel_current_operation, width=60)
        self.cancel.grid(row=0, column=1, padx=(app.px(8), 0))

    def display(self, prefix, *, suffix="", busy=False, color=MUTED):
        self.prefix, self.suffix = prefix, suffix
        self.label.configure(fg=color, takefocus=bool(prefix))
        if prefix:
            self.label.grid()
        else:
            self.label.grid_remove()
        if busy:
            self.cancel.grid(padx=(self.app.px(8), 0))
        else:
            self.cancel.grid_remove()
        self.fit()

    def fit(self, _event=None):
        face = self.app.fonts["body"]
        width = max(0, self.label.winfo_width() - 2 * int(self.label.cget("padx")))
        text = " ".join(self.prefix.split())
        if face.measure(text + self.suffix) > width:
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if face.measure(text[:mid] + "…" + self.suffix) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            text = text[:lo].rstrip(" .…") + "…"
        self.label.configure(text=text + self.suffix if self.prefix else "")
