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


@pytest.fixture
def approved_checkout(checkout):
    # A recorded project decision adopting historical upstream evidence, not a
    # claim that this checker obtains a fresh grant from the rights holder.
    documents = {
        "LICENSES/model-decision.md": (
            "Project decision: adopt historical-upstream-mit evidence.\n"
            "This is not a new rights-holder permission grant.\n"
        ),
        "LICENSES/model-card-historical.md": "---\nlicense: mit\n---\nArchived model card fixture.\n",
        "LICENSES/model-notice.txt": "Historical upstream MIT notice fixture.\n",
    }
    materials = []
    for relative, content in documents.items():
        path = checkout / relative
        path.write_text(content, encoding="utf-8")
        materials.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    path = checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["public_binary_distribution"] = "approved"
    status["reason"] = "Project adopted the recorded historical upstream MIT evidence."
    status["model"].update(
        permission_status="approved",
        permission_basis="historical-upstream-mit",
        permission_document="LICENSES/model-decision.md",
        required_materials=materials,
    )
    path.write_text(json.dumps(status), encoding="utf-8")
    return checkout


@pytest.mark.parametrize("public", [True, False])
def test_recorded_historical_mit_decision_with_intact_materials_passes(approved_checkout, public):
    assert check_distribution(approved_checkout, public=public) == []


@pytest.mark.parametrize("public", [True, False])
def test_historical_mit_basis_adoption_accepts_pinned_upstream_card(approved_checkout, public):
    path = approved_checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["model"]["permission_status"] = "historical-mit-basis-adopted"
    status["model"]["permission_document"] = "LICENSES/model-card-historical.md"
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(approved_checkout, public=public) == []


@pytest.mark.parametrize("public", [True, False])
@pytest.mark.parametrize("omit_materials", [True, False])
def test_historical_adoption_requires_material_records(approved_checkout, public, omit_materials):
    path = approved_checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["model"]["permission_status"] = "historical-mit-basis-adopted"
    status["model"]["permission_document"] = "LICENSES/model-card-historical.md"
    if omit_materials:
        del status["model"]["required_materials"]
    else:
        status["model"]["required_materials"] = []
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(approved_checkout, public=public)


@pytest.mark.parametrize("public", [True, False])
def test_legacy_decision_without_optional_material_list_still_passes(approved_checkout, public):
    path = approved_checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    del status["model"]["required_materials"]
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(approved_checkout, public=public) == []


@pytest.mark.parametrize("public", [True, False])
def test_missing_archived_model_card_blocks_build(approved_checkout, public):
    (approved_checkout / "LICENSES/model-card-historical.md").unlink()
    assert check_distribution(approved_checkout, public=public)


@pytest.mark.parametrize("public", [True, False])
def test_changed_model_notice_blocks_build(approved_checkout, public):
    (approved_checkout / "LICENSES/model-notice.txt").write_text("changed terms", encoding="utf-8")
    assert check_distribution(approved_checkout, public=public)


@pytest.mark.parametrize("public", [True, False])
def test_required_material_cannot_escape_checkout_even_with_matching_hash(approved_checkout, public):
    outside = approved_checkout.parent / (approved_checkout.name + "-external-notice.txt")
    outside.write_bytes(b"correctly hashed external notice")
    path = approved_checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["model"]["required_materials"] = [{
        "path": "../" + outside.name,
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }]
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(approved_checkout, public=public)


@pytest.mark.parametrize("public", [True, False])
@pytest.mark.parametrize("materials", [
    None,
    "LICENSES/model-notice.txt",
    {"path": "LICENSES/model-notice.txt", "sha256": "a" * 64},
    [None],
    [{"path": "LICENSES/model-notice.txt"}],
    [{"sha256": "a" * 64}],
    [{"path": 123, "sha256": "a" * 64}],
    [{"path": "LICENSES/model-notice.txt", "sha256": "not a SHA-256"}],
    [{"path": "LICENSES/model-notice.txt", "sha256": 123}],
])
def test_malformed_required_materials_fail_closed(approved_checkout, public, materials):
    path = approved_checkout / "LICENSES/distribution-status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status["model"]["required_materials"] = materials
    path.write_text(json.dumps(status), encoding="utf-8")
    assert check_distribution(approved_checkout, public=public)
