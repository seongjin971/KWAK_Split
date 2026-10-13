"""Select exact win64 GPL 8.1 dependency sources from the private full cache.

Recipe metadata is evaluated separately, without running build/download actions.
Unused variants, including nonfree dependencies, are not placed in the bundle.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "temp/license-remediation/ffmpeg"


def main():
    metadata = json.loads((STAGING / "recipe-metadata.json").read_text())
    by_stage = {}
    for path, value in metadata.items():
        parts = PurePosixPath(path).parts
        stage = parts[1][3:].removesuffix(".sh")
        by_stage.setdefault(stage, []).append((path, value))
    visited = set()
    selected = {}

    def visit(stage):
        if stage in visited:
            return
        visited.add(stage)
        scripts = by_stage[stage]
        if not scripts[-1][1]["enabled"]:
            return
        for path, value in scripts:
            if not value["enabled"]:
                continue
            for dep in value["depends"]:
                visit(dep)
            if value["download_command"].strip():
                name = PurePosixPath(path).stem
                selected[name] = dict(value, script=path)

    visit("final")
    assert not any("fdk-aac" in stage or "decklink" in stage.lower() for stage in selected)
    destination = STAGING / "selected-dependencies"
    destination.mkdir(exist_ok=True)
    entries = []
    excluded = []
    cache = STAGING / "dependency-source-cache.zip"
    with cache.open("rb") as stream:
        assert hashlib.file_digest(stream,"sha256").hexdigest() == "ae912701a3fc2f92473c5bd16deb8fedadcdd3720badd96d72284637b5d55ffc"
    with zipfile.ZipFile(cache) as archive:
        items = [item for item in archive.infolist() if not item.is_dir()]
        assert len(items) == 1 and items[0].filename.endswith("cache.tar.gz")
        with archive.open(items[0]) as compressed, tarfile.open(fileobj=compressed, mode="r|gz") as outer:
            for item in outer:
                if not item.isfile():
                    continue
                name = PurePosixPath(item.name).name
                match = re.fullmatch(r"(.+)_([0-9a-f]{64})\.tar\.xz", name)
                assert match, name
                stage, command_hash = match.groups()
                if stage not in selected:
                    excluded.append(name)
                    continue
                spec = selected[stage]
                assert command_hash == spec["download_command_sha256"], stage
                target = destination / name
                digest = hashlib.sha256()
                with target.open("wb") as output:
                    payload = outer.extractfile(item)
                    while block := payload.read(8 * 1024 * 1024):
                        digest.update(block)
                        output.write(block)
                entries.append(dict(spec, stage=stage, file=name, bytes=item.size, sha256=digest.hexdigest()))
                print(stage, item.size, flush=True)
    assert set(selected) == {entry["stage"] for entry in entries}
    result = {"target":"win64", "variant":"gpl", "addin":"8.1", "selected":entries, "excluded":excluded}
    (STAGING / "source-selection.json").write_text(json.dumps(result, indent=2)+"\n")
    print("Selected",len(entries),"excluded",len(excluded),"bytes",sum(e["bytes"] for e in entries),flush=True)


if __name__ == "__main__":
    main()
