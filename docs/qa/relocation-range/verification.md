# Relocation and selection bounds

Date: 2026-09-26  
Status: **USER_REVIEW_READY**

The active project is `C:\Users\brian\Dev\active\Kwaksplit`. The root
`Run KWAK Split.cmd` selects `release/compact-fix5/KWAK Split/KWAK Split.exe`.
Implementation, automated release checks and verified session restoration are
complete. Direct user review is the remaining acceptance step.

## Delivered behavior

When all four stem files are available, Start/End and waveform selection stay
inside their source-time coverage. This applies to typing, numeric drag/wheel
edits, waveform selection, split completion, project/session restoration and
Undo/Redo. The minimum selection is 0.01 seconds; shorter coverage uses its entire
range. Source-only or incomplete-stem sessions retain the source-track editing
bounds and existing playback/export safety checks.

To expand coverage, choose Settings > Split Stems > Full track and click Split
Stems explicitly. Loading audio or adjusting a selection never starts separation.
Four-track WAV/MP3 export and existing effects, settings and project behavior are
retained.

## Workspace and preservation

D: writes and some cold reads stalled for minutes. With the user's approval,
work continued in an isolated C: staging area and the active project was restored
to `C:\Users\brian\Dev\active\Kwaksplit`. All **139 tracked files** from baseline
`main` / `dfb2ab5` are present with the current changes; see
`source-integration.json`. Git integrity checking passed, with dangling trees
reported but no missing or corrupt objects.

D: originals remain preserved and are the authoritative archive for historical
releases. Historical release folders and caches were **not fully copied** to C:;
the partial C: copies are not complete old releases. This report does not certify
a complete old-workspace duplicate. The seven required session files were
recovered separately from verified backups, and the new fix5 package contains its
own runtime/tools/models. Partial previous runtime/build directories remain
preserved as backups. No reset, stash, original deletion, OS setting change, push
or promotional-site change was made.

The three accepted preview HTML files remain byte-identical to their preserved
inputs. `preview-preservation.json` records their sizes and SHA-256 values. The
previous root launcher is preserved at
`backups/relocation-session-originals/Run KWAK Split.cmd`.

The C: test/build environment uses Python 3.11.9, pytest 9.1.1, Pillow 12.3.0,
PyInstaller 6.22.3 and hooks-contrib 2026.7. A fresh pinned Demucs 4.0.1 runtime
with CPU Torch/Torchaudio 2.5.1 was installed on C: and placed in
`backend/demucs_runtime`; the release uses an isolated app-local copy.
`development-runtime.json` confirms the development runtime imports and module
paths stay under that final C: runtime, with no D: or staging entries in sys.path.

## Automated source and UI verification

The complete suite recorded **192 tests passed, 1 skipped and 19 subtests passed
in 218.94 seconds**; see `pytest-full.txt`. The skipped case requires permission
to create a Windows symbolic link; system permissions were not changed. The suite includes selection bounds, restored
edits, grouped history, existing audio/workflow regressions and session-copy
preservation/failure handling.

`responsive/ui-results.json` records **11 actual Tk viewport/scaling cases** and
**15 startup work-area calculations**. The cases cover 640×480 through 4K-equivalent
geometry at 100–200% app scaling. Windows resolution and global scaling were not
changed. Where a requested viewport exceeded the physical screen, widget bounds
verified the large geometry and the capture used a visible window at the same
app scale; those captures are not physical 4K monitor tests.

`stem-export/ui-results.json` and its five captures cover 1000×700, 760×620,
640×480, Settings > Stem format and a completed four-file export. The generated
MP3 files were created successfully and no Tk callback errors were recorded.
`scripts/qa_compact.py --evidence-dir` now keeps these results separate from the
historical compact-UI evidence.

## Separate release verification

The clean fix5 package was verified before user settings/recovery were installed.
`release/release-results.json` records:

- Packaged EXE startup and shutdown: **exit 0**.
- Python/Torch/Demucs imports confined to the packaged runtime with the
  development Python path excluded and an invalid external PYTHONHOME.
- Actual bundled Demucs separation of generated source seconds 2–4 into four
  **2.000-second stems**, completing in **75.047 seconds** on this PC. This is a
  short workflow check, not a long-track or musical-quality benchmark.
- Mixed WAV/MP3, four individual WAVs and four individual MP3s. All outputs were
  **1.600 seconds at 125% speed, 48 kHz**, with pitch/EQ/fades applied; WAV was
  **24-bit PCM** and MP3 was **320 kbps**.
- Dummy-device play/pause/resume and automatic 200% DPI sizing to a 2000×1400
  client window.

EXE SHA-256:
`69c6d22ee4549a3c1afc218f02fb60c0530b91d1de1476f1bf6e2e0ab3d46322`.
`frozen-source-verification.json` confirms that the packaged application code
matches the changed `StemSamplePrep`, `backend.workspace_features` and
`backend.compact_ui` source modules.

The EXE itself received the startup smoke check. Split/export/playback workflow
checks used the real source UI with bundled engines; source matching confirms the
changed code is packaged but does not turn those checks into native EXE input
verification.

## User-session restoration

`user-data-copy.json` verifies the original settings, recovery and five working
audio files restored at their existing C: paths. The application's project reader
validated the source recovery's edits, stem coverage and all five existing audio
references before the final restore.

The explicit restore helper copied five audio files into fix5's
`temp/restored-session`, then published settings and recovery. Source files stayed
unchanged, exact source/destination JSON backups were retained, and recovery now
uses relative references to the five new audio copies. Every copy and both JSON
writes passed SHA-256 verification. See `session-migration/manifest.json`, whose
status is `applied`. Old and new workspace prefixes were both the final C: project
path; the helper did not rewrite external original-input metadata.

`restored-session-results.json` records an **isolated real-Tk restore**, without
playing, exporting or re-splitting user audio:

- All edit values and four stems restored.
- Selection remained **5.76–67.60 seconds**.
- Save folder remained
  `C:\Users\brian\Dev\active\Kwaksplit\release\compact-fix1\KWAK Split\output`.
- Export was available and the callback-error list was empty.
- All seven new session files retained their verified hashes through the check.

The restored working audio is self-contained in fix5. The Save folder deliberately
remains at the user's existing location; it can be changed in Settings.

An independent delivery audit found no blockers. It matched all five copied audio
files (**123,297,752 bytes** total) to the manifest hashes, verified the two active
JSON files and three available JSON backups, confirmed fix4's original JSON stayed
unchanged, and rechecked the three preview hashes, edits/coverage/metadata and
fix5 launcher. Active session references contain no D: paths. `git diff --check`
also passed.

[Final integrity](final-integrity.json) records **PASS**: the EXE and three changed
source modules match the frozen-source record; all five source/destination audio
pairs, two active JSON files, three JSON backups and three previews match their
recorded hashes. Root and packaged model hashes match, the launcher selects fix5,
no QA temporary folders remain, and `git diff --check` passes.

## User review and limits

Run the root launcher and press **Ctrl+Shift+R** to restore the transferred session.
Check the selection, four stems, edits and Save folder, then use Ctrl+S for a
permanent project with companion audio assets.

The computer-use runtime initialized, but listing native applications failed with
`Computer Use native pipe is unavailable: failed to connect native pipe`
(`OS error 2`). Native Windows mouse/key interaction with the new EXE was therefore
not verified. No alternate native-input bridge was built.

The remaining user checks are direct native input, music listening and separation
quality, physical monitor/DPI transitions, independent-PC execution and final
visual acceptance. Real Tk events/captures, objective audio results, dummy-device
playback and local bundled-runtime isolation are distinct from those checks.
