"""Fail closed for public builds while model redistribution is unresolved.

This checks recorded release decisions, not the legal validity of a license.
It never downloads weights, changes runtime behavior, or grants permission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def check_distribution(root: Path, *, public: bool = True) -> list[str]:
    problems = []
    status_path = root / "LICENSES/distribution-status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Missing or invalid distribution decision: {exc}"]
    if not isinstance(status, dict) or status.get("schema_version") != 1:
        return ["Unsupported distribution decision schema."]
    model = status.get("model")
    if not isinstance(model, dict):
        return ["Missing model permission record."]
    if public:
        if status.get("public_binary_distribution") != "approved":
            problems.append("Public executable distribution is ON HOLD: " + str(status.get("reason", "No approval recorded.")))
        if model.get("permission_status") != "approved":
            problems.append("Demucs model redistribution permission remains unresolved; see LICENSES/demucs-model/PROVENANCE.md.")
        # An approved decision must identify the actual permission document.
        permission = model.get("permission_document")
        if not isinstance(permission, str) or not permission:
            problems.append("No model redistribution permission document is recorded.")
        elif not safe_file(root, permission):
            problems.append("The model permission document is missing or outside the package.")
    for relative in ("LICENSE", "THIRD_PARTY_NOTICES.txt", model.get("evidence", "")):
        if not isinstance(relative, str) or not relative or not safe_file(root, relative):
            problems.append(f"Missing required licensing document: {relative!r}")
    relative = model.get("path")
    if not isinstance(relative, str) or not relative:
        problems.append("Missing model file identity.")
    else:
        path = safe_file(root, relative)
        # Source-only checkouts legitimately do not contain a model. Public
        # model-less builds are still held: the runner can download it later.
        if path is not None:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != model.get("sha256"):
                problems.append("The model differs from the recorded license review; review its permissions before packaging.")
    return problems


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
    args = parser.parse_args()
    problems = check_distribution(args.root, public=not args.local_only)
    for problem in problems:
        print("ERROR: " + problem)
    if problems:
        return 1
    print("Local licensing records verified; PUBLIC DISTRIBUTION IS NOT AUTHORIZED." if args.local_only else "Recorded public-distribution checks passed; complete the dependency source checks before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
