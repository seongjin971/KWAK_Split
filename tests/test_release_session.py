"""Session restore tests use byte fixtures, never user audio or release folders."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import restore_release_session as restore


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=4), encoding="utf-8")


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def session(tmp_path):
    old = tmp_path / "old-workspace"
    new = tmp_path / "new-workspace"
    source = new / "release/fix4/KWAK Split"
    destination = new / "release/fix5/KWAK Split"
    output = new / "release/fix1/KWAK Split/output"
    output.mkdir(parents=True)
    (output / "keep.wav").write_bytes(b"old export must not change")
    (destination / "temp").mkdir(parents=True)
    external = tmp_path / "external original.wav"
    external.write_bytes(b"external original")
    settings = {"output_dir": str(old / output.relative_to(new)), "stem_export_format": "MP3",
                "sample_rate": 44100, "bit_depth": 16, "recent_project": "", "unknown": {"keep": "한국어"}}
    recovery = {"format": "kwak-split-project", "version": 2, "original_input": str(external),
                "stem_range": [5.76, 67.6], "edits": {"selection_start": 5.76, "selection_end": 67.6,
                "eq_low": -24, "tempo_percent": 125, "stems": {"vocals": {"volume": 52, "solo": True}}}, "stems": {}}
    audio = {}
    for index, name in enumerate(("source", *restore.STEMS)):
        path = new / ("release/fix4/KWAK Split/temp/sessions/source.wav" if name == "source"
                      else f"release/fix3/KWAK Split/temp/stems/{name}.wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([index]) * (index + 12))
        audio[name] = path
        value = str(old / path.relative_to(new))
        if name == "source":
            recovery[name] = value
        else:
            recovery["stems"][name] = value
    write_json(source / "settings.json", settings)
    write_json(source / "temp/recovery.json", recovery)
    write_json(destination / "settings.json", {"clean": True})
    write_json(destination / "temp/recovery.json", {"clean recovery": True})
    kwargs = dict(source_release=source, destination_release=destination, old_workspace=old,
                  new_workspace=new, evidence_dir=new / "qa/session-restore")
    return SimpleNamespace(**kwargs, kwargs=kwargs, settings=settings, recovery=recovery, audio=audio,
                           external=external, output=output)


def test_dry_run_has_exact_files_and_writes_nothing(session):
    before = snapshot(session.new_workspace.parent)
    result = restore.restore_release_session(**session.kwargs)
    assert result["status"] == "dry-run"
    assert snapshot(session.new_workspace.parent) == before
    assert not session.evidence_dir.exists()
    assert len(result["backups"]) == 4
    assert {entry["destination"] for entry in result["audio_copies"]} == {
        str(session.destination_release / "temp/restored-session" / f"{name}.wav") for name in ("source", *restore.STEMS)}
    assert {entry["source"] for entry in result["audio_copies"]} == {str(path) for path in session.audio.values()}
    assert {entry["path"] for entry in result["json_writes"]} == {
        str(session.destination_release / "settings.json"), str(session.destination_release / "temp/recovery.json")}


def test_source_only_restore_requires_opt_in_and_preserves_latest_state(session):
    session.recovery["stems"]={}
    write_json(session.source_release / "temp/recovery.json",session.recovery)
    original=snapshot(session.source_release)
    with pytest.raises(ValueError):
        restore.restore_release_session(**session.kwargs,apply=True)
    result=restore.restore_release_session(**session.kwargs,apply=True,allow_source_only=True)
    assert result["status"]=="applied" and len(result["audio_copies"])==1
    saved=json.loads((session.destination_release / "temp/recovery.json").read_text(encoding="utf-8"))
    assert saved["stems"]=={} and saved["edits"]==session.recovery["edits"]
    assert snapshot(session.source_release)==original
    assert (session.destination_release / "temp/restored-session/source.wav").read_bytes()==session.audio["source"].read_bytes()


def test_source_only_opt_in_still_rejects_partial_stems_without_writes(session):
    del session.recovery["stems"]["other"]
    write_json(session.source_release / "temp/recovery.json",session.recovery)
    before=snapshot(session.new_workspace.parent)
    with pytest.raises(ValueError):
        restore.restore_release_session(**session.kwargs,apply=True,allow_source_only=True)
    assert snapshot(session.new_workspace.parent)==before


@pytest.mark.parametrize("source_only",(False,True))
def test_previous_release_relative_recovery_is_copied_without_changing_inputs(session,source_only):
    names=("source",) if source_only else ("source",*restore.STEMS)
    session.recovery["stems"]={}
    for name in names:
        relative=f"restored-session/{name}.wav"
        audio=session.source_release / "temp" / relative
        audio.parent.mkdir(parents=True,exist_ok=True)
        audio.write_bytes(session.audio[name].read_bytes())
        if name=="source":session.recovery["source"]=relative
        else:session.recovery["stems"][name]=relative
    write_json(session.source_release / "temp/recovery.json",session.recovery)
    before=snapshot(session.source_release)
    result=restore.restore_release_session(**session.kwargs,apply=True,allow_source_only=source_only)
    assert result["status"]=="applied"
    assert snapshot(session.source_release)==before
    assert len(result["audio_copies"])==len(names)
    for name in names:
        assert (session.destination_release / f"temp/restored-session/{name}.wav").read_bytes()==session.audio[name].read_bytes()


def test_relative_recovery_symlink_cannot_escape_source_temp(session):
    link=session.source_release / "temp/relative.wav"
    try:link.symlink_to(session.external)
    except OSError:pytest.skip("Symlink creation unavailable")
    session.recovery["source"]="relative.wav"
    write_json(session.source_release / "temp/recovery.json",session.recovery)
    before=snapshot(session.new_workspace.parent)
    with pytest.raises(ValueError):restore.restore_release_session(**session.kwargs,apply=True)
    assert snapshot(session.new_workspace.parent)==before


def test_apply_preserves_inputs_edits_and_makes_self_contained_recovery(session):
    original = snapshot(session.source_release)
    old_output = snapshot(session.output)
    clean_destination = snapshot(session.destination_release)
    old_audio = {name: path.read_bytes() for name, path in session.audio.items()}
    result = restore.restore_release_session(**session.kwargs, apply=True)
    assert result["status"] == "applied"
    assert snapshot(session.source_release) == original
    assert snapshot(session.output) == old_output
    assert session.external.read_bytes() == b"external original"
    assert not session.old_workspace.exists()
    settings = json.loads((session.destination_release / "settings.json").read_text(encoding="utf-8"))
    assert settings == {**session.settings, "output_dir": str(session.output)}
    recovery = json.loads((session.destination_release / "temp/recovery.json").read_text(encoding="utf-8"))
    expected = copy.deepcopy(session.recovery)
    expected["source"] = "restored-session/source.wav"
    expected["stems"] = {stem: f"restored-session/{stem}.wav" for stem in restore.STEMS}
    assert recovery == expected
    for name, data in old_audio.items():
        destination = session.destination_release / "temp/restored-session" / f"{name}.wav"
        assert destination.read_bytes() == data == session.audio[name].read_bytes()
        item = next(item for item in result["audio_copies"] if item["name"] == name)
        assert restore.sha256(destination) == item["sha256"] == item["verified_sha256"]
    assert all(item["sha256"] == item["verified_sha256"] for item in result["json_writes"])
    for name, relative in (("settings", "settings.json"), ("recovery", "temp/recovery.json")):
        assert (session.evidence_dir / f"source/{name}.json").read_bytes() == original[relative]
        assert (session.evidence_dir / f"destination/{name}.json").read_bytes() == clean_destination[relative]
    assert json.loads((session.evidence_dir / "manifest.json").read_text(encoding="utf-8")) == result


@pytest.mark.parametrize("bad_path", ("traversal", "prefix-lookalike", "external", "relative", "missing"))
def test_bad_audio_is_rejected_before_any_write(session, bad_path):
    values = {"traversal": str(session.old_workspace / "nested/../source.wav"),
              "prefix-lookalike": str(session.old_workspace.with_name("old-workspace-extra") / "source.wav"),
              "external": str(session.external), "relative": "../../external original.wav",
              "missing": str(session.old_workspace / "missing.wav")}
    session.recovery["source"] = values[bad_path]
    write_json(session.source_release / "temp/recovery.json", session.recovery)
    before = snapshot(session.new_workspace.parent)
    with pytest.raises((ValueError, FileNotFoundError)):
        restore.restore_release_session(**session.kwargs, apply=True)
    assert snapshot(session.new_workspace.parent) == before


def test_external_metadata_and_output_are_preserved_without_guessing(session):
    session.settings["output_dir"] = str(session.external.parent)
    session.settings["recent_project"] = str(session.external.parent / "missing.kwaksplit")
    session.recovery["original_input"] = str(session.external.parent / "missing-original.wav")
    write_json(session.source_release / "settings.json", session.settings)
    write_json(session.source_release / "temp/recovery.json", session.recovery)
    result = restore.restore_release_session(**session.kwargs, apply=True)
    settings = json.loads((session.destination_release / "settings.json").read_text(encoding="utf-8"))
    assert settings == session.settings
    references = {item["field"]: item for item in result["preserved_references"]}
    assert references["original_input"]["exists"] is False
    assert references["recent_project"]["exists"] is False
    assert references["output_dir"]["exists"] is True
    assert all(item["action"] == "preserve" for item in references.values())


def test_existing_restored_session_is_never_overwritten(session):
    restore.restore_release_session(**session.kwargs, apply=True)
    before = snapshot(session.new_workspace)
    with pytest.raises(FileExistsError):
        restore.restore_release_session(**{**session.kwargs, "evidence_dir": session.new_workspace / "qa/retry"}, apply=True)
    assert snapshot(session.new_workspace) == before


@pytest.mark.parametrize("failure", ("copy", "hash", "publish_json", "after_replace"))
def test_failure_preserves_user_files_and_rolls_back_destination(session, monkeypatch, failure):
    source_before = snapshot(session.source_release)
    destination_before = snapshot(session.destination_release)
    audio_before = {name: path.read_bytes() for name, path in session.audio.items()}
    actual_copy = restore.shutil.copy2
    actual_atomic = restore._atomic_bytes
    if failure in ("copy", "hash"):
        def fail_copy(source, destination):
            if Path(source) == session.audio["drums"]:
                if failure == "copy":
                    Path(destination).write_bytes(b"unfinished")
                    raise OSError("injected copy failure")
                Path(destination).write_bytes(b"corrupt copied audio")
                return destination
            return actual_copy(source, destination)
        monkeypatch.setattr(restore.shutil, "copy2", fail_copy)
    else:
        attempts = []
        def fail_atomic(path, data):
            if path == session.destination_release / "temp/recovery.json" and not attempts:
                attempts.append(path)
                if failure == "after_replace":
                    actual_atomic(path, data)
                raise OSError("injected JSON publication failure")
            return actual_atomic(path, data)
        monkeypatch.setattr(restore, "_atomic_bytes", fail_atomic)
    with pytest.raises((OSError, RuntimeError)):
        restore.restore_release_session(**session.kwargs, apply=True)
    assert snapshot(session.source_release) == source_before
    assert snapshot(session.destination_release) == destination_before
    assert {name: path.read_bytes() for name, path in session.audio.items()} == audio_before
    assert session.external.read_bytes() == b"external original"
    result = json.loads((session.evidence_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed" and not result["rollback_errors"]


def test_missing_output_folder_is_not_silently_recreated(session):
    session.settings["output_dir"] = str(session.old_workspace / "missing-output")
    write_json(session.source_release / "settings.json", session.settings)
    before = snapshot(session.new_workspace.parent)
    with pytest.raises(FileNotFoundError, match="Save folder"):
        restore.restore_release_session(**session.kwargs, apply=True)
    assert snapshot(session.new_workspace.parent) == before


def test_cli_defaults_to_dry_run(session, capsys):
    argv = []
    for name, value in session.kwargs.items():
        argv.extend(["--" + name.replace("_", "-"), str(value)])
    before = snapshot(session.new_workspace.parent)
    assert restore.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry-run"
    assert snapshot(session.new_workspace.parent) == before


def test_identical_old_and_new_workspace_is_supported(session):
    session.settings["output_dir"] = str(session.output)
    session.recovery["source"] = str(session.audio["source"])
    session.recovery["stems"] = {name: str(session.audio[name]) for name in restore.STEMS}
    write_json(session.source_release / "settings.json", session.settings)
    write_json(session.source_release / "temp/recovery.json", session.recovery)
    kwargs = {**session.kwargs, "old_workspace": session.new_workspace}
    result = restore.restore_release_session(**kwargs, apply=True)
    assert result["status"] == "applied"
    assert result["changes"]["settings.output_dir"]["before"] == result["changes"]["settings.output_dir"]["after"]
    assert len(result["audio_copies"]) == 5


def test_clean_release_without_existing_documents_is_supported(session):
    (session.destination_release / "settings.json").unlink()
    (session.destination_release / "temp/recovery.json").unlink()
    result = restore.restore_release_session(**session.kwargs, apply=True)
    assert len(result["backups"]) == 2
    assert all(item["previous_sha256"] is None for item in result["json_writes"])
    assert (session.destination_release / "temp/recovery.json").exists()


@pytest.mark.parametrize("overlap", ("same-release", "evidence-in-source", "evidence-in-destination"))
def test_overlapping_mutation_paths_are_rejected_without_writes(session, overlap):
    kwargs = dict(session.kwargs)
    if overlap == "same-release":
        kwargs["destination_release"] = session.source_release
    elif overlap == "evidence-in-source":
        kwargs["evidence_dir"] = session.source_release / "evidence"
    else:
        kwargs["evidence_dir"] = session.destination_release / "evidence"
    before = snapshot(session.new_workspace)
    with pytest.raises(ValueError):
        restore.restore_release_session(**kwargs, apply=True)
    assert snapshot(session.new_workspace) == before


def test_symlinked_audio_cannot_escape_the_authorized_workspace(session):
    link = session.new_workspace / "outside.wav"
    try:
        link.symlink_to(session.external)
    except OSError:
        pytest.skip("Creating symlinks requires Windows Developer Mode or elevated privileges.")
    session.recovery["source"] = str(session.old_workspace / "outside.wav")
    write_json(session.source_release / "temp/recovery.json", session.recovery)
    before = snapshot(session.new_workspace.parent)
    with pytest.raises(ValueError, match="outside the new workspace"):
        restore.restore_release_session(**session.kwargs, apply=True)
    assert snapshot(session.new_workspace.parent) == before
