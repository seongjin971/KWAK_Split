"""Waveform selection, trackpad gestures and left-button seeking."""
from dataclasses import dataclass
from types import SimpleNamespace


# Windows Tk: Control is 0x04, Alt is Mod2 (0x10). Mod1 (0x08) is
# Num Lock, so it must not turn an ordinary range drag into a seek.
CONTROL_ALT_MASK = 0x04 | 0x10


@dataclass(frozen=True)
class SelectionDrag:
    mode: str
    anchor: float
    start: float
    end: float

    def bounds(self, seconds, limits):
        lower, upper = limits
        minimum = min(.01, upper - lower)
        delta = round(seconds - self.anchor, 2)
        if self.mode == "move":
            # Clamp the translation, never the two ends independently.
            delta = max(lower - self.start, min(upper - self.end, delta))
            return self.start + delta, self.end + delta
        if self.mode == "start":
            return max(lower, min(self.end - minimum, self.start + delta)), self.end
        if self.mode == "end":
            return self.start, min(upper, max(self.start + minimum, self.end + delta))
        start, end = sorted((round(self.anchor, 2), round(seconds, 2)))
        start = max(lower, min(upper - minimum, start))
        end = min(upper, max(start + minimum, end))
        return start, end


class WaveSelection:
    def __init__(self, app):
        self.app = app
        self.drag = None
        self.pointer_x = 0
        self.origin_x = 0
        self.pan_after = None
        self.keys_down = set()
        self.left_action = None
        self.left_moved = False
        self.click_anchor = None
        self.anchor_source = None

    def source_key(self):
        return self.app.source_wav, self.app.session_name

    def remember_seek(self, event):
        self.click_anchor = self.app._event_to_seconds(event)
        self.anchor_source = self.source_key()

    def left_begin(self, event):
        app = self.app
        if app.busy or not app.duration_seconds:
            return
        self.cancel()
        app.wave_canvas.focus_set()
        app._begin_edit_drag()
        app.playback_seek_dragging = False
        state = getattr(event, "state", 0)
        if state & 1 and not state & CONTROL_ALT_MASK:
            # Keep the last explicit seek point even while the audio cursor moves.
            anchor = (self.click_anchor if self.anchor_source == self.source_key()
                      and self.click_anchor is not None else float(app.playback_position_var.get()))
            self.click_anchor, self.anchor_source = anchor, self.source_key()
            start, end = SelectionDrag("new", anchor, 0, 0).bounds(app._event_to_seconds(event), self.limits())
            app.playback_cursor_manual = True
            app.selection_start_var.set(start)
            app.selection_end_var.set(end)
            app._selection_changed()
            self.left_action = "select"
        elif self.hit(event) != "new" and not state & CONTROL_ALT_MASK:
            self.begin(event)
            self.left_action = "handle"
            self.left_moved = False
        else:
            app._wave_seek_begin(event)
            self.remember_seek(event)
            self.left_action = "seek"

    def left_update(self, event):
        app = self.app
        if app.busy or app.closing:
            return
        if self.left_action == "handle":
            if self.left_moved or abs(event.x - self.origin_x) >= max(3, app.px(3)):
                self.left_moved = True
                self.update(event)
        elif self.left_action == "seek":
            app._wave_seek_to_event(event)
            self.remember_seek(event)

    def left_finish(self, event):
        app = self.app
        action = self.left_action
        if app.busy or app.closing or not app.duration_seconds:
            self.cancel()
            app.playback_seek_dragging = False
            return
        if action == "handle":
            self.left_update(event)
            if self.left_moved:
                app._wave_mouse_up(event)
            else:
                # Handles only edit the range. A click or tiny hand movement
                # must not reposition the audio cursor.
                self.cancel()
                self.hover(event)
        elif action == "seek":
            app._wave_seek_end(event)
        elif action == "select":
            app._end_edit_drag()
            app._commit_edit()
        self.left_action = None

    def limits(self):
        return self.app._stem_selection_limits() or (0.0, self.app.duration_seconds)

    def geometry(self):
        app = self.app
        view_start, view_end = app._wave_view_bounds()
        width = app.wave_canvas.winfo_width()
        start, end = app._selection_bounds_no_error()
        x1 = (start - view_start) / (view_end - view_start) * width
        x2 = (end - view_start) / (view_end - view_start) * width
        return width, x1, x2

    def grip(self):
        width, x1, x2 = self.geometry()
        if x2 <= 0 or x1 >= width or x2 <= x1:
            return None
        scale = self.app.ui_scale
        half = min(18 * scale, max(8 * scale, (x2 - x1) / 4))
        center = (max(0, x1) + min(width, x2)) / 2
        center = max(half + 2, min(width - half - 2, center))
        return center - half, 2 * scale, center + half, 15 * scale

    def hit(self, event):
        app = self.app
        if app.busy or not app.duration_seconds:
            return "new"
        x, y = event.x, getattr(event, "y", app.wave_canvas.winfo_height() / 2)
        grip = self.grip()
        if grip and grip[0] <= x <= grip[2] and grip[1] <= y <= grip[3]:
            return "move"
        width, x1, x2 = self.geometry()
        # Older sessions may contain a single selected point. It must create a
        # range in either direction, rather than choose one of two tied edges.
        if x2 <= x1:
            return "new"
        radius = max(12, 18 * app.ui_scale)
        if 0 <= y <= app.wave_canvas.winfo_height() - 23 * app.ui_scale:
            candidates = [(abs(x - edge), name) for name, edge in (("start", x1), ("end", x2))
                          if 0 <= edge <= width and abs(x - edge) <= radius]
            if candidates:
                return min(candidates)[1]
        return "new"

    def hover(self, event):
        if self.left_action in ("seek", "select"):
            mode = "new"
        elif self.drag is not None:
            mode = self.drag.mode
        else:
            mode = self.hit(event)
        cursor = {"start": "sb_h_double_arrow", "end": "sb_h_double_arrow",
                  "move": "hand2", "new": "arrow"}[mode]
        self.app.wave_canvas.configure(cursor=cursor)

    def leave(self, _event=None):
        if self.drag is None:
            self.app.wave_canvas.configure(cursor="")

    def begin(self, event):
        app = self.app
        if app.busy or not app.duration_seconds:
            return
        self.cancel()
        app.wave_canvas.focus_set()
        app._begin_edit_drag()
        start, end = app._selection_bounds_no_error()
        seconds = app._event_to_seconds(event)
        self.drag = SelectionDrag(self.hit(event), seconds, start, end)
        self.origin_x = self.pointer_x = event.x
        app.drag_start_seconds = seconds
        self.hover(event)

    def update(self, event):
        app = self.app
        if self.drag is None or app.busy or app.closing:
            return
        self.pointer_x = event.x
        # A right click must not erase a carefully prepared range.
        if self.drag.mode != "new" or abs(event.x - self.origin_x) >= max(3, app.px(3)):
            self.apply(*self.drag.bounds(app._event_to_seconds(event), self.limits()))
        width = app.wave_canvas.winfo_width()
        if (event.x < 0 or event.x > width) and self.pan_after is None:
            self.pan_after = app.after(40, self.pan)

    def pan(self):
        self.pan_after = None
        app = self.app
        if self.drag is None or app.busy or app.closing:
            return
        width = max(1, app.wave_canvas.winfo_width())
        if 0 <= self.pointer_x <= width:
            return
        start, end = app._wave_view_bounds()
        span = end - start
        direction = -1 if self.pointer_x < 0 else 1
        overflow = -self.pointer_x if direction < 0 else self.pointer_x - width
        step = span * min(.15, max(.02, overflow / width)) * direction
        target = max(0, min(app.duration_seconds - span, start + step))
        if abs(target - start) < 1e-9:
            return
        app.view_start, app.view_end = target, target + span
        self.update(SimpleNamespace(x=self.pointer_x))
        app.draw_waveform()

    def apply(self, start, end):
        app = self.app
        if (start, end) == app._selection_bounds_no_error():
            return
        # Range edits do not seek. Preserve a paused cursor while preparing the
        # new bounds, just as Shift+click and bracket marking already do.
        app.playback_cursor_manual = True
        app.selection_start_var.set(start)
        app.selection_end_var.set(end)
        app._selection_changed()

    def finish(self, event):
        original = self.drag
        if original is not None and event.x != self.pointer_x:
            self.update(event)
        self.cancel()
        self.hover(event)
        return original is not None and (original.start, original.end) != self.app._selection_bounds_no_error()

    def cancel(self):
        if self.pan_after is not None:
            self.app.after_cancel(self.pan_after)
            self.pan_after = None
        self.drag = None
        self.left_action = None
        self.left_moved = False
        self.app.drag_start_seconds = None

    def mark(self, endpoint):
        app = self.app
        if app.busy or not app.duration_seconds or self.drag is not None or endpoint in self.keys_down:
            return "break"
        self.keys_down.add(endpoint)
        # Read the audio clock now, rather than the last 50 ms UI tick.
        if app.preview_playing:
            app._update_playback_position()
        position = float(app.playback_position_var.get())
        lower, upper = self.limits()
        minimum = min(.01, upper - lower)
        position = max(lower, min(upper, round(position, 2)))
        app._begin_edit_drag()
        start, end = app._selection_bounds_no_error()
        if endpoint == "start":
            start = min(position, upper - minimum)
            end = max(end, start + minimum)
        else:
            end = max(position, lower + minimum)
            start = min(start, end - minimum)
        # Marking never seeks/restarts the running stream or moves a paused cursor.
        app.playback_cursor_manual = True
        app.selection_start_var.set(start)
        app.selection_end_var.set(end)
        app._selection_changed()
        app._end_edit_drag()
        app._commit_edit()
        return "break"

    def release_key(self, endpoint):
        self.keys_down.discard(endpoint)

    def draw(self, plot, color):
        app = self.app
        canvas = app.wave_canvas
        width, x1, x2 = self.geometry()
        scale = app.ui_scale
        for name, x in (("start", x1), ("end", x2)):
            if 0 <= x <= width:
                canvas.create_line(x, 0, x, plot, fill=color, width=max(1, 2 * scale),
                                   tags=("selection-boundary", "selection-" + name))
                # Keep the full handle visible at the beginning/end of a file.
                center = max(1 + 8 * scale, min(width - 1 - 8 * scale, x))
                top, bottom = max(2 * scale, plot / 2 - 18 * scale), min(plot - 2 * scale, plot / 2 + 18 * scale)
                canvas.create_rectangle(center - 8 * scale, top, center + 8 * scale, bottom,
                                        fill="#315c88", outline=color, width=max(1, scale),
                                        tags=("selection-handle", "selection-" + name))
                for offset in (-2, 2):
                    canvas.create_line(center + offset * scale, top + 7 * scale,
                                       center + offset * scale, bottom - 7 * scale,
                                       fill="#d1e7ff", width=max(1, scale), tags="selection-handle-grip")
        grip = self.grip()
        if grip:
            canvas.create_rectangle(*grip, fill="#315c88", outline=color, width=max(1, scale),
                                    tags="selection-move")
            center = (grip[0] + grip[2]) / 2
            for offset in (-4, 0, 4):
                x = center + offset * scale
                canvas.create_line(x, 6 * scale, x, 11 * scale, fill="#b5d7ff",
                                   width=max(1, scale), tags="selection-move-grip")
