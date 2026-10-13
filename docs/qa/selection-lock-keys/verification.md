# Range dragging with lock keys enabled

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix24.

Scope: fix the reported handle drag that moves only the playhead. Keep current
layout and gestures; use isolated generated audio and the current display.

## Cause and correction

[Native input before the fix](native-before.json) records a genuine Windows
button press at the visible left handle with state 8. Hit testing correctly
returned start, but the next motion used the seek action. Selection stayed
0..12 seconds while the cursor advanced to 1.82449 seconds.

The previous Control/Alt mask included 0x08. Windows Tk uses that bit for Num
Lock and Mod2 (0x10) for Alt. The mapping is confirmed in the [official Tk Windows
key implementation](https://github.com/tcltk/tk/blob/core-8-6-branch/win/tkWinKey.c).
Control/Alt now uses 0x04|0x10 for handle selection, Shift+click and bracket
marking. Caps/Num/Scroll Lock are ignored; actual Control/Alt remain excluded.

[Native input after the fix](native-after.json) keeps the same state 8/264 and
uses handle mode: dragging the left edge changed 0..12 to 1.71..12, and the
right edge changed that to 1.71..10.38 seconds. Both changes were visible in
the waveform and Start/End fields. No callback errors. The keyboard lock state
was never changed. The user's existing app and loaded audio were not edited.

## Checks

The focused gesture suite covered 33 unique cases. Its initial run passed 30;
three new cases had an incorrect assumption that range dragging preserved a
paused playhead. Existing behavior places that playhead at the selected start.
The assertion was corrected and all three reran successfully. Initial and
corrected JUnit records are retained. Tests cover locks off, Num Lock on, all
three lock keys on, both ends, whole-range moves, click preservation, Undo/Redo,
Shift+click, brackets and actual Control/Alt exclusion.

[Source UI](source-selection.json) passed at the current 2000x1400 client / 200%
scale. Its generated events now include the observed Windows Num Lock state,
including source/four-stem continuous Shift+click and bracket playback checks.
No FHD/QHD/4K matrix was run.

[Packaged UI checks](frozen-selection.json) passed the same Num Lock gestures,
source/four-stem playback and callback checks with development Python excluded.
[Startup/exit](frozen-checks.json) passed, and all [24 embedded modules](frozen-source-verification.json)
match source. Native mouse input was verified in the source app; the package
used generated Tk input with the observed lock state. Its startup window was
inspected, but an additional native packaged drag was not performed after
foreground user activity interrupted that optional check.

[Session migration](session-migration/manifest.json) copied the latest fix23
working source audio with matching hashes. [Isolated restoration](session-restore/restored-session-results.json)
preserved edits, 0..238.956563-second selection and Save folder without playing
or exporting user audio. The root launcher selects fix24. The final hash, source,
session and document checks are in [delivery verification](final-delivery-verification.json).
The previous running app closed during delivery and rewrote settings formatting;
parsed settings values remained identical. Its executable and recovery bytes
stayed unchanged. This task did not write the previous release's settings.
