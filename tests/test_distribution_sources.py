import hashlib
import json

import pytest

from scripts.prepare_distribution_sources import prepare


@pytest.fixture
def sources(tmp_path):
    def item(name, content):
        path = tmp_path / "vendor-sources" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return {"path": "vendor-sources/" + name, "bundle_path": "source/" + name,
                "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                "role": "corresponding-source"}
    ffmpeg = item("ffmpeg.tar.gz", b"synthetic source archive")
    lame = item("lame.tar.gz", b"another synthetic archive")
    for name, manifest in (("ffmpeg/manifest.json", {"source_local_verified": True, "source_bundle": [ffmpeg]}),
                           ("lameenc/provenance.json", {"files": [lame]})):
        path = tmp_path / "LICENSES" / name
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_sources_are_staged_with_hash_index(sources):
    destination = sources / "release/test"
    assert len(prepare(sources, destination)) == 2
    assert (destination / "source/ffmpeg.tar.gz").read_bytes() == b"synthetic source archive"
    assert len(json.loads((destination / "source/SHA256.json").read_text())["files"]) == 2


def test_corrupt_download_is_rejected_before_staging(sources):
    (sources / "vendor-sources/ffmpeg.tar.gz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="modified"):
        prepare(sources, sources / "release/test")
    assert not (sources / "release/test").exists()


def test_source_sidecar_cannot_escape_release(sources):
    with pytest.raises(ValueError, match="named release"):
        prepare(sources, sources.parent / "external")


def test_existing_modified_sidecar_is_not_overwritten(sources):
    destination = sources / "release/test"
    prepare(sources, destination)
    (destination / "source/lame.tar.gz").write_bytes(b"local edit")
    with pytest.raises(ValueError, match="modified"):
        prepare(sources, destination)
    assert (destination / "source/lame.tar.gz").read_bytes() == b"local edit"


def test_unverified_ffmpeg_bundle_is_not_accepted(sources):
    path = sources / "LICENSES/ffmpeg/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["source_local_verified"] = False
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not verified"):
        prepare(sources)
