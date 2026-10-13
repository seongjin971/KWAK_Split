"""Acquire and verify the pinned candidate without changing installed FFmpeg.

Downloaded archives stay in temp/license-remediation/ffmpeg (git-ignored).
The Actions artifact requires existing GitHub credentials. Credentials are used
only for api.github.com, remain in memory, and are never written to the receipt.
This acquisition step alone is not a statement of redistribution compliance.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "temp" / "license-remediation" / "ffmpeg"
BUILD_COMMIT = "63ac3265b0789ea16c7b1f8351cd2ad195a28722"
FFMPEG_COMMIT = "46d899d7a02bc63237472cc4897258d5ddf274ac"
ARTIFACTS = (
    {
        "name": "ffmpeg-n8.1.3-18-g46d899d7a0-win64-gpl-8.1.zip",
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-13-13-05/ffmpeg-n8.1.3-18-g46d899d7a0-win64-gpl-8.1.zip",
        "bytes": 193039590,
        "sha256": "f328d719f8805ea9ab76b8e99dc4a52537e92c6d6f5f8302f297988b9a928bb6",
    },
    {
        "name": "dependency-source-cache.zip",
        "url": "https://api.github.com/repos/BtbN/FFmpeg-Builds/actions/artifacts/11811473165/zip",
        "bytes": 2210375147,
        "sha256": "ae912701a3fc2f92473c5bd16deb8fedadcdd3720badd96d72284637b5d55ffc",
    },
    {
        "name": "FFmpeg-Builds-63ac3265b0789ea16c7b1f8351cd2ad195a28722.tar.gz",
        "url": "https://codeload.github.com/BtbN/FFmpeg-Builds/tar.gz/63ac3265b0789ea16c7b1f8351cd2ad195a28722",
        "bytes": 116749,
        "sha256": "4fd8856d5b207fce5c870a690aefc9a72b9a1943cfc79df8d5d327ec4612c9d2",
    },
    {
        "name": "FFmpeg-46d899d7a02bc63237472cc4897258d5ddf274ac.tar.gz",
        "url": "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/46d899d7a02bc63237472cc4897258d5ddf274ac",
        "bytes": 16923502,
        "sha256": "6626e1f622324597146a8cc90a89bb4c3529f7df55f0a8c998fde55ac5ae4161",
    },
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def artifact_location(url):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, env=env, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30,
    )
    credentials = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    token = credentials.get("password")
    if result.returncode or not token:
        raise RuntimeError("Existing GitHub credentials are required for the source artifact")
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "User-Agent": "KWAK-Split-license-remediation",
        "Accept": "application/vnd.github+json",
    })
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            # Follow the signed object-storage URL in a separate unauthenticated request.
            return error.headers["Location"]
        raise RuntimeError("GitHub source artifact request failed with HTTP " + str(error.code)) from None
    raise RuntimeError("GitHub did not return a source artifact download location")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def acquire(item):
    target = DEST / item["name"]
    if item.get("bytes", 0) > 512 * 1024 * 1024 and not target.exists():
        return acquire_large(item)
    if not target.exists():
        url = item["url"]
        if url.startswith("https://api.github.com/"):
            url = artifact_location(url)
        request = urllib.request.Request(url, headers={"User-Agent": "KWAK-Split-license-remediation"})
        partial = target.with_name(target.name + ".partial")
        received = 0
        next_progress = 128 * 1024 * 1024
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            while block := response.read(8 * 1024 * 1024):
                output.write(block)
                received += len(block)
                if received >= next_progress:
                    print(item["name"], received, "bytes received", flush=True)
                    next_progress += 128 * 1024 * 1024
        actual = fingerprint(partial)
        if any(actual[key] != item[key] for key in ("bytes", "sha256") if key in item):
            raise RuntimeError(item["name"] + " failed pinned size/hash verification; partial file retained")
        partial.replace(target)
    actual = fingerprint(target)
    if any(actual[key] != item[key] for key in ("bytes", "sha256") if key in item):
        raise RuntimeError(item["name"] + " existing file failed pinned verification")
    record = dict(item, **actual, path=str(target.relative_to(ROOT)))
    print(item["name"], "verified", actual["sha256"], flush=True)
    return record


def acquire_large(item):
    """Resume the verified-source download using bounded HTTP byte ranges."""
    target = DEST / item["name"]
    prefix = target.with_name(target.name + ".partial")
    prefix_bytes = prefix.stat().st_size if prefix.exists() else 0
    if prefix_bytes > item["bytes"]:
        raise RuntimeError("Source partial file is larger than the pinned artifact")
    url = artifact_location(item["url"])
    remaining = item["bytes"] - prefix_bytes
    chunk_size = (remaining + 3) // 4 if remaining else 0

    def fetch_range(index):
        start = prefix_bytes + index * chunk_size
        end = min(item["bytes"], start + chunk_size) - 1
        if end < start:
            return None
        part = DEST / (item["name"] + f".range-{start}-{end}")
        if part.exists() and part.stat().st_size == end - start + 1:
            return part
        request = urllib.request.Request(url, headers={
            "User-Agent": "KWAK-Split-license-remediation",
            "Range": f"bytes={start}-{end}",
        })
        with urllib.request.urlopen(request, timeout=90) as response, part.open("wb") as output:
            if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{item['bytes']}":
                raise RuntimeError("Source server did not honor the exact byte range")
            while block := response.read(4 * 1024 * 1024):
                output.write(block)
        if part.stat().st_size != end - start + 1:
            raise RuntimeError("Incomplete source artifact byte range")
        print("Source range", index + 1, "received", part.stat().st_size, "bytes", flush=True)
        return part

    with ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(fetch_range, range(4)))
    assembled = target.with_name(target.name + ".assembled")
    with assembled.open("wb") as output:
        for part in ([prefix] if prefix_bytes else []) + [p for p in parts if p]:
            with part.open("rb") as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    output.write(block)
    actual = fingerprint(assembled)
    if any(actual[key] != item[key] for key in ("bytes", "sha256")):
        raise RuntimeError("Assembled source artifact failed pinned size/hash verification")
    assembled.replace(target)
    record = dict(item, **actual, path=str(target.relative_to(ROOT)))
    print(item["name"], "verified", actual["sha256"], flush=True)
    return record


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        acquired = list(pool.map(acquire, ARTIFACTS))
    receipt = {
        "candidate_only": True,
        "installed_binaries_changed": False,
        "build_recipe_commit": BUILD_COMMIT,
        "ffmpeg_commit": FFMPEG_COMMIT,
        "upstream_workflow_run": 38396239770,
        "source_completeness_verified": False,
        "artifacts": acquired,
    }
    (DEST / "acquisition.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Acquisition receipt:", DEST / "acquisition.json", flush=True)


if __name__ == "__main__":
    main()
