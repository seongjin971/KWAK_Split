"""Compare shipped Python code with the verified source and record hashes."""
import argparse
import hashlib
import json
import marshal
from pathlib import Path
import types

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
MODULES=("StemSamplePrep","backend.compact_ui","backend.compact_widgets",
         "backend.compact_model","backend.window_bounds",
         "backend.workspace_features","backend.audio_processing.ffmpeg_tools",
         "backend.audio_processing.spectrum","backend.audio_processing.playback_stream",
         "backend.audio_processing.live_eq","backend.audio_processing.qa_live_eq",
         "backend.audio_processing.qa_live_seek","backend.audio_processing.qa_transport",
         "backend.audio_processing.wave_output","backend.audio_processing.warm_transport",
         "backend.prepared_preview","backend.header_status","backend.qa_header_status",
         "backend.window_snapshot","backend.resize_preview","backend.qa_resize")


def normalize(code):
    return code.replace(co_filename="",co_consts=tuple(normalize(value) if isinstance(value,types.CodeType)
                                                       else value for value in code.co_consts))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args=parser.parse_args()
    exe=args.release/"KWAK Split.exe"
    archive=CArchiveReader(str(exe))
    embedded=archive.open_embedded_archive("PYZ.pyz")
    result={"exe_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"modules":[]}
    for name in MODULES:
        path=ROOT/(name.replace(".","/")+".py")
        source=path.read_bytes()
        code=(marshal.loads(archive.extract(name)) if name=="StemSamplePrep" else embedded.extract(name))
        matches=normalize(code)==normalize(compile(source,str(path),"exec",dont_inherit=True))
        assert matches,name
        result["modules"].append({"module":name,"source_sha256":hashlib.sha256(source).hexdigest(),
                                  "frozen_code_matches":matches})
    args.evidence_dir.mkdir(parents=True,exist_ok=True)
    (args.evidence_dir/"frozen-source-verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
