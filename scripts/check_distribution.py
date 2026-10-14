"""Verify the recorded distribution basis and keep model files out of public packages.

This checks recorded release decisions, not the legal validity of a license.
It never downloads weights, changes runtime behavior, or grants permission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# Unambiguous checkpoint formats. ".pth" is also Python's path-configuration
# suffix (site-packages), so it is only caught by the empty-models-folder rule.
WEIGHT_SUFFIXES = frozenset({".th", ".pt", ".ckpt", ".safetensors", ".onnx"})


def check_distribution(root: Path, *, public: bool = True) -> list[str]:
    problems = []
    status_path = root / "LICENSES/distribution-status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Missing or invalid distribution decision: {exc}"]
    if not isinstance(status, dict) or status.get("schema_version") != 2:
        return ["Unsupported distribution decision schema."]
    model = status.get("model")
    if not isinstance(model, dict):
        return ["Missing model distribution record."]
    if public:
        if status.get("public_binary_distribution") != "approved":
            problems.append("Public executable distribution is ON HOLD: " + str(status.get("reason", "No approval recorded.")))
        # The weights are outside KWAK Split's license; public packages rely on
        # the runner's first-split download from the official Demucs server.
        if model.get("bundled_in_public_packages") is not False:
            problems.append("Public packages must not bundle the Demucs model weights.")
    for relative in ("LICENSE", "THIRD_PARTY_NOTICES.txt", model.get("notice", "")):
        if not isinstance(relative, str) or not relative or not safe_file(root, relative):
            problems.append(f"Missing required licensing document: {relative!r}")
    relative = model.get("path")
    if not isinstance(relative, str) or not relative:
        problems.append("Missing model file identity.")
    else:
        path = safe_file(root, relative)
        # Source checkouts and public packages contain no model. A developer's
        # local copy must still be the recorded official checkpoint.
        if path is not None:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != model.get("sha256"):
                problems.append("The local model differs from the recorded official checkpoint; review it before use.")
    return problems


def bundled_model_files(package: Path) -> list[Path]:
    """Files a public package must not contain: anything in models/ and any checkpoint."""
    models = package / "models"
    return sorted(
        path for path in package.rglob("*")
        if path.is_file() and (
            (path.is_relative_to(models) and path.name != ".gitkeep")
            or path.suffix.lower() in WEIGHT_SUFFIXES
        )
    )


def safe_file(root: Path, relative: str) -> Path | None:
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size == 0:
        return None
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--local-only", action="store_true", help="Check records for a local-only build; this does not authorize distribution.")
    parser.add_argument("--package", type=Path, help="Also fail if this built package contains model files.")
    args = parser.parse_args()
    problems = check_distribution(args.root, public=not args.local_only)
    if args.package is not None:
        if not args.package.is_dir():
            problems.append(f"Package folder not found: {args.package}")
        else:
            problems.extend(f"Model file in package: {path}" for path in bundled_model_files(args.package))
    for problem in problems:
        print("ERROR: " + problem)
    if problems:
        return 1
    if args.package is not None:
        print("Package contains no model files.")
    print("Local licensing records verified; this local-only check does not approve a release." if args.local_only else "Recorded public-distribution checks passed; complete the dependency source checks before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
