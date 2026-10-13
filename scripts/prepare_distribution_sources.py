"""Verify pinned source archives, optionally stage them next to an app folder.

Publish the resulting source/ directory alongside the executable download when
public distribution is authorized. GitHub Actions caches expire and are not a
substitute for supplying the saved corresponding source to recipients.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Source material path escapes its root: {relative}")
    return path


def source_records(root: Path) -> list[dict]:
    ffmpeg = json.loads((root / "LICENSES/ffmpeg/manifest.json").read_text(encoding="utf-8"))
    if not ffmpeg.get("source_local_verified") or not ffmpeg.get("source_bundle"):
        raise ValueError("FFmpeg's complete local corresponding-source bundle is not verified.")
    records = list(ffmpeg["source_bundle"])
    lame = json.loads((root / "LICENSES/lameenc/provenance.json").read_text(encoding="utf-8"))
    records.extend(item for item in lame["files"] if item["role"] == "corresponding-source")
    destinations = [item["bundle_path"] for item in records]
    if len(set(destinations)) != len(destinations):
        raise ValueError("Source archive destinations must be unique.")
    for item in records:
        if not item["bundle_path"].startswith("source/"):
            raise ValueError("Every source archive must be staged below source/.")
    return records


def verify(path: Path, item: dict) -> None:
    if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
        raise ValueError(f"Missing or modified corresponding source: {path}")


def prepare(root: Path, destination: Path | None = None) -> list[dict]:
    records = source_records(root)
    for item in records:
        verify(inside(root, item["path"]), item)
    if destination is not None:
        destination = destination.resolve()
        release_root = (root / "release").resolve()
        if not destination.is_relative_to(release_root) or destination == release_root:
            raise ValueError("Stage source materials inside a named release/ folder.")
        for item in records:
            source = inside(root, item["path"])
            target = inside(destination, item["bundle_path"])
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            verify(target, item)  # Never replace an existing mismatching archive.
        index = {"schema_version": 1, "files": [
            {key: item[key] for key in ("bundle_path", "sha256", "bytes")}
            for item in records
        ]}
        (destination / "source/SHA256.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, help="Named release folder; source/ is staged next to its app folder")
    args = parser.parse_args()
    try:
        records = prepare(ROOT, args.destination)
        print(json.dumps({"status": "verified", "source_archives": len(records),
                          "bytes": sum(item["bytes"] for item in records),
                          "staged": args.destination is not None}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("ERROR: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
