"""Small Tk widgets shared by the desktop workspace."""
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, minimum_width=720):
        super().__init__(parent)
        self.minimum_width = minimum_width
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#090d14")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._layout)
        self.canvas.bind("<Configure>", self._layout)
        # Do not steal the mouse wheel from knobs, sliders, or numeric entries.
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.content.bind("<MouseWheel>", self._wheel)

    def _layout(self, _event=None):
        width = max(self.canvas.winfo_width(), self.minimum_width, self.content.winfo_reqwidth())
        self.canvas.itemconfigure(self.window_id, width=width)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"


class ToolTip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.window = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _schedule(self, _event=None):
        self.hide()
        self.after_id = self.widget.after(550, self.show)

    def show(self):
        self.after_id = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        ttk.Label(self.window, text=self.text, padding=8, wraplength=340).pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - self.window.winfo_reqwidth())
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 4,
                self.widget.winfo_screenheight() - self.window.winfo_reqheight())
        self.window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def hide(self, _event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window:
            self.window.destroy()
            self.window = None
