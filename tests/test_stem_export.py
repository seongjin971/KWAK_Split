"""Four-track export contracts, real formats, preservation and compact controls."""
from array import array
import json
import math
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import test_workspace
from StemSamplePrep import StemSamplePrepApp
from backend.audio_processing.ffmpeg_tools import AudioProcessingError, OperationCancelled, extract_audio_range
from backend.workspace_features import WorkspaceFeatures


@pytest.fixture
def session():
    original = StemSamplePrepApp._set_initial_compact_window

    def hidden(app):
        original(app)
        app.withdraw()

    case = test_workspace.WorkspaceTests()
    with patch.object(StemSamplePrepApp, "_set_initial_compact_window", hidden):
        case.setUp()
        try:
            yield case
            assert not case.callback_errors
        finally:
            case.tearDown()


def attach_stems(case):
    crop = case.paths.root / "selected-stem.wav"
    extract_audio_range(case.paths, case.source, crop, 2, 2)
    app = case.app
    app.stem_paths = {name: crop for name in app.stem_vars}
    app.stem_range = (2, 4)
    app.selection_start_var.set(2.5)
    app.selection_end_var.set(3.5)
    app._selection_changed()
    app._refresh_action_states()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def command(name, *args):
    return subprocess.run([shutil.which(name), "-v", "error", *args], capture_output=True,
                          check=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout


def decode(path):
    samples = array("f")
    samples.frombytes(command("ffmpeg", "-i", str(path), "-af", "pan=mono|c0=c0", "-f", "f32le", "-"))
    return samples


def rms(samples):
    return math.sqrt(sum(value * value for value in samples) / len(samples))


@pytest.mark.parametrize("kind,rate,depth,bitrate", (
    ("WAV", 48000, 24, 320), ("WAV", 44100, 16, 320),
    ("MP3", 48000, 24, 320), ("MP3", 44100, 16, 128),
))
def test_four_real_files_follow_format_selection_gain_and_effects(session, kind, rate, depth, bitrate):
    app = session.app
    attach_stems(session)
    app.current_input = session.paths.root / "음악 demo.wav"
    app.stem_export_format_var.set(kind)
    app.sample_rate_var.set(rate)
    app.bit_depth_var.set(depth)
    app.mp3_bitrate_var.set(bitrate)
    app.tempo_percent_var.set(125)
    app.pitch_semitones_var.set(3)
    app.eq_mid_freq_var.set(440)
    app.eq_mid_var.set(-6)
    app.fade_in_var.set(.2)
    app.fade_out_var.set(.2)
    app.limiter_enabled_var.set(False)
    gains = {"vocals": .5, "drums": 1, "bass": 0, "other": .25}
    for name, values in app.stem_vars.items():
        values["volume"].set(gains[name] * 100)
        values["mute"].set(True)
    app.stem_vars["vocals"]["solo"].set(True)
    snapshot = app._edit_snapshot()
    app.export_stems_button.invoke()
    assert app.busy and not app.export_stems_button.enabled
    session.wait_idle()
    assert len(app.result_files) == 4
    assert set(app.output_dir.iterdir()) == set(app.result_files)
    levels = {}
    for name, path in zip(gains, app.result_files):
        assert path.name == f"음악 demo_2.50-3.50_{name}.{kind.lower()}"
        stream = json.loads(command("ffprobe", "-show_streams", "-of", "json", str(path)))["streams"][0]
        assert int(stream["sample_rate"]) == rate
        if kind == "WAV":
            assert stream["codec_name"] == f"pcm_s{depth}le"
        else:
            assert stream["codec_name"] == "mp3" and int(stream["bit_rate"]) == bitrate * 1000
        samples = decode(path)
        assert len(samples) / rate == pytest.approx(.8, abs=.025)
        middle = samples[round(.3 * rate):round(.5 * rate)]
        level = rms(middle)
        levels[name] = level
        if name == "bass":
            assert max(map(abs, samples)) < .0001
        else:
            assert level > .002  # Even muted/non-soloed tracks must contain audio.
            for portion in (samples[:round(.03 * rate)], samples[-round(.03 * rate):]):
                assert rms(portion) < level * .35
            crossings = sum(left <= 0 < right for left, right in zip(middle, middle[1:]))
            frequency = crossings * rate / len(middle)
            assert frequency == pytest.approx(440 * 2 ** (3 / 12), abs=6)
    assert levels["vocals"] / levels["drums"] == pytest.approx(.5, abs=.03)
    assert levels["other"] / levels["drums"] == pytest.approx(.25, abs=.03)
    assert app._edit_snapshot() == snapshot
    assert app.export_stems_button.enabled and "(+3 files)" in app.status_var.get()


def test_format_setting_is_visible_persisted_and_validated_on_startup(session):
    app = session.app
    assert app.stem_export_format_var.get() == "WAV"
    app.open_render_settings()
    app._dialog.withdraw()
    choice = next(widget for widget in descendants(app._dialog)
                  if widget.winfo_class() == "TCombobox"
                  and str(widget.cget("textvariable")) == str(app.stem_export_format_var))
    assert tuple(choice.cget("values")) == ("WAV", "MP3")
    assert str(choice.cget("state")) == "readonly"
    choice.set("MP3")
    app._save_compact_settings()
    saved = session.paths.read_settings()
    assert saved["stem_export_format"] == "MP3"
    restored = SimpleNamespace(settings=saved, peak_normalize_var=app.peak_normalize_var)
    WorkspaceFeatures._init_workspace(restored)
    assert restored.stem_export_format_var.get() == "MP3"
    restored.settings = {"stem_export_format": "invalid"}
    WorkspaceFeatures._init_workspace(restored)
    assert restored.stem_export_format_var.get() == "WAV"


def test_incomplete_stems_and_busy_state_cannot_start_an_export(session):
    app = session.app
    assert not app.export_stems_button.enabled
    attach_stems(session)
    assert app.export_stems_button.enabled
    with patch("StemSamplePrep.render_mix") as render:
        app._set_busy(True, "Busy")
        app.export_individual_stems()
        assert not app.export_stems_button.enabled
        app._set_busy(False)
        del app.stem_paths["bass"]
        app.export_individual_stems()
        assert not app.export_stems_button.enabled
        assert "All four stems" in app.status_var.get()
        render.assert_not_called()
    assert not list(app.output_dir.iterdir())


def test_existing_files_survive_repeated_export_and_missing_folder_is_created(session):
    app = session.app
    attach_stems(session)
    app.output_dir /= "new folder"
    app.export_individual_stems()
    session.wait_idle()
    originals = {path: path.read_bytes() for path in app.result_files}
    app.export_individual_stems()
    session.wait_idle()
    assert len(list(app.output_dir.iterdir())) == 8
    for path in app.result_files:
        assert path.stem.endswith("(1)")
    assert all(path.read_bytes() == contents for path, contents in originals.items())


@pytest.mark.parametrize("failure", ("render", "cancel", "publish"))
def test_failed_or_cancelled_batch_removes_only_its_own_files(session, failure):
    app = session.app
    attach_stems(session)
    retained = app.output_dir / "test_2.50-3.50_vocals.wav"
    retained.write_bytes(b"existing user output")
    renders = []
    renames = []
    original_rename = Path.rename

    def fake_render(paths, stems, path, **kwargs):
        path.write_bytes(b"temporary output")
        renders.append(path)
        if len(renders) == 2:
            if failure == "render":
                raise AudioProcessingError("Test render failed")
            if failure == "cancel":
                app.cancel_event.set()
                raise OperationCancelled("Task cancelled.")

    def rename(path, target):
        renames.append(path)
        if failure == "publish" and len(renames) == 2:
            raise PermissionError("Test publish failed")
        return original_rename(path, target)

    with patch("StemSamplePrep.render_mix", side_effect=fake_render), \
            patch.object(Path, "rename", rename), patch("tkinter.messagebox.showerror") as error:
        app.export_individual_stems()
        session.wait_idle()
        assert error.called == (failure != "cancel")
    assert list(app.output_dir.iterdir()) == [retained]
    assert retained.read_bytes() == b"existing user output"
    assert not app.result_files and app.export_stems_button.enabled
    assert app.source_wav.exists() and len(app.stem_paths) == 4


def test_unwritable_folder_is_inline_and_starts_no_worker(session):
    app = session.app
    attach_stems(session)
    app.output_dir = session.source  # A file cannot be used as a directory.
    original = session.source.read_bytes()
    with patch.object(app, "_run_worker") as worker:
        app.export_individual_stems()
        worker.assert_not_called()
    assert "Cannot save" in app.status_var.get()
    assert session.source.read_bytes() == original


def test_normalize_and_opt_in_cleanup_apply_after_all_four_outputs(session):
    app = session.app
    attach_stems(session)
    app.peak_normalize_var.set(True)
    app.delete_temp_var.set(True)
    source_work = app.source_wav
    app.export_individual_stems()
    session.wait_idle()
    assert len(app.result_files) == 4 and all(path.exists() for path in app.result_files)
    for path in app.result_files:
        samples = decode(path)
        assert .85 < max(map(abs, samples)) <= 1
    assert app.source_wav is None and not source_work.exists()
    assert not app.stem_paths and not app.export_stems_button.enabled
    assert session.source.exists()  # User input is never deleted.


def test_mixer_header_keeps_both_actions_visible_at_layout_boundary(session):
    app = session.app
    app.deiconify()
    for width, height in ((1000, 700), (760, 620), (740, 620), (640, 480)):
        app.geometry(f"{width}x{height}")
        app.update()
        app._layout_compact()
        app.update()
        header = app.export_stems_button.master
        widgets = header.winfo_children()
        for widget in widgets:
            assert widget.winfo_ismapped()
            assert widget.winfo_x() >= 0
            assert widget.winfo_x() + widget.winfo_width() <= header.winfo_width()
            assert widget.winfo_width() >= widget.winfo_reqwidth()
        intervals = sorted((widget.winfo_x(), widget.winfo_x() + widget.winfo_width()) for widget in widgets)
        assert all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:]))
