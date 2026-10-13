# Trackpad waveform selection

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix21.

Approved: ordinary click followed by Shift+click selects a range; left-drag the
blue boundaries/top grip to resize/move. Retain left-drag seeking in the waveform
body and all right-button selection gestures.

Order: implement and document gesture routing; check real Tk input, anchors,
history, stem limits, zoom/pan and playback; build a separate fix21, verify its
embedded code/UI, preserve the current session and update the root launcher.

Baseline code and protected fix20 hashes are saved here. Tests use isolated
settings and generated audio. Physical trackpad feel remains a user check.

## Behavior

- Click, then Shift+click selects between the two source-time positions. Repeated
  Shift+clicks retain the original seek point across zooming and playback. A new
  ordinary click/body seek drag replaces it; a different audio session discards it.
  Before the first seek click, the current playhead is used.
- Left-drag a blue boundary to resize that end, or the top grip to move the range
  without changing its length. Pressing does not jump the edge. Horizontal travel
  of three logical pixels distinguishes a drag from a tap. A handle tap still seeks.
- Body seeking starts on press and remains a seek while crossing handles. Both
  mouse buttons support handle drags; right-drag in the body still selects.
- Shift+click leaves the audio stream running; the new range applies to the next
  play/loop/export. A completed handle drag retains the existing range-edit playback
  behavior. Stem coverage limits, centisecond entry, exact range length and one
  Undo per selection gesture are retained. Out-of-canvas handle drags pan zoomed views.
- Persistent instructions are in the existing closed Settings Help and tooltip.

## Source UI

[Source UI results](source-ui.json) passed 45 minimum/initial/maximum combinations
at FHD/QHD/4K and 100/125/150/175/200% app DPI. Each checks click/Shift+click, left
boundary drag, grip movement, Undo/Redo, visible handles and the no-scroll 10:7 layout.
Work areas and DPI were simulated without changing Windows display settings.
[Initial](source-ui-initial.png) and [minimum](source-ui-minimum.png) captures were
visually inspected. Source and four-stem playback retained the stream and fixed
anchor during repeated Shift+clicks; bracket marks and next-play bounds also passed.

## Regression and build

[Regression summary](regression-summary.json): 70 unique tests passed, with no
failures or skips. The first gesture/seek/keyboard run passed 38 tests; the final
range/numeric/trackpad run passed 44, including the 12 repeated trackpad cases.
Checks cover fixed/reversed anchors, zoom and different sources, handle tap/drag
distinction, no premature seeks, body seeks crossing handles, Undo/Redo, point
selections, fractional stem coverage, automatic panning and running source/stem audio.

[Build result](build-result.json): compact-fix21 was built using the preserved
fix20 Demucs runtime. [Frozen code comparison](frozen-source-verification.json)
matches all 23 checked modules to the final source. Older releases are retained.

## Final executable and session

[Packaged UI](frozen-ui.json) passed the same 45 display cases, fixed Shift+click
anchors during source/four-stem playback, bracket marking and next-play bounds.
The [initial](frozen-ui-initial.png) and [minimum](frozen-ui-minimum.png) captures
were visually inspected. [Executable checks](frozen-checks.json) record the exact
EXE hash for selection, [Space transport](frozen-transport.json) and startup/exit;
all passed with development Python excluded from the runtime search paths.

[Migration](session-migration/manifest.json) copied the latest fix20 source-only
session with matching audio hashes. [Isolated restoration](session-restore/restored-session-results.json)
preserved edits, the 0..238.956563 s full-track selection and the existing Save
folder. User audio was not played or exported, and original fix20 files are unchanged.
Use Ctrl+Shift+R in fix21 to resume the transferred session.

The root launcher now selects fix21. [Final delivery verification](final-delivery-verification.json)
records code/executable hashes, old release protection, session audio, launcher
and documentation matching. No physical trackpad, speaker listening, physical
monitor switching or external-PC result is claimed.
