import hashlib

import pytest

from scripts import prepare_license_materials as materials


def record(path, content):
    return {"path": path, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def test_unchanged_material_is_verified_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(materials, "ROOT", tmp_path)
    target = tmp_path / "LICENSES/test.txt"
    target.parent.mkdir()
    target.write_bytes(b"original notice")
    materials.fetch_missing([record("LICENSES/test.txt", b"original notice")])


def test_fetch_does_not_overwrite_a_modified_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(materials, "ROOT", tmp_path)
    target = tmp_path / "LICENSES/test.txt"
    target.parent.mkdir()
    target.write_bytes(b"local edit")
    with pytest.raises(ValueError, match="pinned hash"):
        materials.fetch_missing([record("LICENSES/test.txt", b"original notice")])
    assert target.read_bytes() == b"local edit"


def test_required_source_archive_cannot_be_missing(tmp_path):
    with pytest.raises(ValueError, match="Missing material"):
        materials.verify_file(tmp_path / "absent.tar.gz", record("absent.tar.gz", b"source"))


@pytest.mark.parametrize("relative", ["../escape", "LICENSES/../../escape"])
def test_material_paths_cannot_escape_repository(tmp_path, relative):
    with pytest.raises(ValueError, match="escapes"):
        materials.confined(tmp_path, relative)


def test_material_output_must_be_in_license_or_source_area(tmp_path, monkeypatch):
    monkeypatch.setattr(materials, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Unexpected material location"):
        materials.artifact_path({"path": "backend/app.py"})
