"""Tk integration for silent preparation and retained Space pause/resume."""
import time
import tkinter as tk

from backend.audio_processing.ffmpeg_tools import AudioProcessingError, ToolMissingError
from backend.audio_processing.warm_transport import PlaybackRequest, WarmTransport


class PreparedPreview:
    def _init_prepared_preview(self, factory):
        self._pending_playback = None
        self._warm_transport = WarmTransport(factory)
        self._prepared_after = None
        self.bind("<Destroy>", self._prepared_destroyed, add="+")

    def _prepared_destroyed(self, event):
        if event.widget is self:self._warm_transport.close(wait=False)

    def _prepared_request(self, stems=None):
        if stems is None:stems, _label, _mode = self._context_preview_request()
        start, end = self._playback_bounds()
        if end <= start:raise AudioProcessingError("Select a range longer than 0 seconds.")
        return PlaybackRequest(tuple(stems), start, end-start,
                               float(self.fade_in_var.get()), float(self.fade_out_var.get()),
                               self._build_audio_effects(), self._selection_bounds())

    def _begin_prepared_preview(self, request, label):
        self._cancel_live_preview_restart()
        if self.current_preview_file:self.stop_preview(show_status=False)
        if self.realtime_processes:self._stop_realtime_playback()
        self._pending_playback = (request, label)
        self.preview_playing = True
        self.playback_started_at = None  # The cursor waits for the actual device.
        self.playback_start_seconds = request.start_seconds
        self.playback_duration_seconds = request.duration_seconds
        self.playback_tempo_ratio = request.effects.tempo_ratio
        self.playback_output_duration_seconds = request.duration_seconds / request.effects.tempo_ratio
        self._set_playback_position(request.start_seconds)
        self._warm_transport.prepare(request)
        try:self._activate_prepared_preview()
        except (ValueError, tk.TclError, AudioProcessingError, OSError) as exc:
            self._prepared_failed(exc)
        self._refresh_action_states(transport_only=True)
        # A cold request is completed asynchronously, without blocking keys.
        if self._pending_playback:
            if self._prepared_after:self.after_cancel(self._prepared_after)
            self._prepared_after = self.after(10, self._prepared_tick)

    def _activate_prepared_preview(self):
        if not self._pending_playback:return
        request, label = self._pending_playback
        owner = self._warm_transport.take(request)
        if owner is None:return
        try:
            if not owner.resume():raise OSError("The prepared audio output is unavailable.")
        except Exception:
            owner.close()
            raise
        self.realtime_processes = owner
        self._pending_playback = None
        self.current_preview_file = None
        self.playback_started_at = time.monotonic()
        self.status_var.set(f"Realtime preview: {label}")

    def _prepared_tick(self):
        self._prepared_after = None
        if self.closing:return
        try:
            if self._pending_playback:
                request, label = self._pending_playback
                if self._warm_transport.unavailable:
                    # Device-open failure retains the established FFplay path.
                    self._pending_playback = None
                    self.preview_playing = False
                    self.append_log(f"Prepared output unavailable; using FFplay: {self._warm_transport.unavailable}")
                    self._start_preview(list(request.stems), label)
                else:
                    # Include any EQ/mixer/range changes made during cold start.
                    stems, _ = self._build_last_preview_request()
                    request = self._prepared_request(stems)
                    self._pending_playback = (request, label)
                    self._warm_transport.prepare(request)
                    self._activate_prepared_preview()
            elif not self.preview_playing and not self.busy and self.source_wav is not None:
                self._warm_transport.prepare(self._prepared_request())
            elif self.busy or self.source_wav is None:
                self._warm_transport.cancel()
        except (ValueError, tk.TclError, AudioProcessingError, OSError) as exc:
            # Idle incomplete text never launches playback or replaces its status.
            if self._pending_playback:self._prepared_failed(exc)
        self._prepared_after = self.after(10 if self._pending_playback else 100, self._prepared_tick)

    def _prepared_failed(self, exc):
        request, label = self._pending_playback
        self._pending_playback = None
        self.preview_playing = False
        self.playback_started_at = None
        self._warm_transport.cancel()
        if isinstance(exc, ToolMissingError):
            self._start_rendered_preview(list(request.stems), label, request.start_seconds,
                request.duration_seconds, request.fade_in, request.fade_out, request.effects)
        else:
            self.status_var.set(f"Could not start playback: {exc}")
            self.append_log(f"Prepared playback failed: {exc}")
        self._refresh_action_states(transport_only=True)

    def _pause_prepared_preview(self):
        if self._pending_playback:
            self.stop_preview()
            return True
        owner = self.realtime_processes
        pause = getattr(owner, "pause", None)
        if not pause or not pause():return False
        self._cancel_live_preview_restart()
        self._update_playback_position()
        if not self.preview_playing:return True  # The last device buffer finished.
        self.playback_cursor_manual = True
        self.preview_playing = False
        self.playback_started_at = None
        self.playback_seek_dragging = False
        self.realtime_processes = []
        self.eq_editor.clear_spectrum()
        self.status_var.set("Playback stopped.")
        try:
            stems, _ = self._build_last_preview_request()
            request = self._prepared_request(stems)
            # Pending edits must not label old queued PCM as already updated.
            settings = owner._settings
            same_audio = (request.stems == settings["stems"] and request.effects == settings["effects"]
                          and request.fade_in == settings["fade_in"] and request.fade_out == settings["fade_out"]
                          and request.fade_bounds == settings["fade_bounds"]
                          and not owner.playback_position().seeking)
            controller = owner.eq_controller
            if controller:
                same_audio = same_audio and controller.revision == controller.applied_revision
                same_audio = same_audio and controller.mixer_revision == controller.mixer_applied_revision
            if same_audio:self._warm_transport.hold(owner, request)
            else:
                owner.close(wait=False)
                self._warm_transport.prepare(request)
        except (ValueError, tk.TclError, AudioProcessingError):
            owner.close(wait=False)
        self._refresh_action_states(transport_only=True)
        return True
