"""Read a restored session in an isolated real Tk app; never play or export it."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from StemSamplePrep import StemSamplePrepApp
from backend.app_paths import AppPaths
from backend.project_store import atomic_json, read_project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--allow-source-only", action="store_true")
    args = parser.parse_args()
    release = args.release.resolve()
    manifest = release / "temp/recovery.json"
    saved = read_project(manifest, allow_external=True)
    audio = [saved["source_path"], *saved["stem_paths"].values()]
    assert (len(audio)==5 or (args.allow_source_only and len(audio)==1))
    assert all(p.is_file() and p.is_relative_to(release) for p in audio)
    preserved = [manifest, release / "settings.json", *audio]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved}
    settings = AppPaths(release).read_settings()

    class Assets(AppPaths):
        @property
        def bin(self): return release / "bin"
        @property
        def backend(self): return release / "backend"
        @property
        def models(self): return release / "models"

    with tempfile.TemporaryDirectory(prefix="restore-qa-", dir=ROOT / "temp") as folder:
        paths = Assets(Path(folder))
        paths.temp.mkdir(parents=True)
        paths.write_settings(settings)
        local = copy.deepcopy(json.loads(manifest.read_text(encoding="utf-8")))
        local["source"] = str(saved["source_path"])
        local["stems"] = {name: str(p) for name, p in saved["stem_paths"].items()}
        atomic_json(paths.temp / "recovery.json", local)
        errors = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(AppPaths, "from_runtime", return_value=paths))
            stack.enter_context(patch.object(StemSamplePrepApp, "_configure_logging"))
            for name in ("showerror", "showwarning"):
                stack.enter_context(patch("tkinter.messagebox." + name,
                                          side_effect=lambda *a, **k: errors.append(str(a))))
            stack.enter_context(patch("tkinter.filedialog.askopenfilename", return_value=""))
            app = StemSamplePrepApp(ui_scale=1)
            app.report_callback_exception = lambda *a: errors.append(str(a))
            try:
                app.restore_last_session()
                deadline = time.monotonic() + 90
                while app.busy and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                app.update()
                assert not app.busy and not errors, errors
                assert app._edit_snapshot() == saved["edits"]
                assert app.stem_range == tuple(saved["stem_range"])
                assert app.stem_paths == saved["stem_paths"]
                assert str(app.output_dir) == settings["output_dir"]
                export_available=bool(saved["stem_paths"])
                assert not app.preview_playing and app.export_stems_button.cget("state") == ("normal" if export_available else "disabled")
                result = {"method": "real Tk restore in isolated settings/workspace; no playback/export",
                          "edits_preserved": True, "four_stems_restored": len(saved["stem_paths"])==4,
                          "source_only_restored": not saved["stem_paths"],
                          # A saved point selection is valid session state even
                          # though playback/export need a positive-length range.
                          "selection": list(app._selection_bounds_no_error()),
                          "selection_has_length": saved["edits"]["selection_end"] != saved["edits"]["selection_start"],
                          "save_folder": str(app.output_dir), "export_available": export_available,
                          "callback_errors": errors}
            finally:
                app.on_close()
                app._warm_transport.close()
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved}
    assert before == after, "User session changed during isolated verification"
    result["user_session_hashes_unchanged"] = True
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    (args.evidence_dir / "restored-session-results.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
