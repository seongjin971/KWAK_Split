"""Assemble local corresponding-source material; never approve publication."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "temp/license-remediation/ffmpeg"
OUTPUT = ROOT / "vendor-sources/ffmpeg"
LICENSES = ROOT / "LICENSES/ffmpeg"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def add_zip(archive, path, name):
    info = zipfile.ZipInfo(name, (2026, 10, 13, 13, 5, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, 8*1024*1024)


def main():
    assert OUTPUT.resolve().is_relative_to(ROOT.resolve())
    OUTPUT.mkdir(parents=True,exist_ok=True)
    inventory=json.loads((LICENSES/"source-inventory.json").read_text(encoding="utf-8"))
    assert not inventory["missing_refs"]
    entries=inventory["entries"]
    # The recipe only installs AMF public/include. Its other source contains
    # unused DeckLink-generated SDK headers. Do not redistribute that material.
    amf=next(e for e in entries if e["stage"]=="50-amf")
    original=STAGING/"selected-dependencies"/amf["file"]
    filtered=STAGING/"amf-headers-only.tar.xz"
    kept=[]
    with tarfile.open(original,"r:xz") as source,tarfile.open(filtered,"w:xz") as target:
        for member in source:
            name=member.name.removeprefix("./")
            if name=="LICENSE.txt" or name.startswith("amf/public/include/"):
                if not member.isfile() and not member.isdir():
                    raise RuntimeError("Unexpected link in AMF headers")
                target.addfile(member,source.extractfile(member) if member.isfile() else None)
                kept.append(name)
    assert kept and not any("decklink" in name.lower() for name in kept)
    amf["distributed_archive_sha256"]=sha(filtered)
    amf["distributed_archive_bytes"]=filtered.stat().st_size
    amf["distribution_filter"]="Only LICENSE.txt and amf/public/include, exactly the source installed by 50-amf.sh; unused samples/implementations including DeckLink SDK-derived files excluded."
    inventory["possible_sdk_paths_excluded_from_distribution"]=inventory.pop("possible_sdk_paths",{})
    inventory["possible_sdk_paths"]={}
    (LICENSES/"source-inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    groups=[]
    for entry in entries:
        file=filtered if entry["stage"]=="50-amf" else STAGING/"selected-dependencies"/entry["file"]
        expected=entry.get("distributed_archive_sha256",entry["sha256"])
        assert sha(file)==expected,entry["stage"]
        if not groups or sum(p.stat().st_size for _,p in groups[-1])+file.stat().st_size>900_000_000:
            groups.append([])
        groups[-1].append((entry,file))
    paths=[]
    for number,group in enumerate(groups,1):
        path=OUTPUT/f"dependencies-part{number}.zip"
        with zipfile.ZipFile(path,"w",allowZip64=True) as archive:
            for entry,file in group:
                add_zip(archive,file,".cache/downloads/"+entry["file"])
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
        paths.append(path)
        print(path.name,path.stat().st_size,sha(path),flush=True)
    for pattern in ("FFmpeg-Builds-*.tar.gz","FFmpeg-*.tar.gz"):
        path=next(STAGING.glob(pattern));target=OUTPUT/path.name
        shutil.copyfile(path,target)
        assert sha(path)==sha(target)
        paths.append(target)
    records=[{"path":p.relative_to(ROOT).as_posix(),"sha256":sha(p),"bytes":p.stat().st_size,
              "bundle_path":"source/ffmpeg/"+p.name} for p in paths]
    (STAGING/"assembled-source-records.json").write_text(json.dumps(records,indent=2)+"\n")
    print("Assembled",len(records),"files; Rust supplementation and final review still required.",flush=True)


if __name__=="__main__":
    main()
