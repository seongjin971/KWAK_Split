"""Release policy must fail closed without changing the editor's behavior."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts import check_distribution as checker
from scripts.check_distribution import bundled_model_files, check_distribution


def load_status(root: Path) -> dict:
    return json.loads((root / "LICENSES/distribution-status.json").read_text(encoding="utf-8"))


def save_status(root: Path, status: dict) -> None:
    (root / "LICENSES/distribution-status.json").write_text(json.dumps(status), encoding="utf-8")


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "LICENSES").mkdir()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.txt", "LICENSES/model-notice.txt"):
        (tmp_path / name).write_text("test document", encoding="utf-8")
    save_status(tmp_path, {
        "schema_version": 2,
        "public_binary_distribution": "approved",
        "reason": "Public packages exclude the model weights.",
        "model": {
            "path": "models/model.th",
            "sha256": hashlib.sha256(b"reviewed model").hexdigest(),
            "bundled_in_public_packages": False,
            "notice": "LICENSES/model-notice.txt",
        },
    })
    return tmp_path


@pytest.mark.parametrize("public", [True, False])
def test_model_free_decision_passes(checkout, public):
    assert check_distribution(checkout, public=public) == []


def test_public_build_blocked_while_on_hold(checkout):
    status = load_status(checkout)
    status["public_binary_distribution"] = "on-hold"
    save_status(checkout, status)
    assert any("ON HOLD" in message for message in check_distribution(checkout))
    assert check_distribution(checkout, public=False) == []


@pytest.mark.parametrize("bundled", [True, None, "false", 0])
def test_public_build_cannot_bundle_model_weights(checkout, bundled):
    status = load_status(checkout)
    if bundled is None:
        del status["model"]["bundled_in_public_packages"]
    else:
        status["model"]["bundled_in_public_packages"] = bundled
    save_status(checkout, status)
    assert any("must not bundle" in message for message in check_distribution(checkout))


@pytest.mark.parametrize("public", [True, False])
def test_unreviewed_local_model_is_detected(checkout, public):
    (checkout / "models").mkdir()
    (checkout / "models/model.th").write_bytes(b"different model")
    assert any("differs" in message for message in check_distribution(checkout, public=public))


def test_reviewed_local_model_is_accepted(checkout):
    (checkout / "models").mkdir()
    (checkout / "models/model.th").write_bytes(b"reviewed model")
    assert check_distribution(checkout) == []


def test_missing_or_broken_decision_cannot_pass(checkout):
    path = checkout / "LICENSES/distribution-status.json"
    path.write_text("{not json", encoding="utf-8")
    assert check_distribution(checkout)
    path.unlink()
    assert check_distribution(checkout, public=False)


@pytest.mark.parametrize("public", [True, False])
def test_superseded_schema_is_rejected(checkout, public):
    status = load_status(checkout)
    status["schema_version"] = 1
    save_status(checkout, status)
    assert check_distribution(checkout, public=public)


@pytest.mark.parametrize("name", ["LICENSE", "THIRD_PARTY_NOTICES.txt", "LICENSES/model-notice.txt"])
def test_missing_licensing_document_cannot_pass_local_build(checkout, name):
    (checkout / name).unlink()
    assert check_distribution(checkout, public=False)


def test_model_notice_cannot_escape_checkout(checkout):
    outside = checkout.parent / (checkout.name + "-outside.txt")
    outside.write_text("test", encoding="utf-8")
    status = load_status(checkout)
    status["model"]["notice"] = str(outside)
    save_status(checkout, status)
    assert check_distribution(checkout, public=False)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "KWAK Split"
    for name in ("bin/ffmpeg.exe", "LICENSES/GPL-3.0.txt", "models/.gitkeep",
                 "backend/demucs_runtime/Lib/site-packages/distutils-precedence.pth"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"package file")
    return root


def test_model_free_package_passes(package):
    # A site-packages ".pth" path file is not a checkpoint.
    assert bundled_model_files(package) == []


def test_any_file_in_package_models_folder_is_reported(package):
    checkpoint = package / "models/torch/hub/checkpoints/955717e8-8726e21a.th"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"weights")
    cache = package / "models/huggingface/model.pth"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"weights")
    assert bundled_model_files(package) == sorted([checkpoint, cache])


def test_checkpoint_outside_models_folder_is_reported(package):
    stray = package / "backend/demucs_runtime/htdemucs.SafeTensors"
    stray.write_bytes(b"weights")
    assert bundled_model_files(package) == [stray]


def test_cli_rejects_package_with_model(checkout, package, monkeypatch, capsys):
    (package / "models/model.th").write_bytes(b"weights")
    monkeypatch.setattr(sys, "argv", ["check_distribution.py", "--root", str(checkout), "--package", str(package)])
    assert checker.main() == 1
    assert "Model file in package" in capsys.readouterr().out


def test_cli_accepts_model_free_package(checkout, package, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_distribution.py", "--root", str(checkout), "--package", str(package)])
    assert checker.main() == 0
