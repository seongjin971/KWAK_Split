"""Regression checks for fractional track lengths and worker lifecycle."""
import subprocess
import sys
import threading
import time
import tkinter as tk
from unittest.mock import patch

import pytest
import test_workspace


@pytest.fixture
def session():
    case=test_workspace.WorkspaceTests();case.setUp()
    try:yield case
    finally:
        try:alive=bool(case.app.winfo_exists())
        except tk.TclError:alive=False
        if alive:case.tearDown()
        else:
            case.app._warm_transport.close()
            for mock in reversed(case.patches):mock.stop()
            case.folder.cleanup()


def test_fractional_duration_finishes_loading_and_enables_controls(session):
    app=session.app;source=session.paths.root/"fractional.wav"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i",
        "sine=frequency=440:duration=6.006:sample_rate=48000","-ac","2",str(source)],
        check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    app.load_audio_path(source)
    deadline=time.monotonic()+5
    while app.busy and time.monotonic()<deadline:
        app.update();time.sleep(.01)
    assert not session.callback_errors,session.callback_errors
    assert not app.busy
    assert app.play_button.enabled and app.render_button.enabled
    assert not app.cancel_button.winfo_ismapped()
    assert not app.stem_paths  # Open Audio does not split automatically.
    assert app.selection_end_var.get()<=app.duration_seconds


def test_worker_completion_survives_ui_result_handler_error(session):
    app=session.app;app._set_busy(True,"Open Audio")
    app.worker_queue.put(("source_ready",{}));app.worker_queue.put(("done","Open Audio"))
    with patch.object(app,"_handle_source_ready",side_effect=ValueError("injected UI failure")):
        app._process_worker_queue()
    assert not app.busy
    assert app.worker_queue_after_id is not None
    assert "error" in app.status_var.get().lower()


def test_close_during_work_is_immediate_cancels_child_and_keeps_recovery(session):
    app=session.app
    child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    finished=threading.Event()
    def worker():
        app.cancel_event.wait(10)
        finished.set()
    try:
        app._run_worker("Test work",worker);app._register_process(child)
        with patch("tkinter.messagebox.showinfo") as message,patch.object(app,"_guard_project") as guard:
            started=time.monotonic();app.on_close();elapsed=time.monotonic()-started
        assert elapsed<1,elapsed
        message.assert_not_called();guard.assert_not_called()
        assert app.closing and finished.wait(2)
        child.wait(timeout=5)
        assert session.paths.root.joinpath("temp/recovery.json").is_file()
        assert session.source.exists()
    finally:
        if child.poll() is None:child.kill();child.wait()


def test_late_process_registration_after_close_is_terminated(session):
    app=session.app;app.on_close()
    child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        app._register_process(child);child.wait(timeout=5)
    finally:
        if child.poll() is None:child.kill();child.wait()
