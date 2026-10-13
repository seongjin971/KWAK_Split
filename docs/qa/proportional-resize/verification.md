# Proportional editor resizing — 2026-10-01

The user's request replaces the previous narrow-window stacking and main-editor
scrolling behavior. EQ and Stem Mixer keep their side-by-side composition.
Fonts, buttons, controls, margins, borders and graphs shrink together to fit
both client dimensions, capped at the monitor's normal DPI scale. The minimum
client window is 480x360 device pixels. Settings and Advanced retain scrolling.

Scaling uses the original logical spacing measurements, so repeated resizing
does not accumulate rounding errors. Contextual status, progress and Cancel
are included in the fit. Audio edits, history, processing and project schemas
retain their existing behavior.

## UI evidence

- `ui-results.json`: thirteen actual Tk viewport cases, 480x360 through 4K
  equivalent sizes, including a short 1000x420 window and 100–200% requested DPI.
  All preserve side-by-side panels and report no editor scrollbar.
- `captures/compact-640.png` and `captures/compact-480.png` were visually
  inspected: waveform, numeric fields, EQ graph/bands, effects, four stem
  faders, Mute/Solo, Play, Split Stems and export buttons are visible.
- Larger off-monitor cases are validated by widget geometry; their captures
  use a normal window at the same DPI, as recorded in `ui-results.json`.
- `tests/test_proportional_resize.py`: six passing cases cover 100/125/150/175/200%
  DPI, repeated shrinking/growing, restored font sizes and padding, preserved
  edits and Undo/Redo, visible progress/Cancel, and simulated monitor-DPI changes.
- One initial targeted run encountered a transient failure reading the system
  Tk `scale.tcl` file during root creation. The affected test passed when rerun
  alone; this was not an application layout assertion failure.

## Package and preservation

`compact-fix7` is a separate local package; `compact-fix6` and earlier releases
remain available. The pre-change source/document backup is
`backups/2026-10-01-proportional-resize/`.

`build.txt` records completed PyInstaller packaging and verified copied runtime
imports. The outer PowerShell logging command reported `NativeCommandError`
for an informational PyInstaller stderr line; the build itself reached its
completion message. `frozen-source-verification.json` independently verifies
that all seven shipped source modules match the tested source.

No Windows resolution/scaling settings were changed. Actual Tk layout and
captures are distinct from physical monitor transitions and native OS input.

`release/release-results.json` records EXE startup/exit, isolated bundled runtime
imports, real four-stem separation, mixed WAV/MP3 and four individual files in
each format, and dummy-device play/pause/resume. Transport observation uses
50% speed to give the short generated selection four output seconds; an initial
125% observation ended before its assertion on the loaded test machine.

The current fix6 recovery was source-only, unlike the previous delivery's
four-stem snapshot. `session-migration/manifest.json` records a hash-verified
copy of this latest state into fix7, without changing fix6. The restore helper
now permits an empty stem set only with `--allow-source-only`; partial stems
remain rejected. `session-restore-tests.txt` records 22 passed and 1 skipped.
`restored-session-results.json` confirms unchanged source/settings hashes,
preserved edits, source selection 0–207.456 seconds and the existing Save folder.
Individual stem Export correctly stays disabled until the source is separated.

An initial unqualified pytest invocation collected bundled third-party library
tests; `pytest-root-collection.txt` preserves that collection failure. The app's
regression suite is explicitly scoped to `tests/` in `pytest-full.txt`.
It passed **214 tests and 22 subtests, with 1 Windows symlink-permission skip**
in 378.77 seconds. The subsequently added source-only restore cases are included
in the separate 22-pass session-restore run. `git diff --check` passed.

The root `Run KWAK Split.cmd` selects compact-fix7. Close the previous app and
start that launcher; Ctrl+Shift+R restores the copied latest session. Physical
monitor transitions and final visual readability remain direct user checks.
