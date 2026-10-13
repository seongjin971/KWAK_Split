# Simple waveform handles and README help

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix22.

Approved scope: make the two range boundaries easier to grab and dedicated to
range editing; use an ordinary pointer over the waveform; remove hover help and
collect instructions in README. Check the current display only. Do not expand
or run the FHD/QHD/4K display matrix for this change.

Order: preserve the fix21 baseline, simplify interactions and help, check focused
gestures and the current-size UI, then deliver a separate executable retaining
the latest session and earlier release. QA uses isolated settings/generated audio.

## Changes

- The crosshair was an explicitly assigned selection cursor. Normal waveform
  hover now uses an arrow; endpoints use a horizontal resize cursor and the move
  grip keeps its hand cursor. Body seeking keeps the arrow while crossing an end.
- End handles grew from 6x14 to 16x36 logical pixels, with wider hit targets and
  visible grip strokes. At full-track bounds the complete handle stays on canvas.
  Plain handle clicks and tiny movement preserve both selection and playhead;
  dragging adjusts the range with one Undo action. Other range shortcuts remain.
- Removed ToolTip, all creation/binding/cleanup sites, and the status tooltip.
  README contains the instructions; Settings opens it through the system text
  viewer and retains Environment Check. Status details/errors remain clickable.
- Current-display QA exposed a Tk distance value for label padding after using
  Settings. Header fitting now uses Tk's pixel conversion instead of Python int,
  avoiding a callback failure when task status changes.

## Source UI

[Current-display QA](source-ui.json) passed at the actual initial 2000x1400 client
size and 200% display scale. No display matrix was run. Generated Tk input checked
both full-track edge handles, cursor changes, no seek on handle clicks, drag and
Undo/Redo, README activation, status details, and no popup after hovering 116 main
and 41 settings widgets for longer than the former tooltip delay.

Source and four-stem native muted playback still pass continuous Shift+click
and bracket marking, with correct next-play bounds. [Editor](source-ui-current.png)
and [Settings](source-ui-settings.png) screenshots were visually inspected.

Initial failed QA records are retained. The first used an internal playhead
setter without marking a user seek; it now uses an actual body click. The next
exposed the header padding conversion fixed above. The final run has no callback errors.

## Regression, package and session

[Focused regression](regression-summary.json) passed 39 tests with no skips:
trackpad/range gestures, live seeking, keyboard focus/transport and English UI.
Existing tap tests now require the selection and cursor to stay unchanged.

[Build](build-result.json) completed using the preserved fix21 local runtime.
[Frozen source verification](frozen-source-verification.json) matches 24 modules,
including ui_helpers after removal of ToolTip. A final trailing-blank-line cleanup
left bytecode unchanged; the comparison was refreshed after that formatting edit.

[Final executable checks](frozen-checks.json) identify the exact executable hash.
[Current-display UI](frozen-ui.json), [transport](frozen-transport.json) and
startup/exit passed with development Python excluded. The packaged [editor](frozen-ui-current.png)
and [Settings](frozen-ui-settings.png) captures were visually inspected. UI scope
remains the actual initial window only; no FHD/QHD/4K matrix was run.

[Session migration](session-migration/manifest.json) copied the latest fix21
source-only audio with matching hashes. [Isolated restore](session-restore/restored-session-results.json)
preserved edits, the 0..238.956563 s selection and Save folder, without playing or
exporting user audio. Ctrl+Shift+R restores this session in fix22.

The root launcher selects fix22. [Final delivery verification](final-delivery-verification.json)
records preserved old release files, matching source/package code and documents,
and session checks. Physical input, listening and other-display/PC acceptance
remain unmeasured.
