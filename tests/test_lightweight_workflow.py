"""Single-file lifecycle checks using generated audio and isolated preferences."""
import json
import subprocess
import threading
from unittest.mock import patch

from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import OperationCancelled
from backend.edit_state import EDIT_DEFAULTS
from test_loading_lifecycle import session
from test_audit_lifecycle import wait_finished


def mp3(case, name="next", duration=3):
    path = case.paths.root / (name + ".mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency=880:duration={duration}:sample_rate=48000",
                    str(path)], check=True, capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return path


def test_drop_replaces_edited_audio_without_prompt_and_resets_history(session):
    app = session.app
    original, work = session.source, app.source_wav
    app.eq_low_var.set(9)
    app.pitch_semitones_var.set(5)
    app.tempo_percent_var.set(125)
    app.selection_start_var.set(1)
    app.selection_end_var.set(2)
    app.stem_paths = {name: work for name in app.stem_vars}
    app.stem_vars["vocals"]["mute"].set(True)
    app._commit_edit()
    incoming = mp3(session)
    with patch("tkinter.messagebox.askyesnocancel") as prompt:
        app.drop_queue.put(incoming)
        app._process_drop_queue()
        session.wait_idle()
    prompt.assert_not_called()
    assert app.current_input == incoming
    assert original.exists() and incoming.exists()
    assert not work.exists()
    assert not app.stem_paths
    assert app.eq_low_var.get() == 0
    assert app.pitch_semitones_var.get() == 0
    assert app.tempo_percent_var.get() == 100
    assert app.fade_in_var.get() == EDIT_DEFAULTS["fade_in"]
    assert not app.stem_vars["vocals"]["mute"].get()
    assert app._selection_bounds() == (0, app.duration_seconds)
    app.undo_edit()
    assert app.eq_low_var.get() == 0 and app.history.index == 0
    app.eq_low_var.set(4)
    app._commit_edit()
    app.undo_edit()
    assert app.eq_low_var.get() == 0
    app.redo_edit()
    assert app.eq_low_var.get() == 4
    assert not (session.paths.temp / "recovery.json").exists()


def test_corrupt_replacement_keeps_edits_stems_and_removes_partial_audio(session):
    app = session.app
    app.eq_mid_var.set(-7)
    app.stem_paths = {"vocals": app.source_wav}
    app._commit_edit()
    before = app._edit_snapshot(), app.source_wav, dict(app.stem_paths), app.history.index
    owned = set(app._owned_sessions)
    bad = session.paths.root / "corrupt.mp3"
    bad.write_bytes(b"not an mp3")
    app.load_audio_path(bad)
    wait_finished(session)
    assert before == (app._edit_snapshot(), app.source_wav, app.stem_paths, app.history.index)
    assert app.source_wav.is_file()
    assert app._owned_sessions == owned
    assert session.mocks[-1].call_count == 1
    session.mocks[-1].reset_mock()


def test_latest_file_waits_for_cancelled_worker_and_ignores_old_result(session):
    app = session.app
    second, third = mp3(session, "second"), mp3(session, "third", 4)
    previous = app.source_wav
    started, finished = threading.Event(), threading.Event()

    def worker():
        event = app.cancel_event
        started.set()
        assert event.wait(5)
        app.worker_queue.put(("stems_ready", {"paths": {}, "range": [0, 1]}))
        finished.set()
        raise OperationCancelled("old split cancelled")

    app._run_worker("Split Stems", worker)
    assert started.wait(2) and app.load_button.enabled
    assert app.load_audio_path(second)
    assert app.load_audio_path(third)
    assert app.source_wav == previous
    session.wait_idle()
    assert finished.is_set()
    assert app.current_input == third and app._pending_audio is None
    assert not previous.exists() and not app.stem_paths
    session.mocks[-1].assert_not_called()


def test_cancel_pending_replacement_keeps_current_file(session):
    app = session.app
    previous = app.source_wav
    incoming = mp3(session)
    started = threading.Event()

    def worker():
        event = app.cancel_event
        started.set()
        event.wait(5)
        raise OperationCancelled("cancelled")

    app._run_worker("Render WAV", worker)
    assert started.wait(2)
    app.load_audio_path(incoming)
    app.cancel_current_operation()
    session.wait_idle()
    assert app.source_wav == previous and previous.exists()
    assert app._pending_audio is None


def test_open_during_export_removes_partial_output_and_preserves_existing_files(session):
    app = session.app
    incoming = mp3(session)
    app.output_dir = session.paths.root / "exports"
    app.output_dir.mkdir()
    existing = app.output_dir / "keep.wav"
    existing.write_bytes(b"existing result")
    started = threading.Event()

    def slow_render(paths, stems, output, **kwargs):
        output.write_bytes(b"unfinished output")
        started.set()
        assert kwargs["cancel_event"].wait(5)
        raise OperationCancelled("export replaced by new audio")

    with patch("StemSamplePrep.render_mix", side_effect=slow_render):
        app.render_wav()
        assert started.wait(2)
        app.load_audio_path(incoming)
        session.wait_idle()
    assert app.current_input == incoming
    assert list(app.output_dir.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing result"


def test_restart_is_empty_keeps_preferences_and_ignores_old_recovery(session):
    app = session.app
    legacy = session.paths.temp / "recovery.json"
    legacy.write_bytes(b'{"old": "saved session remains untouched"}')
    original_recovery = legacy.read_bytes()
    work = app.source_wav
    app.eq_low_var.set(8)
    app.sample_rate_var.set(44100)
    app.mp3_bitrate_var.set(192)
    app.output_dir = session.paths.root / "exports"
    app.on_close()
    app._close_cleanup_thread.join(timeout=15)
    assert not app._close_cleanup_thread.is_alive()
    assert not work.exists() and session.source.exists()
    assert legacy.read_bytes() == original_recovery
    preferences = json.loads(session.paths.settings_file.read_text(encoding="utf-8"))
    # Simulate settings left by an older release.
    preferences.update(keep_adjustments=True, recent_project="old.kwaksplit")
    session.paths.settings_file.write_text(json.dumps(preferences), encoding="utf-8")
    session.app = reopened = StemSamplePrepApp(ui_scale=1)
    reopened.report_callback_exception = lambda *args: session.callback_errors.append(args)
    reopened.update()
    assert reopened.source_wav is None and not reopened.stem_paths
    assert reopened.eq_low_var.get() == 0
    assert reopened.sample_rate_var.get() == 44100
    assert reopened.mp3_bitrate_var.get() == 192
    assert reopened.output_dir == app.output_dir
    assert not hasattr(reopened, "save_current_project")
    assert not hasattr(reopened, "restore_last_session")
    for chord in ("<Control-s>", "<Control-Shift-O>", "<Control-Shift-R>"):
        assert not reopened.bind(chord)
    assert "keep_adjustments" not in reopened.settings
    assert "recent_project" not in reopened.settings
    assert legacy.read_bytes() == original_recovery
