"""Bundle the prepared runtime without its development-machine venv dependency.

Uses the same installed CPython and native dependencies; does not install or
modify Python on the host. Windows ._pth isolates imports to the release folder:
https://docs.python.org/3.11/using/windows.html#finding-modules
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path


def bundle(source, destination):
    source=source.resolve();destination=destination.resolve()
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError("Runtime destination must be separate from its source.")
    if any(destination.iterdir()):
        raise ValueError("Runtime destination must be empty; preserving existing files.")
    python=source/"Scripts/python.exe"
    result=subprocess.run([str(python),"-I","-c",
        "import sys,json;print(json.dumps({'base':sys.base_prefix,'version':list(sys.version_info[:3])}))"],
        capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    metadata=json.loads(result.stdout);base=Path(metadata["base"])
    ignore=shutil.ignore_patterns("__pycache__","*.pyc")
    # Copy third-party packages, retaining package metadata and license files.
    shutil.copytree(source/"Lib/site-packages",destination/"Lib/site-packages",ignore=ignore)
    for item in (base/"Lib").iterdir():
        if item.name in ("site-packages","__pycache__"):continue
        target=destination/"Lib"/item.name
        if item.is_dir():shutil.copytree(item,target,ignore=ignore)
        else:shutil.copy2(item,target)
    shutil.copytree(base/"DLLs",destination/"DLLs",ignore=ignore)
    for item in base.iterdir():
        if item.is_file() and (item.suffix.lower()==".dll" or item.name in ("python.exe","pythonw.exe","LICENSE.txt")):
            shutil.copy2(item,destination/item.name)
    version="".join(str(n) for n in metadata["version"][:2])
    (destination/f"python{version}._pth").write_text(".\nLib\nDLLs\nLib\\site-packages\nimport site\n",encoding="ascii")
    verification=subprocess.run([str(destination/"python.exe"),"-B","-c",
        "import sys,json,demucs,torch,torchaudio;print(json.dumps({'prefix':sys.prefix,'paths':sys.path,'torch':torch.__version__,'torchaudio':torchaudio.__version__}))"],
        cwd=destination,capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    verified=json.loads(verification.stdout)
    if any(not Path(p).resolve().is_relative_to(destination) for p in verified["paths"]):
        raise RuntimeError("Runtime verification found an external Python import path.")
    (destination/"bundle-info.json").write_text(json.dumps({"python_version":metadata["version"],
        "torch":verified["torch"],"torchaudio":verified["torchaudio"],"imports_confined_to_bundle":True},indent=2),encoding="utf-8")
    print(f"App-local Python {'.'.join(map(str,metadata['version']))}; Demucs/Torch imports verified.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--destination",type=Path,required=True);args=parser.parse_args()
    args.destination.mkdir(parents=True,exist_ok=True)
    bundle(args.source,args.destination)
