# Resize optimization stop checkpoint

Date: 2026-10-02 (Asia/Seoul)

Status: `PAUSED_BY_USER`. User instruction: "안전지점에서 종료해".
No further implementation, dependency installation, build, session migration or
launcher change is authorized by this stop checkpoint. Resume when requested.

## Current runnable delivery

- `Run KWAK Split.cmd` still selects `release/compact-fix18/KWAK Split`.
- compact-fix19 does not exist. No resize optimization has been packaged.
- Existing dirty work, old releases and user audio are preserved.
- No task-owned Python, FFmpeg, application or build process was found at stop.
- `stop-checkpoint.json` records source hashes, syntax-only results and the
  comparison against the four files in `preserved-session-before.json`.

## Saved work and evidence

Baseline native SetWindowPos measurements with loaded generated audio took
roughly 580 ms per resize step (flat EQ) and 590 ms (active EQ), with duplicate
waveform/EQ draws. Partial geometry and repaint batching reduced these medians
to roughly 342/335 ms, still insufficient for smooth continuous resizing.
These are generated window-size events, not physical mouse measurements.
See `before.json`, `batched.json` and their profiles.

Source edits remain uncommitted:

- `backend/compact_widgets.py`: coalesce canvas redraws and let the viewport
  use the intended client size while fitting content.
- `backend/compact_ui.py`: cache layout/style/font/metadata work and batch
  final geometry. The latest change nests the editor inside a surface frame.
- `StemSamplePrep.py`: coalesce waveform resize draws at idle.
- `backend/window_bounds.py`: track native move/size entry, resizing and exit.
- `backend/resize_preview.py`: NEW, UNVERIFIED prototype captures the editor
  surface, scales its image during border dragging, then restores real widgets.
- `requirements-runtime.txt`: Pillow requirement added, not installed into the
  build environment; license/dependency packaging work is still pending.
- `scripts/qa_resize_latency.py`: repeatable source benchmark. Currently tests
  ordinary programmatic resizing, not the new interactive preview route.

`before-source/` contains the pre-optimization copies of StemSamplePrep,
compact_ui, compact_widgets and window_bounds. Do not replace unrelated dirty
files or discard earlier feature work.

## Validation boundary and next starting point

The newest preview/surface patch has not been run. Syntax checks alone do not
establish its behavior. There has been no regression run, screenshot review,
playback continuity check or packaged validation for this implementation.
Development launch uses this unfinished source; the normal root launcher uses
the retained fix18 executable.

On an explicit resume, first test an isolated generated-audio window: confirm
that capturing a child HWND includes the entire editor, preview resize/exit
restores visible controls, pending callbacks clean up, and audio continues.
Measure first-frame capture and final reflow separately from preview frames.
Then verify FHD/QHD/4K, DPI, ratio/bounds, header status and editor behavior
before deciding whether to keep the prototype and package fix19.

Do not send synthetic WM_ENTERSIZEMOVE/WM_EXITSIZEMOVE messages directly to Tk
outside its actual native modal loop. That invalid harness crashed a test
process; details are retained in `synthetic-modal-message-error.txt`. A safe
isolated simulation can set the cached flags directly, with the limitation
documented. No physical native gesture has been validated.

The WM_SETREDRAW experiment was rejected: the seemingly fast path left the
Tk window unmapped and geometry stale. Its diagnostic artifacts are retained;
the product does not use it. Do not reuse those timings as an improvement.
