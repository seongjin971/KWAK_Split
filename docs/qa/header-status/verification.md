# Text status beside the logo

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix18.

The space between KWAK Split and Open Audio now holds one line of task text,
with the reported percentage when known and a small Cancel button while busy.
The frame has a fixed requested height/width and absorbs available header space;
text is shortened by measured font width, preserving the percentage suffix.
The header and action buttons do not move as status changes. Idle status is blank.
No progress-bar widget is constructed in the compact UI and the lower 64-unit
reservation is removed. EQ/mixer fill the recovered height at the same 10:7
window ratio, with only their normal outer margin left below them.

Saved-file text opens the output folder. Clicking other messages opens the
complete original text; hover also exposes it. Worker errors now retain the
original error payload, and their busy animation stops before showing the
existing error dialog so it cannot overwrite the error during the modal loop.
Cancellation retains the existing worker/process mechanism. Audio processing
and export encoding remain unchanged.

## Source checks

[Display and action check](source-header.json): 45 combinations across FHD/QHD/4K,
100%, 125%, 150%, 175%, 200% app DPI, and initial/minimum/maximum sizes. Each
combination checks idle, indeterminate work, known progress, cancellation, save
completion and error. Assertions cover stable header/editor bounds, no scrolling,
no progress bar, readable progress suffix, reachable Cancel, correct saved-folder
action, complete error detail and preserved edits. Generated audio was actually
loaded and exported to an isolated temporary folder. No user audio was exported.

The test uses real Tk windows with simulated monitor work areas/app DPI; Windows
display settings were not changed and physical monitor switching was not tested.
Normal and minimum captures were inspected for the reclaimed lower space and
status text, including [idle](captures/idle-initial.png),
[progress](captures/progress-minimum.png) and [error](captures/error-minimum.png).

[Focused regression](focused-tests.txt) covered loading, cancellation, worker
errors, real playback and retained resume, exports, shortcuts, state/history and
proportional layout. The initial run had 52 passes, one failure and one setup
error; both were Tcl initialization failures before the app could start.
[Resize rerun](isolated-resize.txt) and [audio rerun](isolated-audio.txt) passed
in isolated processes. The combined result is 54 unique tests and 11 subtests
passed, with no unresolved failures.

## Package and session

[Frozen-source comparison](frozen-source-verification.json) verifies all 18
shipped modules match the checked source. [Isolated executable checks](release-smoke.json)
passed with development Python and its search paths excluded: the same
[45 header cases](frozen-header.json), [Space transport](frozen-transport.json)
and startup/exit. The transport check used generated Tk events and muted native
output, retaining the same device/decoder across pauses and freezing the paused
clock. Physical keyboard-to-speaker latency and listening were not measured.

The [build](build-result.json) returned exit code 0, including verification of
the copied app-local Demucs runtime imports. No dependency was added.

The latest saved fix17 session contains one working source WAV and no stems.
[Migration](session-migration/manifest.json) copied that current session with a
matching SHA-256, preserving the prior release. [Isolated restoration](session-restore-qa/restored-session-results.json)
confirmed edits, selection and Save folder without playing/exporting user audio
or changing its files. The root launcher selects fix18. [Final delivery checks](final-delivery-verification.json)
record the executable/source hashes, previous-release preservation, restored
session, documentation sync and launcher target.
