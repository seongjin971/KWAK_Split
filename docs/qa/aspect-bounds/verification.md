# Fixed window aspect and display bounds

Date: 2026-10-01. Status: `USER_REVIEW_READY` — `compact-fix9`.

## Delivered behavior

The main editor keeps an exact **10:7 client-area aspect ratio**. The Windows
title bar and borders are outside this ratio. Dragging any edge/corner changes
both client dimensions; nominal sizes at 100% DPI are minimum **760x532**, initial
**1000x700**, maximum **1400x980**. Monitor DPI scales them, and the monitor's work
area minus actual window decorations and 12-scaled-pixel margins bounds them.
If that cannot accommodate the nominal minimum, minimum and maximum are reduced
together. Maximization centers the bounded maximum in the work area.

Fonts, controls, spacing and graphs use one scale from the 1000x700 reference.
EQ and mixer remain side by side without editor scrolling. The reserved status
space prevents audio loading/progress/errors from changing composition. Settings
and Advanced retain their own freely resizable, scrollable windows.

`backend/window_bounds.py` supplies pure geometry policy and a native hook on
only Tk's outer wrapper window. It handles Windows sizing/minmax messages without
calling Tk from the callback, and restores the original procedure on destruction.
Existing widget file-drop hooks remain separate. No audio engine change was made
for this delivery. Size limits stabilize layout and bound drawing dimensions;
they do not claim faster stem separation or rendering.

## Display and native-window evidence

`scripts/qa_window_bounds.py` passed **15 real-Tk cases**: FHD 1920x1080, QHD
2560x1440, 4K 3840x2160, each at 100/125/150/175/200% app DPI. Monitor work areas
were simulated with a 40-device-pixel taskbar reserve; decorations were measured
on the actual QA monitor. Each case checked initial/minimum/maximum client sizes,
work-area fit, exact ratio, actual maximization, unchanged edits, reachable widget
bounds and no editor scrollbar. See [display-matrix.json](display-matrix.json)
and [run output](display-matrix-run.txt).

Representative actual captures:

- [FHD at 100%](captures/fhd-100.png)
- [FHD at 200%, reduced bounds](captures/fhd-200.png)
- [QHD at 150%](captures/qhd-150.png)
- [4K at 200%](captures/4k-200.png)

Captures move the isolated QA window to a visible origin, retaining the same
client dimensions; no Windows resolution/scaling or user window is changed.
Physical monitor switching, another PC and direct native mouse input remain
device acceptance checks; the matrix is not evidence of those physical actions.

`tests/test_window_bounds.py` passed 20 work-area/DPI policies, 24 pure edge/corner
cases, programmatic axis changes, actual installed Windows sizing messages on
24 edge/size combinations, min/max messages, maximization, dialog independence,
hook cleanup and a smaller-monitor transition. Existing resize/loading tests
also checked that content/status changes do not change dimensions or UI scale.

## Regression and release

- Scoped full run: `pytest tests -q` recorded **265 passed, 1 skipped, 22 subtests
  passed**, plus one failure and one setup error. The setup error was a transient
  system-Tk library read during root creation; the failure was the existing live
  playback clock lead assertion. Both exact tests passed an isolated rerun:
  **2 passed**. Thus all 267 non-skipped checks passed across the run and rerun.
  The original failure output is preserved, not presented as a clean full-run
  exit. See [full output](test-results.txt) and [rerun](test-rerun.txt).
- Session helper validation: **24 passed, 2 skipped** (Windows symlink creation
  permission), including relative recovery references from a previously restored
  release and rejection of traversal/escape. See [session-tests.txt](session-tests.txt).
- Separate release: `release/compact-fix9/KWAK Split`. Build completed with the
  previously verified app-local runtime; development/source and earlier releases
  remain intact. [Build output](build.txt), [build stderr](build-stderr.txt).
- EXE startup and scheduled close passed with development Python unavailable in
  PATH/PYTHONHOME/PYTHONPATH; exit 0 and no callback error in its startup log.
  [Release smoke](release-smoke.json).
- Nine frozen modules match the tested source, including the new geometry module
  and compact model. [Frozen source verification](frozen-source-verification.json).

## Session preservation and use

The latest saved fix8 state contains source audio only, selection 0–207.456 seconds,
flat EQ and the existing Save folder. Its settings, recovery and original audio
were preserved; source WAV copy and JSON writes have matching SHA-256 hashes.
The helper now safely resolves source-release relative recovery audio within
its own `temp` directory, allowing consecutive release transfers without
rewriting the older manifest. Partial stem sets remain rejected.

[Transfer manifest](session-migration/manifest.json) records exact backups,
copied audio and hashes. [Isolated restoration](session-restore-qa/restored-session-results.json)
passed with edits, selection and Save folder preserved, no callback errors, no
playback/export and unchanged user-session hashes. With no separated stems in
that saved state, individual-stem Export remains disabled until splitting.

Run the root `Run KWAK Split.cmd` to select fix9. Close an earlier app first if
it is still running; press **Ctrl+Shift+R** to restore the transferred state.
Save with Ctrl+S for a permanent project. Earlier releases remain available.

Implementation references: [Tk wm](https://www.tcl-lang.org/man/tcl8.6/TkCmd/wm.htm),
[Windows WM_SIZING](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-sizing),
[MINMAXINFO](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-minmaxinfo).
