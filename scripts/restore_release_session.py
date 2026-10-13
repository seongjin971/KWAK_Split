"""Explicit, local-only release-session restore; dry-run unless --apply is given.

Only the supplied old/new workspace prefixes may locate working audio. Relative
audio references are resolved inside the source release's temp directory. This
does not migrate the application or alter an older release. Run with the app
closed, after the destination release has passed its clean-package checks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

STEMS = ("vocals", "drums", "bass", "other")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(value, label):
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{label} must be an absolute path.")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be an absolute path without traversal: {value}")
    return path


def _within(path, parent):
    return path == parent or parent in path.parents


def _json_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _atomic_bytes(path, data):
    """Replace one file atomically; the caller owns its parent directory."""
    descriptor, temporary = tempfile.mkstemp(prefix=".restore-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path):
    data = path.read_bytes()
    document = json.loads(data.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data, document


def _current_bytes(path):
    if path.exists() and not path.is_file():
        raise ValueError(f"Expected a file: {path}")
    return path.read_bytes() if path.exists() else None


def _mapped_path(value, old_workspace, new_workspace, label, *, audio=False):
    path = _absolute(value, label)
    if _within(path, old_workspace):
        result = new_workspace / path.relative_to(old_workspace)
    elif _within(path, new_workspace):
        result = path
    else:
        if audio:
            raise ValueError(f"{label} is outside the authorized workspaces: {path}")
        return path, False
    resolved = result.resolve()
    if not _within(resolved, new_workspace):
        raise ValueError(f"{label} resolves outside the new workspace: {result}")
    return result, True


def prepare_restore(source_release, destination_release, old_workspace, new_workspace, evidence_dir, *, allow_source_only=False):
    """Read and validate inputs without writing; return a plan plus private bytes."""
    old_workspace = _absolute(old_workspace, "old workspace")
    new_workspace = _absolute(new_workspace, "new workspace").resolve(strict=True)
    if old_workspace != new_workspace and (_within(old_workspace, new_workspace) or _within(new_workspace, old_workspace)):
        raise ValueError("Different old/new workspaces must not be nested.")
    source_release = _absolute(source_release, "source release").resolve(strict=True)
    destination_release = _absolute(destination_release, "destination release").resolve(strict=True)
    evidence_dir = _absolute(evidence_dir, "evidence directory").resolve()
    for label, path in (("source release", source_release), ("destination release", destination_release)):
        if not path.is_dir() or path == new_workspace or not _within(path, new_workspace):
            raise ValueError(f"{label} must be a directory inside the new workspace.")
    if _within(source_release, destination_release) or _within(destination_release, source_release):
        raise ValueError("Source and destination releases must be separate directories.")
    protected = [source_release, destination_release]
    if old_workspace != new_workspace:
        protected.append(old_workspace)
    if any(_within(evidence_dir, root) or _within(root, evidence_dir) for root in protected):
        raise ValueError("Evidence must be separate from release folders and the distinct old workspace.")
    if evidence_dir.exists() and (not evidence_dir.is_dir() or any(evidence_dir.iterdir())):
        raise ValueError("Evidence directory must be absent or empty; existing evidence is preserved.")
    temp = destination_release / "temp"
    if not temp.is_dir() or not _within(temp.resolve(), destination_release):
        raise ValueError("Destination release must have its own existing temp directory.")
    session = temp / "restored-session"
    if session.exists() or session.is_symlink():
        raise FileExistsError(f"Refusing to overwrite an existing restored session: {session}")

    source_files = {"settings": source_release / "settings.json", "recovery": source_release / "temp/recovery.json"}
    destination_files = {"settings": destination_release / "settings.json", "recovery": temp / "recovery.json"}
    source_bytes, documents, destination_bytes = {}, {}, {}
    for name, path in source_files.items():
        if not _within(path.resolve(), source_release):
            raise ValueError(f"Source {name} points outside its release.")
        source_bytes[name], documents[name] = _read_json(path)
    for name, path in destination_files.items():
        if not _within(path.resolve(), destination_release) or path.is_symlink():
            raise ValueError(f"Destination {name} points outside its release.")
        destination_bytes[name] = _current_bytes(path)

    settings = copy.deepcopy(documents["settings"])
    recovery = copy.deepcopy(documents["recovery"])
    if recovery.get("format") != "kwak-split-project" or recovery.get("version") not in (1, 2):
        raise ValueError("Source recovery is not a supported KWAK Split project.")
    if (not isinstance(recovery.get("stems"), dict) or
            (set(recovery["stems"]) != set(STEMS) and not (allow_source_only and not recovery["stems"]))):
        raise ValueError("Source recovery must contain exactly four stems.")
    output, output_internal = _mapped_path(settings.get("output_dir", ""), old_workspace, new_workspace, "output_dir")
    if not output.is_dir():
        raise FileNotFoundError(f"Save folder must already exist: {output}")
    settings["output_dir"] = str(output) if output_internal else settings["output_dir"]
    references = []
    for name, value in (("original_input", recovery.get("original_input", "")),
                        ("recent_project", settings.get("recent_project", ""))):
        if value:
            path = _absolute(value, name)
            references.append({"field": name, "path": value, "exists": path.exists(), "action": "preserve"})
    if not output_internal:
        references.append({"field": "output_dir", "path": str(output), "exists": True, "action": "preserve"})

    audio = []
    for name, value in [("source", recovery.get("source")), *recovery["stems"].items()]:
        if not isinstance(value, str) or not value:
            raise ValueError(f"Missing {name} audio path.")
        reference=Path(value)
        if not reference.is_absolute():
            if reference.anchor or ".." in reference.parts:
                raise ValueError(f"{name} relative audio path contains traversal: {value}")
            path=(source_release / "temp" / reference).resolve()
            if not _within(path,source_release / "temp"):
                raise ValueError(f"{name} relative audio resolves outside source temp: {value}")
            value=str(path)
        path, _ = _mapped_path(value, old_workspace, new_workspace, name, audio=True)
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name} audio: {path}")
        if _within(path.resolve(), destination_release) or _within(path.resolve(), evidence_dir):
            raise ValueError(f"Working audio cannot come from destination/evidence: {path}")
        target = session / f"{name}.wav"
        audio.append({"name": name, "source": str(path), "destination": str(target),
                      "size": path.stat().st_size, "sha256": sha256(path)})
        if name == "source":
            recovery["source"] = target.relative_to(temp).as_posix()
        else:
            recovery["stems"][name] = target.relative_to(temp).as_posix()

    backups = []
    for group, paths, contents in (("source", source_files, source_bytes), ("destination", destination_files, destination_bytes)):
        for name, path in paths.items():
            data = contents[name]
            if data is not None:
                backups.append({"source": str(path), "destination": str(evidence_dir / group / f"{name}.json"),
                                "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    updated = {"settings": _json_bytes(settings), "recovery": _json_bytes(recovery)}
    writes = [{"path": str(destination_files[name]), "sha256": hashlib.sha256(data).hexdigest(),
               "previous_sha256": hashlib.sha256(destination_bytes[name]).hexdigest() if destination_bytes[name] is not None else None}
              for name, data in updated.items()]
    plan = {"status": "dry-run", "source_release": str(source_release), "destination_release": str(destination_release),
            "old_workspace": str(old_workspace), "new_workspace": str(new_workspace),
            "backups": backups, "audio_copies": audio, "json_writes": writes,
            "manifest": str(evidence_dir / "manifest.json"), "preserved_references": references,
            "changes": {"settings.output_dir": {"before": documents["settings"].get("output_dir"), "after": settings["output_dir"]},
                        "recovery.source": {"before": documents["recovery"]["source"], "after": recovery["source"]},
                        "recovery.stems": {"before": documents["recovery"]["stems"], "after": recovery["stems"]}}}
    return plan, {"source_files": source_files, "destination_files": destination_files,
                  "source_bytes": source_bytes, "destination_bytes": destination_bytes, "updated": updated,
                  "evidence": evidence_dir, "session": session, "temp": temp}


def restore_release_session(source_release, destination_release, old_workspace, new_workspace, evidence_dir, *, apply=False, allow_source_only=False):
    plan, state = prepare_restore(source_release, destination_release, old_workspace, new_workspace, evidence_dir,
                                allow_source_only=allow_source_only)
    if not apply:
        return plan
    evidence = state["evidence"]
    evidence.mkdir(parents=True, exist_ok=True)
    # Exclusive backups preserve exact bytes, including formatting and unknown fields.
    for entry in plan["backups"]:
        backup = Path(entry["destination"])
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open("xb") as stream:
            stream.write(Path(entry["source"]).read_bytes())
        if sha256(backup) != entry["sha256"]:
            raise RuntimeError(f"Input changed while making its backup: {entry['source']}")
    manifest = evidence / "manifest.json"
    _atomic_bytes(manifest, _json_bytes({**plan, "status": "prepared"}))
    staging = Path(tempfile.mkdtemp(prefix=".restore-session-", dir=state["temp"]))
    published = False
    changed = []
    try:
        for entry in plan["audio_copies"]:
            copied = staging / Path(entry["destination"]).name
            shutil.copy2(entry["source"], copied)
            if sha256(copied) != entry["sha256"] or sha256(entry["source"]) != entry["sha256"]:
                raise RuntimeError(f"Audio hash mismatch: {entry['source']}")
        for group in ("source", "destination"):
            for name, path in state[f"{group}_files"].items():
                if _current_bytes(path) != state[f"{group}_bytes"][name]:
                    raise RuntimeError(f"Input changed during restoration: {path}")
        if state["session"].exists() or state["session"].is_symlink():
            raise FileExistsError(f"Restored session appeared during restoration: {state['session']}")
        staging.rename(state["session"])
        published = True
        for name, path in state["destination_files"].items():
            changed.append(name)
            _atomic_bytes(path, state["updated"][name])
        for entry in plan["audio_copies"]:
            entry["verified_sha256"] = sha256(entry["destination"])
            if entry["verified_sha256"] != entry["sha256"]:
                raise RuntimeError(f"Published audio hash mismatch: {entry['destination']}")
        for entry in plan["json_writes"]:
            entry["verified_sha256"] = sha256(entry["path"])
            if entry["verified_sha256"] != entry["sha256"]:
                raise RuntimeError(f"Published JSON hash mismatch: {entry['path']}")
        plan["status"] = "applied"
        _atomic_bytes(manifest, _json_bytes(plan))
        return plan
    except BaseException as exc:
        # Only files written by this invocation are rolled back; original audio
        # and every source-release file are read-only throughout.
        rollback_errors = []
        for name in reversed(changed):
            path = state["destination_files"][name]
            original = state["destination_bytes"][name]
            try:
                if _current_bytes(path) == original:
                    continue
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_bytes(path, original)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        # Keep copied audio if restoring a document failed: recovery may need it.
        if published and not rollback_errors:
            shutil.rmtree(state["session"])
        failed = {**plan, "status": "failed", "error": str(exc), "rollback_errors": rollback_errors}
        try:
            _atomic_bytes(manifest, _json_bytes(failed))
        except OSError:
            pass
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source-release", "destination-release", "old-workspace", "new-workspace", "evidence-dir"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Copy and restore after successful validation; default is dry-run.")
    parser.add_argument("--allow-source-only", action="store_true", help="Also allow a saved session with no separated stems; partial stems remain rejected.")
    args = vars(parser.parse_args(argv))
    try:
        result = restore_release_session(**args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Session restore refused/failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
