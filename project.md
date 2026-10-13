# KWAK Split - final project state

Date: 2026-10-13. Status: **FINAL - compact-fix30**, accepted as the final
version by the user. `Run KWAK Split.cmd` selects that package. This cleanup does
not change application behavior or pursue further split-speed tuning.

Licensing update, 2026-10-14: the owner selected MIT for the project's original
code and chose to preserve Demucs quality while holding public executable
distribution pending model permission. The existing v1.0.0 GitHub release was
changed to draft without deleting its asset. See [license remediation](docs/license-compliance.md)
and [model evidence](LICENSES/demucs-model/PROVENANCE.md). The functional acceptance
above does not imply that third-party model redistribution is cleared.

## Product

A compact Windows audio/stem editor: open or drop audio, select a range,
play/edit/split, then export WAV or MP3. File replacement resets edits without a
project-save prompt; each launch starts empty. Output/playback preferences and
per-file Undo/Redo remain. Original audio and finished exports are preserved.

- EQ bands cover 20 to 20,000 Hz, with live EQ/mixer updates and range playback.
- Demucs uses `htdemucs`, shifts 1 and overlap 0.25. The included runtime is CPU
  based. Raw float32 stems preserve the model's levels, including peaks above
  unity; playback/export effects retain their existing behavior.
- Float waveform generation for the measured 206.31-second file improved from
  2.702 to 0.624 seconds, with exactly matching stereo peaks. This is waveform
  loading, not a claim of faster AI separation.

Usage: [README](README.txt). Design/interaction contract:
[compact UI](docs/compact-ui-implementation.md).

## Validation

[Final verification](docs/qa/stabilization/verification.md): 426 tests and 22
subtests passed; two existing Windows symlink-permission skips. Frozen file
replacement, fresh launch, header/range interactions, bundled separation and
WAV/MP3 exports passed within the documented methods. All 30 frozen modules and
the standalone runner match source. Physical listening and another PC were not
tested in that pass.

The previous completed work is checkpointed as `3a11256`. The October 14
repository update includes stabilization, the final launcher and source cleanup
for [KWAK_Split](https://github.com/seongjin971/KWAK_Split). Earlier implementation
details are retained in Git history.

## Repository and local files

Keep source, tests, build/setup/QA scripts, licenses, documentation, the approved
HTML design references and promotional site. Final QA retains a concise summary
and small machine-readable results; repeated logs, captures and source snapshots
are disposable and ignored on future runs.

The latest local package, source runtime, FFmpeg, model weights and development
Python environments remain usable and are excluded from Git. Audio/settings
from older packages were copied and hash-verified under
`backups/retained-user-data-20261013/`. Those archives are local only.

Cleanup removed the older packages, failed builds, generated caches and raw QA
files from this workspace by moving them to the Windows Recycle Bin. Only
`release/compact-fix30` remains. About 58.5 GB of old local material was recycled;
disk space is reclaimed only when those items are permanently removed from the
Recycle Bin. Existing Recycle Bin items were retained.

The preservation archive contains 98 unique files mapped to 214 original paths.
The exact target list, original-to-recycled paths and verification records are
under `backups/cleanup-20261013-195645/`. Source, final executable, settings,
licenses, model/runtime files and the three approved HTML references were kept.
