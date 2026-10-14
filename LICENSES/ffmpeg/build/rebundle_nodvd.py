"""Derive the no-DVD FFmpeg source sidecar from the verified 2026-10-13 bundle.

build-nodvd.sh links the same dependency image except libdvdcss, libdvdread
and libdvdnav. "parts" copies every other stage archive unchanged into new
dependency ZIPs (checked against source-inventory.json) and records the three
unlinked stages there. "metadata" rebuilds source-metadata.zip from the notices,
inventories, recipes and build log; run it after those files are final.

    python rebundle_nodvd.py parts <folder with the original dependency ZIPs>
    python rebundle_nodvd.py metadata
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
LICENSES = ROOT / "LICENSES"
OUTPUT = ROOT / "vendor-sources/ffmpeg"
BUILD_RECORDS = OUTPUT / "build-nodvd"
ORIGINAL_PARTS = {
    "dependencies-part1.zip": "36efe805140b58e32c45d6338accc8fcacd65e2bf7f230b7ef80059c0bc39c05",
    "dependencies-part2.zip": "92526cceb11648ed2565a853b4f1478716f093f4c6516d3a59f7fc59ca233314",
    "dependencies-part3.zip": "81e9460162a97f58ea38d985e66505c2bed54fffdce30fff58d5eb9eed2e311e",
}
UNLINKED = ("30-libdvdcss", "40-libdvdread", "50-libdvdnav")
PART_LIMIT = 900_000_000
STAMP = (2026, 10, 14, 0, 0, 0)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def member(name, compress):
    info = zipfile.ZipInfo(name, STAMP)
    info.compress_type = compress
    info.external_attr = 0o100644 << 16
    return info


def parts(original):
    inventory_path = LICENSES / "ffmpeg/source-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    removed = [e for e in inventory["entries"] if e["stage"] in UNLINKED]
    inventory["entries"] = [e for e in inventory["entries"] if e["stage"] not in UNLINKED]
    expected = {e["file"]: e.get("distributed_archive_sha256", e["sha256"]) for e in inventory["entries"]}
    for name, digest in ORIGINAL_PARTS.items():
        assert sha(original / name) == digest, f"Unexpected original archive: {name}"

    kept, dropped = [], []
    for name in ORIGINAL_PARTS:
        with zipfile.ZipFile(original / name) as archive:
            for info in archive.infolist():
                file = PurePosixPath(info.filename).name
                if file.split("_", 1)[0] in UNLINKED:
                    dropped.append(file)
                    continue
                assert info.compress_type == zipfile.ZIP_STORED and file in expected, file
                kept.append((name, info))
    assert len(dropped) == len(UNLINKED) and len(kept) == len(expected), (dropped, len(kept))

    groups = []
    for name, info in kept:
        if not groups or sum(i.file_size for _, i in groups[-1]) + info.file_size > PART_LIMIT:
            groups.append([])
        groups[-1].append((name, info))
    records = []
    for number, group in enumerate(groups, 1):
        path = OUTPUT / f"dependencies-part{number}.zip"
        assert not path.exists(), f"Move the previous {path.name} aside first."
        with zipfile.ZipFile(path, "w", allowZip64=True) as target:
            for name, info in group:
                digest = hashlib.sha256()
                with zipfile.ZipFile(original / name) as source, source.open(info) as data, \
                        target.open(member(info.filename, zipfile.ZIP_STORED), "w", force_zip64=True) as out:
                    while block := data.read(8 * 1024 * 1024):
                        digest.update(block)
                        out.write(block)
                assert digest.hexdigest() == expected[PurePosixPath(info.filename).name], info.filename
        with zipfile.ZipFile(path) as check:
            assert check.testzip() is None
        records.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                        "bytes": path.stat().st_size, "bundle_path": "source/ffmpeg/" + path.name})

    if removed:
        inventory["excluded_unlinked_stages"] = [
            {key: e[key] for key in ("stage", "script", "file", "bytes", "sha256")} for e in removed]
        inventory["excluded_unlinked_reason"] = (
            "The no-DVD build disables libdvdread and libdvdnav, so libdvdcss, libdvdread "
            "and libdvdnav are not linked into the distributed executables.")
        inventory["scope"] = (
            "Locally verified corresponding-source material for the pinned win64 GPL 8.1 "
            "no-DVD binaries, with recipes, used dependencies and Rust source supplementation. "
            "No byte-for-byte rebuild is asserted.")
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stages": len(kept), "dropped": dropped, "records": records}, indent=2))


def metadata():
    files = sorted(p for p in (LICENSES / "ffmpeg").rglob("*") if p.is_file() and p.name != "manifest.json")
    extra = [
        (LICENSES / "GPL-3.0.txt", "LICENSES/GPL-3.0.txt"),
        (LICENSES / "FFMPEG_SOURCE_NOTICE.txt", "LICENSES/FFMPEG_SOURCE_NOTICE.txt"),
        (ROOT / "LICENSE", "KWAK-Split-tools-LICENSE.txt"),
        (ROOT / ".github/workflows/ffmpeg-nodvd.yml", ".github/workflows/ffmpeg-nodvd.yml"),
    ]
    extra += [(p, "build-nodvd/" + p.name) for p in sorted(BUILD_RECORDS.glob("*"))
              if p.is_file() and p.suffix != ".zip"]
    path = OUTPUT / "source-metadata.zip"
    assert not path.exists(), "Move the previous source-metadata.zip aside first."
    with zipfile.ZipFile(path, "w") as archive:
        for source, name in [(p, p.relative_to(ROOT).as_posix()) for p in files] + extra:
            archive.writestr(member(name, zipfile.ZIP_DEFLATED), source.read_bytes())
    with zipfile.ZipFile(path) as check:
        assert check.testzip() is None
    print(json.dumps({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                      "bytes": path.stat().st_size, "bundle_path": "source/ffmpeg/" + path.name}, indent=2))


if __name__ == "__main__":
    if sys.argv[1:2] == ["parts"] and len(sys.argv) == 3:
        parts(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["metadata"]:
        metadata()
    else:
        raise SystemExit(__doc__)
