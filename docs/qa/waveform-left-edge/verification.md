# Waveform beginning visibility

Date: 2026-10-01. Status: `USER_REVIEW_READY` — `compact-fix10`.

The waveform's L/R text and 22-scaled-pixel reserved left space are removed.
Both upper/lower stereo channels now draw from the visible left edge. Full-track,
zoomed and panned views retain the same source-time mapping, selection, playhead
and fades. The source change is limited to removing the text draw and changing
the waveform loop's starting x-coordinate to zero.

## Validation

- **12 real-Tk checks passed** using FFmpeg-generated stereo: minimum/reference/
  150%/200% window sizes, each with full view, beginning zoom and panned zoom.
  Verified no L/R text, both channels at x=0, visible-start/midpoint/end time
  mapping and decoded channel amplitudes including the selected fade. Edits,
  exact 10:7 ratio and no editor scrollbar were preserved; no callback errors.
  [Waveform results](waveform-results.json).
- Captures inspected: [reference](captures/reference.png),
  [beginning zoom](captures/beginning-zoom.png), [minimum](captures/minimum.png),
  [200%](captures/200-percent.png). These are isolated source-app Tk captures;
  user audio/windows and Windows display settings were not changed.
- **6 existing tests passed** for fade envelope/markers through zoom, selection
  zoom/time mapping, waveform focus/Space on either mouse button, and active
  playback selection changes including an empty selection. [Test output](test-results.txt).
- Separate fix10 package built using the verified fix9 app-local runtime.
  EXE startup and scheduled close passed without development Python (exit 0).
  [Build output](build.txt), [build stderr](build-stderr.txt),
  [EXE smoke](release-smoke.json).
- All **9 frozen modules match** the tested source.
  [Frozen verification](frozen-source-verification.json).

The previous full-suite and FHD/QHD/4K aspect/bounds evidence remains in
[aspect-bounds](../aspect-bounds/verification.md). This delivery changes only
waveform label/left-origin drawing; it did not repeat unrelated engine tests or
claim physical monitor switching/native mouse acceptance.

## Preserved session and launch

Latest saved fix9 source-only audio, selection 0–207.456 seconds, edits and Save
folder were copied into fix10 with matching SHA-256 hashes. Older release files,
original audio and exports remain preserved. [Transfer manifest](session-migration/manifest.json).
Isolated real-Tk recovery restored edits/selection/Save folder with no callback
errors, no playback/export and unchanged user-session hashes.
[Restoration evidence](session-restore-qa/restored-session-results.json).

The root `Run KWAK Split.cmd` selects fix10. Restart using that launcher; use
**Ctrl+Shift+R** to resume the transferred session and Ctrl+S for a permanent project.
