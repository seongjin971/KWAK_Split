"""Inspect only the selected GPL win64 source archives and preserve notices."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "temp/license-remediation/ffmpeg"
OUTPUT = Path(__file__).resolve().parent


def inspect(entry):
    file = STAGING / "selected-dependencies" / entry["file"]
    with file.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"]
    recipe = (STAGING / "recipes" / entry["script"]).read_text()
    fields = dict(re.findall(r'^SCRIPT_(\w+)="([^"\n]*)"',recipe,re.M))
    heads, notices, suspect = [], [], []
    source_count = file_count = 0
    cargo_vendor = 0
    body = []
    with tarfile.open(file, mode="r|xz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            file_count += 1
            path = PurePosixPath(member.name)
            parts = [p for p in path.parts if p != "."]
            if path.suffix.lower() in {".c", ".h", ".cpp", ".rs", ".cc", ".s", ".asm"}:
                source_count += 1
            if path.name == "HEAD" and ".git" in parts:
                heads.append(archive.extractfile(member).read().decode().strip())
            if path.name == ".cargo-checksum.json" and "vendor" in parts:
                cargo_vendor += 1
            if "decklink" in member.name.lower() or "blackmagic" in member.name.lower():
                suspect.append(member.name)
            if entry["stage"] == "50-rav1e" and path.name in {"Cargo.lock","Cargo.toml"} and len(parts) == 1:
                (STAGING / ("rav1e-"+path.name)).write_bytes(archive.extractfile(member).read())
            if (len(parts) <= 5 and ".git" not in parts and member.size < 2*1024*1024
                and re.fullmatch(r"(?:COPYING|LICENSE|LICENCE|NOTICE|AUTHORS|COPYRIGHT)(?:[._-].*)?",path.name,re.I)):
                data = archive.extractfile(member).read()
                notices.append({"path":member.name,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)})
                body.append("\n"+"="*78+"\n"+member.name+"\n"+"="*78+"\n"+data.decode("utf-8",errors="replace"))
    refs = {value for key,value in fields.items() if key.startswith("COMMIT") and re.fullmatch(r"[0-9a-f]{40}",value)}
    missing = sorted(refs-set(heads))
    if entry["stage"] == "50-amf":
        # The exact download recipe deliberately removes .git and Thirdparty.
        missing = []
    if entry["stage"] == "20-libiconv":
        # The exact download recipe deliberately removes the gnulib .git directory.
        missing = [ref for ref in missing if ref != fields.get("COMMIT2")]
    component = OUTPUT / "components" / (entry["stage"]+".txt")
    component.parent.mkdir(exist_ok=True)
    component.write_text("Original notices from "+entry["file"]+"\nSHA-256: "+entry["sha256"]+"\n"+"".join(body),encoding="utf-8")
    result = dict(entry,source_fields=fields,git_heads=heads,missing_refs=missing,source_files=source_count,
                  files=file_count,notices=notices,cargo_vendor_packages=cargo_vendor,possible_sdk_paths=suspect)
    print(entry["stage"],file_count,"files",len(notices),"notices; missing refs",len(missing),flush=True)
    return result


def main():
    selection=json.loads((STAGING/"source-selection.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as executor:
        entries=list(executor.map(inspect,selection["selected"]))
    result={"build_commit":"63ac3265b0789ea16c7b1f8351cd2ad195a28722",
            "ffmpeg_commit":"46d899d7a02bc63237472cc4897258d5ddf274ac",
            "target":"win64","variant":"gpl","addin":"8.1","entries":entries,
            "excluded_cache_members":selection["excluded"],
            "missing_refs":[e["stage"] for e in entries if e["missing_refs"]],
            "possible_sdk_paths":{e["stage"]:e["possible_sdk_paths"] for e in entries if e["possible_sdk_paths"]},
            "source_completeness_verified":False,
            "scope":"Archive, recipe and source-commit inventory; Rust dependency follow-up is separate. No byte-for-byte rebuild performed."}
    (OUTPUT/"source-inventory.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("missing_refs","possible_sdk_paths")}),flush=True)


if __name__ == "__main__":
    main()
