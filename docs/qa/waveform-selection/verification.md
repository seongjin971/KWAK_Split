# Waveform selection editing

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix20.

Approved scope: independently resize the two selection boundaries, move a
selection without changing its length, and mark start/end with `[` / `]` while
listening. Left-click/drag remains seek. Right-drag in the waveform body still
creates a new selection; the small top grip moves the existing selection.

Implementation and validation order:
1. Add scaled boundary targets, a move grip and independent bracket shortcuts.
2. Check zoom, narrow/off-screen ranges, source/stem limits, Undo/Redo, numeric
   precision, keyboard focus, and uninterrupted playback while marking.
3. Run focused regression and packaged checks; preserve the current session and
   earlier releases, then point the root launcher to the verified new build.

Baseline source copies and protected-file hashes are retained in this folder.
Tests use generated audio and isolated app data.

## Implemented behavior

- Blue boundaries have a 10 logical-pixel hit radius (at least eight device
  pixels). Right-drag adjusts only the chosen end; the opposite end stays fixed.
  Pressing near an edge does not jump it to the pointer. Ends stop before crossing.
- Right-drag the small top grip to translate the selection. Clamp the translation
  at the file or complete-stem boundary, preserving the exact selected duration.
  The remaining waveform body still draws a new range; a click or minor pointer
  jitter leaves the existing range intact. Left click/drag always remains seek.
- Drag outside the canvas to pan a zoomed timeline. Release/close cancels the
  timer. Boundaries outside the view are not shown as misleading canvas-edge
  handles; the move grip remains available on the visible selected portion.
- `[` / `]` capture the current audio-clock position as start/end. Repeated
  key-downs are ignored until release. Text inputs, dialogs, modifier chords,
  busy and empty sessions retain their existing keyboard behavior.
- Marking during playback leaves the running stream and cursor alone. The new
  range applies on the next playback, loop or export. Silent preparation no
  longer repositions a paused cursor merely because it is at the marked end.
- Each gesture/mark is one Undo action. Numeric entry still rounds to 0.01 s;
  normalization/history preserve fractional source/stem endpoints so moving a
  selection cannot change its length through repeated endpoint rounding.

## Source validation

[Regression summary](regression-summary.json): 115 unique tests and 11 subtests
passed across focused checks and corrective reruns, with no unresolved failures.
Coverage includes actual Tk gestures, wide/narrow/zoomed/off-screen targets,
move length, partial-stem bounds, history, focus guards, held keys, native source
and four-stem playback, live seek, warm transport, numerical/audio precision,
loading lifecycle, exports and proportional resizing.

The initial run found the paused cursor being changed by idle preparation; this
was fixed by making preparation's bounds query non-mutating. An empty-state
shortcut test originally deleted an audio session while a decoder was releasing
the file; it now exercises the empty-state guard directly. An older waveform
fixture moved only one pixel, so it was corrected to represent an actual drag
above the new click-jitter threshold. Initial logs remain alongside reruns.

The user's latest saved state has a point selection at 56.25 s. Restore QA now
accepts this valid zero-length session state without trying to play it. A point
selection starts a new range in either direction, instead of choosing between
two coincident resize handles. All 16 selection tests passed after this final
correction; the earlier packaged candidate and its checks are preserved.

[Source UI](source-ui.json) passed 45 minimum/initial/maximum size combinations:
FHD/QHD/4K at 100/125/150/175/200% app DPI. Each case checked boundary hit targets,
range translation, exact duration, Undo/Redo and no-scroll 10:7 layout. Screen
work areas and app DPI were simulated; Windows display settings were unchanged.
The [initial](source-ui-initial.png) and [minimum](source-ui-minimum.png) captures
were visually inspected. Source and four-stem marking both kept the same native
audio stream advancing past the marked end and used the range on the next Play.

## Build

[Build](build-result.json) completed using the preserved fix19 Demucs runtime.
An initial shell wrapper treated PyInstaller's normal stderr log as an error;
its incomplete package was preserved under `.build/release-qa/compact-fix20-build-incomplete`.
The successful build uses direct subprocess log files. [Frozen comparison](frozen-source-verification.json)
matches all 23 checked modules to source.

## Final package and session

[Final executable checks](frozen-checks.json) identify the exact EXE SHA-256 for
each successful run. [Packaged selection UI](frozen-ui.json) passed all 45 display
cases, both directions from a saved point, and source/four-stem continuous
marking with correct next-play bounds. [Space transport](frozen-transport.json),
[native resizing](frozen-resize.json), and startup/exit also passed with external
Python and its search paths excluded. Captures of initial/minimum windows were
visually inspected. The early candidate's checks remain in `initial-package/`.

[Final session migration](session-migration-final/manifest.json) copied the latest
fix19 source-only session with a matching audio hash. [Isolated restoration](session-restore-final/restored-session-results.json)
retained edits, the 56.25 s point selection, and the existing Save folder, without
playing/exporting user audio. The range stays a point until the user selects a
region; this preserves the saved state rather than changing their edit.

The root launcher now selects fix20. [Final delivery verification](final-delivery-verification.json)
records source/package matching, protected file and audio hashes, documentation
sync and launcher target. No physical mouse/keyboard, speaker listening, physical
monitor switch or external-PC result is claimed.
