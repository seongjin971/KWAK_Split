"""Release policy must fail closed without changing the editor's behavior."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_distribution import check_distribution


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "LICENSES").mkdir()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.txt", "LICENSES/model-evidence.md"):
        (tmp_path / name).write_text("test document", encoding="utf-8")
    status = {
        "schema_version": 1,
        "public_binary_distribution": "on-hold",
        "reason": "Owner chose to preserve model quality pending permission.",
        "model": {
            "path": "models/model.th",
            "sha256": hashlib.sha256(b"reviewed model").hexdigest(),
            "permission_status": "unresolved",
            "evidence": "LICENSES/model-evidence.md",
        },
    }
    (tmp_path / "LICENSES/distribution-status.json").write_text(json.dumps(status), encoding="utf-8")
    return tmp_path


def test_public_build_blocked_even_without_bundled_model(checkout):
    # Removing the file does not resolve the runner's first-use download.
    assert any("ON HOLD" in message for message in check_distribution(checkout))


def test_local_build_does_not_need_a_model_in_source_checkout(checkout):
    assert check_distribution(checkout, public=False) == []


def test_unreviewed_model_is_detected_even_for_local_build(checkout):
    (checkout / "models").mkdir()
    (checkout / "models/model.th").write_bytes(b"different model")
    assert any("differs" in message for message in check_distribution(checkout, public=False))


def test_missing_or_broken_decision_cannot_pass(checkout):
    path = checkout / "LICENSES/distribution-status.json"
    path.write_text("{not json", encoding="utf-8")
    assert check_distribution(checkout)
    path.unlink()
    assert check_distribution(checkout, public=False)


def test_missing_license_cannot_pass_local_build(checkout):
    (checkout / "LICENSE").unlink()
    assert check_distribution(checkout, public=False)


def test_changing_status_alone_does_not_grant_permission(checkout):
    path = checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["public_binary_distribution"] = "approved"
    status["model"]["permission_status"] = "approved"
    path.write_text(json.dumps(status), encoding="utf-8")
    assert any("permission document" in message for message in check_distribution(checkout))


def test_evidence_cannot_escape_checkout(checkout, tmp_path):
    outside = checkout.parent / (checkout.name + "-outside.md")
    outside.write_text("test", encoding="utf-8")
    path = checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["model"]["evidence"] = str(outside)
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(checkout, public=False)
