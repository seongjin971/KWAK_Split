"""Verify or fetch pinned third-party notices and corresponding source archives.

Only the five runtime components listed below are managed here. This does not
approve distribution of the application or establish rights to model weights.
No third-party packages are installed, imported, or executed. Installer
containers are read only as data to recover original notices.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("antlr4", "more-itertools", "demucs", "lameenc", "intel-openmp")
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def confined(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Path escapes its declared root: {relative}")
    return path


def manifests() -> list[dict]:
    result = []
    for component in COMPONENTS:
        path = ROOT / "LICENSES" / component / "provenance.json"
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("schema_version") != 1 or item.get("component") != component:
            raise ValueError(f"Unexpected provenance manifest: {path}")
        result.append(item)
    return result


def artifact_path(item: dict) -> Path:
    relative = item["path"]
    if not relative.startswith(("LICENSES/", "vendor-sources/")):
        raise ValueError(f"Unexpected material location: {relative}")
    return confined(ROOT, relative)


def verify_file(path: Path, expected: dict) -> None:
    if not path.is_file():
        raise ValueError(f"Missing material: {path}")
    data = path.read_bytes()
    if len(data) != expected["bytes"] or sha256(data) != expected["sha256"]:
        raise ValueError(f"Material differs from its pinned hash: {path}")


def verify_runtime_packages(runtime: Path) -> int:
    """Compare metadata with the audited pins without importing target packages."""
    pinned: dict[str, str] = {}
    for line in (ROOT / "requirements-demucs.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "--extra-index-url ")):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9.+_-]+)", line)
        if match is None:
            raise ValueError(f"Runtime requirement must be an exact audited pin: {line}")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in pinned:
            raise ValueError(f"Duplicate runtime requirement: {name}")
        pinned[name] = match[2]
    if not pinned:
        raise ValueError("No audited runtime package requirements were found")
    installed: dict[str, str] = {}
    site_packages = confined(runtime, "Lib/site-packages")
    for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
        raw_name = distribution.metadata.get("Name")
        version = distribution.version
        if not raw_name or not version:
            raise ValueError(f"Runtime package has incomplete metadata: {distribution}")
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        if name in installed:
            raise ValueError(f"Duplicate installed runtime package: {name}")
        installed[name] = version
    missing = sorted(pinned.keys() - installed.keys())
    extra = sorted(installed.keys() - pinned.keys())
    changed = sorted(
        f"{name}: {installed[name]} (expected {version})"
        for name, version in pinned.items()
        if name in installed and installed[name] != version
    )
    if missing or extra or changed:
        raise ValueError(
            f"Runtime package inventory differs from the license audit: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
    return len(installed)


def read_msi_stream(path: Path, stream_name: str) -> bytes:
    """Read an embedded cabinet without executing installer actions."""
    if os.name != "nt":
        raise ValueError("Recovering Intel installer notices requires Windows; tracked notices already work on any platform")
    import ctypes
    from ctypes import wintypes

    if any(character in stream_name for character in "'`\r\n"):
        raise ValueError("Unexpected MSI stream name")
    api = ctypes.WinDLL("msi")
    api.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    api.MsiDatabaseOpenViewW.argtypes = [wintypes.UINT, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    api.MsiViewExecute.argtypes = [wintypes.UINT, wintypes.UINT]
    api.MsiViewFetch.argtypes = [wintypes.UINT, ctypes.POINTER(wintypes.UINT)]
    api.MsiRecordReadStream.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    handles = []

    def checked(result: int) -> None:
        if result:
            raise OSError(result, "Could not read Intel notice archive")

    try:
        database = wintypes.UINT()
        checked(api.MsiOpenDatabaseW(str(path), None, ctypes.byref(database)))
        handles.append(database)
        view = wintypes.UINT()
        query = f"SELECT `Data` FROM `_Streams` WHERE `Name` = '{stream_name}'"
        checked(api.MsiDatabaseOpenViewW(database, query, ctypes.byref(view)))
        handles.append(view)
        checked(api.MsiViewExecute(view, 0))
        record = wintypes.UINT()
        checked(api.MsiViewFetch(view, ctypes.byref(record)))
        handles.append(record)
        chunks = []
        total = 0
        while True:
            buffer = ctypes.create_string_buffer(65536)
            size = wintypes.DWORD(65536)
            checked(api.MsiRecordReadStream(record, 1, buffer, ctypes.byref(size)))
            if not size.value:
                break
            total += size.value
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("Embedded Intel notice archive exceeds its size limit")
            chunks.append(buffer.raw[:size.value])
        return b"".join(chunks)
    finally:
        for handle in reversed(handles):
            api.MsiCloseHandle(handle)


def extract_installer_notice(raw: bytes, download: dict) -> bytes:
    # The .exe is a ZIP container. Never launch it, MSI actions, or extracted code.
    member = download["member"]
    if Path(member).name != member or any(c in member for c in "*?/\\"):
        raise ValueError("Unexpected Intel cabinet member name")
    with tempfile.TemporaryDirectory(prefix="kwak-license-") as directory:
        work = Path(directory)
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            msi = source.read(download["outer_member"])
        if sha256(msi) != download["msi_sha256"]:
            raise ValueError("Intel MSI does not match the pinned provenance")
        msi_path = work / "notice-source.msi"
        msi_path.write_bytes(msi)
        cabinet = read_msi_stream(msi_path, download["msi_stream"])
        if sha256(cabinet) != download["cabinet_sha256"]:
            raise ValueError("Intel cabinet does not match the pinned provenance")
        cab_path = work / "notice-source.cab"
        cab_path.write_bytes(cabinet)
        subprocess.run(
            ["expand.exe", "-F:" + member, str(cab_path), str(work)],
            check=True, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (work / member).read_bytes()


def fetch_missing(items: list[dict]) -> None:
    downloads: dict[str, bytes] = {}
    for item in items:
        path = artifact_path(item)
        if path.exists():
            verify_file(path, item)
            continue
        download = item["download"]
        url = download["url"]
        if not url.startswith("https://"):
            raise ValueError(f"Material download must use HTTPS: {url}")
        if download["bytes"] > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"Material exceeds the download limit: {url}")
        if url not in downloads:
            request = urllib.request.Request(url, headers={"User-Agent": "KWAK-Split-license-materials/1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                if not response.url.startswith("https://"):
                    raise ValueError(f"Material download redirected outside HTTPS: {url}")
                raw = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(raw) != download["bytes"] or sha256(raw) != download["sha256"]:
                raise ValueError(f"Downloaded material differs from its pinned hash: {url}")
            downloads[url] = raw
        raw = downloads[url]
        if sha256(raw) != download["sha256"] or len(raw) != download["bytes"]:
            raise ValueError(f"Conflicting artifact descriptions for {url}")
        archive = download.get("archive")
        if archive == "zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as source:
                content = source.read(download["member"])
        elif archive == "tar.gz":
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as source:
                member = source.getmember(download["member"])
                if not member.isfile():
                    raise ValueError(f"License archive member is not a regular file: {member.name}")
                stream = source.extractfile(member)
                if stream is None:
                    raise ValueError(f"Cannot read archive member: {member.name}")
                content = stream.read()
        elif archive == "zip-msi-cab":
            content = extract_installer_notice(raw, download)
        elif archive is None:
            content = raw
        else:
            raise ValueError(f"Unsupported license archive format: {archive}")
        if len(content) != item["bytes"] or sha256(content) != item["sha256"]:
            raise ValueError(f"Extracted material differs from its pinned hash: {item['path']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Existing files are verified, never silently overwritten.
        with path.open("xb") as output:
            output.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true", help="Verify notices AND local corresponding-source archives")
    mode.add_argument("--fetch", action="store_true", help="Fetch only missing pinned materials, then verify everything")
    mode.add_argument("--list-sources", action="store_true", help="Print required source archive paths and bundle destinations")
    parser.add_argument("--runtime", type=Path, help="Also check audited package versions and three pinned binaries under this runtime root")
    args = parser.parse_args()
    try:
        records = manifests()
        files = [item for record in records for item in record["files"]]
        if args.list_sources:
            sources = [item for item in files if item["role"] == "corresponding-source"]
            print(json.dumps({"sources": sources}, indent=2))
            return 0
        if args.fetch:
            fetch_missing(files)
        for item in files:
            verify_file(artifact_path(item), item)
        verified_binaries = 0
        verified_packages = 0
        if args.runtime is not None:
            runtime = args.runtime.resolve()
            verified_packages = verify_runtime_packages(runtime)
            for record in records:
                for binary in record["bundled_binaries"]:
                    path = confined(runtime, binary["path"])
                    if not path.is_file() or sha256(path.read_bytes()) != binary["sha256"]:
                        raise ValueError(f"Runtime binary does not match the audited distribution: {path}")
                    verified_binaries += 1
        print(json.dumps({
            "status": "verified", "components": len(records), "files": len(files),
            "source_archives": sum(item["role"] == "corresponding-source" for item in files),
            "runtime_binaries": verified_binaries,
            "runtime_packages": verified_packages,
            "scope": "Runtime license materials only; not an application distribution approval.",
        }, indent=2))
        return 0
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
