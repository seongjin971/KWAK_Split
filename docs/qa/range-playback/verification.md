# Preserve playback position during range editing

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix25.

Scope: correct endpoint drags restarting at the selected beginning. Preserve
current layout, Num Lock handling, effects/mixer and user sessions. Check the
current display only, using isolated generated audio and muted output.

## Cause and change

WaveSelection.apply cleared the manual-cursor flag, moving a paused playhead to
the selected start. The release callback also explicitly stopped playback and
started a new context preview from that beginning. The [before-fix test](before-fix-tests.xml)
reproduced a paused cursor jumping from 3 seconds to 1 second after an end drag.

Range edits now preserve the cursor. While playing, the release callback reads
the actual audio clock and uses the existing live-seek handoff with the new end
and fade bounds. The output owner/device stay open, including for four stems.
The established rule remains: when the current cursor is outside the newly
selected range, playback starts at that range's start. Paused preparation may
prepare from that start without moving the visible cursor.

## Verification

[Focused regression](focused-tests.xml): 42 passed. Tests cover both buttons,
paused cursors inside/outside the new range, source/four-stem playing end drags,
shortening/extending, unchanged owner/player, updated active end and fade bounds,
Undo/Redo, native lock states, Shift/brackets and ordinary live seeking. Existing
expectations of a cursor jump/restarted stream were updated for this request.

[Source UI](source-selection.json) passed at 2000x1400 client / 200% scale with
Num Lock enabled in generated input. No display matrix was run.

[Native input recording](native-range.json) confirms an actual endpoint drag
kept the paused cursor at 20 seconds. After Play, another native drag occurred
at about 28.24 seconds and changed the end from 50.02 to 45.06 seconds. The same
owner/player continued, advanced past 29 seconds, and ended at 45.06 seconds.
There were no callback errors. The output was muted; listening was not tested.

[Frozen current-display checks](frozen-selection.json) passed the same active
endpoint changes for source/four-stem playback with Num Lock, using generated
Tk input and muted audio. [Startup/exit](frozen-checks.json) passed with development
Python excluded. All [24 embedded modules](frozen-source-verification.json) match
source; native mouse input was verified on that source as recorded above.

[Session migration](session-migration/manifest.json) copied the latest fix24
source-only working audio with matching hashes. [Isolated restoration](session-restore/restored-session-results.json)
preserved edits, the saved 0..150.456563-second selection and Save folder without
playing or exporting user audio. The root launcher selects fix25. Earlier
files and final source/package/session/document integrity are checked in
[delivery verification](final-delivery-verification.json).
