"""Independent lifecycle audit, confined to generated temporary audio."""
import json
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

import test_workspace
from backend.audio_processing.ffmpeg_tools import OperationCancelled


@pytest.fixture
def session():
    case = test_workspace.WorkspaceTests()
    case.setUp()
    try:
        yield case
    finally:
        case.tearDown()


def wait_finished(case, timeout=5):
    deadline = time.monotonic() + timeout
    while case.app.busy and time.monotonic() < deadline:
        case.app.update()
        time.sleep(0.01)
    case.app.update()
    assert not case.app.busy, "Worker did not finish"
    assert not case.callback_errors, case.callback_errors


def test_cancel_before_process_registration_stops_late_child(session):
    """Cancellation can land between Popen and its process callback."""
    app = session.app
    app.cancel_event = threading.Event()
    app._set_busy(True, "Synthetic silent worker")
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        assert app.current_process is None
        app.cancel_current_operation()
        assert app.cancel_event.is_set()
        app._register_process(child)
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pytest.fail("Cancelled child registered afterward is left running")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)
        app._set_busy(False)


def test_corrupt_audio_preserves_open_audio(session):
    app = session.app
    previous_source = app.source_wav
    corrupt = session.paths.root / "corrupt.wav"
    corrupt.write_bytes(b"This is not a WAV file")
    app.load_audio_path(corrupt)
    wait_finished(session)
    assert app.source_wav == previous_source
    assert app.source_wav.exists()
    assert app.play_button.enabled and app.load_button.enabled
    assert session.mocks[-1].call_count == 1
    session.mocks[-1].reset_mock()
    app.load_audio_path(session.source)
    session.wait_idle()


def test_cancelled_audio_conversion_preserves_loaded_session(session):
    app = session.app
    previous_source = app.source_wav
    previous_session = app.session_name
    with patch("StemSamplePrep.convert_to_work_wav", side_effect=OperationCancelled("Cancelled conversion")):
        app.load_audio_path(session.source)
        session.wait_idle()
    assert app.source_wav == previous_source
    assert app.session_name == previous_session
    assert app.source_wav.exists()
    assert app.status_var.get() == "Task cancelled."
    assert app.play_button.enabled and app.load_button.enabled
    assert not app.cancel_button.winfo_ismapped()


def test_worker_failure_allows_next_audio_load(session):
    app = session.app

    def failing_worker():
        raise ValueError("Injected worker failure")

    app._run_worker("Failing worker", failing_worker)
    wait_finished(session)
    assert app.worker_queue_after_id is not None
    assert session.mocks[-1].call_count == 1
    session.mocks[-1].reset_mock()
    app.load_audio_path(session.source)
    session.wait_idle()
    assert app.play_button.enabled and app.load_button.enabled
    assert not app.cancel_button.winfo_ismapped()
