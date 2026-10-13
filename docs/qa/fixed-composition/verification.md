# Stable composition during audio loading — 2026-10-01

The initial regression reproduced the report: at 1000x700, showing loading
status reduced each editor panel from 465 to 417 pixels high. Smaller/shorter
windows also changed their overall fit scale because status height entered the
scale calculation.

The status area now reserves 64 logical pixels in every state. The scale depends
only on client width/height and monitor DPI, so audio, progress, success/error
text and idle-state changes leave the main composition fixed. Idle status
contents are hidden while the reserved space stays in place.

## Verified source behavior

- Four real-Tk regression cases compare scale, font size and exact header,
  waveform, EQ, mixer and effects geometry across loading, splitting, export and
  idle states. Actual audio reloads record no scale changes. Cases: 1000x700,
  640x480, 1000x420 and 480x360.
  `loading-composition-tests.txt` records the clean four-case run: 4 passed.
- Six existing resize cases retain 100–200% scaling, roundtrip spacing, edit
  preservation, Undo/Redo, progress/Cancel and simulated DPI transitions.
- One of those ten tests initially hit a system Tk library-read failure during
  root creation; that exact case passed on its isolated rerun. No layout assertion
  failed after the correction.
- `workflow-tests.txt`: 40 workflow tests passed; one setup hit the same system
  Tk read issue. `workflow-test-retry.txt` records that exact test passing alone.
  These cover loading/worker recovery, playback, error visibility, selection
  bounds and edit history.
- `ui-results.json`: thirteen actual Tk viewport/DPI cases remain side by side
  without an editor scrollbar. `captures/compact-640.png` was visually inspected.

This is a native Tk layout check; Windows display settings and the user's running
app were not changed. Package source matching, startup and saved-session results
are recorded alongside this document. The change adds no runtime dependency.

Pre-change files are preserved in `backups/2026-10-01-fixed-composition/`.
The separate compact-fix8 package preserves all earlier releases. Close the old
app, restart `Run KWAK Split.cmd`, and use Ctrl+Shift+R to restore copied work.

## Delivered package

- Build returned exit 0. `exe-smoke.json` records exit 0 with development Python
  excluded. `frozen-source-verification.json` confirms all seven shipped modules
  match the verified source; only the compact interface changed relative to fix7.
- EXE SHA-256: `e0d963e2e86468ee1601aede8a02b736c010f70d5a28a277124c9b1024617c5b`.
- `session-migration/manifest.json` records a consistent, hash-verified copy of
  the latest saved fix7 state. The running fix7 app and its files were not changed.
- `restored-session-results.json` confirms preserved source audio, edits,
  selection 0–207.456 seconds and Save folder, with no callback errors. The
  source-only session correctly keeps individual stem Export disabled.
- No audio-processing module or runtime dependency changed. Validation focused
  on the affected layout/loading/status workflows; the earlier full audio suite
  is documented separately in the fix7 evidence.
- `git diff --check` passed. Physical DPI transitions and final visual acceptance
  remain direct user checks.
