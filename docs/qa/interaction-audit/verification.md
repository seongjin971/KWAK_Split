# Keyboard and independent interaction audit — 2026-09-17

Baseline: `de1f07b`. The user requested removal of persistent mouse-button focus/Space activation and an independent subagent audit. Three agents independently inspected lifecycle, audio playback/export, and editing/settings. The parent applied the production corrections; each agent then reviewed and reran its own regressions.

## Corrected behavior

| Reproduction | Correction |
| --- | --- |
| Click Open Audio, then Space reopens it instead of playing. | Mouse clicks return focus to the editor and leave no blue button outline. Space controls transport; keyboard-focused buttons still support Enter. Numeric inputs and dialogs retain their own keys. |
| Click the waveform after editing a number; Space remains suppressed by the entry focus. | Seeking and right-drag selection transfer focus to the waveform. |
| Cancel occurs between child-process creation and registration. | Registration publishes the child before checking Cancel/Close, so either event ordering terminates the owned child. |
| A project relink rejects a non-audio file; the next ordinary load inherits the abandoned project's name/EQ. | A rejected load reports that it did not start; pending project state is cleared. |
| Right-drag a new range during playback; old audio keeps playing. | Release restarts playback from the new range. Empty or uncovered stem ranges stop playback and show a corrective message. |
| A fader track click followed by a drag creates an intermediate Undo state. | An initial snapshot runs before Tk's widget mutation, grouping the complete drag into one Undo step. |
| Enter Q=999 in Advanced and close; the invalid value becomes hidden. | The dialog shows its allowed range and remains editable until corrected. Closing the main application still exits immediately. |
| HP=2000 Hz and LP=1000 Hz throws from the EQ draw callback. | Validation appears in context without a callback exception. Frequency handles remain reachable; correcting the range restores the curve and clears that error. |
| Ordinary playback/completion opens a duplicate status row. | Play/Pause communicates transport state; errors and export results remain visible. |

## Independent verification

- Lifecycle: `tests/test_audit_lifecycle.py`, **5 passed**. Includes cancellation ordering, rejected relink, corrupt project audio, cancelled conversion, and successful loading after worker failure.
- Audio: `tests/test_audit_audio.py`, **10 passed**. Includes no automatic split, source-coordinate pause/resume at changed speed, real WAV export consistency, stem coverage, selection changes during playback, and contextual status visibility.
- Editing: `tests/test_audit_edits.py`, **5 passed**. Includes real Tk click/drag Undo/Redo, invalid Q correction and successful dialog close, crossed-filter recovery, save-folder validation, and resizing with retained edits.
- Parent keyboard regressions: `tests/test_compact_keyboard.py`, **5 passed**. Dispatches actual Tk mouse/key events through widget bindings, covering clicked buttons, keyboard-focused buttons, waveform focus, numeric input and dialogs.
- Existing bounded audio suite: **47 passed and 6 subtests passed**, including FFmpeg/FFplay using a silent playback device.

Each reported failure was reproduced before its correction. Fixtures use generated audio in isolated temporary folders. Prior release folders, settings, source audio, saved projects, HTML references and historical QA evidence are preserved.

## Release verification

Full regression command:

`.build\qa\Scripts\python.exe -X utf8 -B -m pytest tests -q --capture=sys -p no:cacheprovider`

**108 passed and 19 subtests passed in 155.46 seconds.** `git diff --check` passed.

A separate `compact-fix2` build preserves the prior packages. Packaged-engine checks use the new `--evidence-dir` option in `scripts/qa_compact_release.py` to avoid replacing historical evidence.

`release-results.json` records successful packaged EXE startup/exit, app-local Python imports, real four-stem separation and 48 kHz/24-bit WAV plus 320 kbps MP3 exports. A selected 2-second source range becomes 1.6 seconds at 125% speed; pitch/EQ/fades and dummy-device play/pause/resume also passed. Actual automatic DPI detection selected 200% and a 2000×1400 client window. The generated-audio capture is in `captures/automatic-dpi.png`.

Computer Use verified the newly built EXE with native Windows input: restore the existing session, click Open Audio, cancel its file chooser, press Space to play, and press Space again to pause. The file chooser did not reopen, Open Audio retained no blue focus outline, Play/Pause changed together with the transport icon, and routine playback did not expose a redundant status row. The Advanced dialog was visually inspected and closed with Done. The original window was closed normally; its settings and recovery snapshot were copied into the new package, with matching recovery hashes before restore. The updated app was left open with the original audio/edits restored and playback paused. No display resolution or window size was changed during these native checks.

EXE SHA-256: `63082165a858489d3bebe1ec96d4028e3412e7a9e4418405d0fc97ffdcfa4a70`.
The root `Run KWAK Split.cmd` selects `release/compact-fix2/KWAK Split/KWAK Split.exe`. Earlier packages and the previous Save folder remain intact. No push was made.

Local automated checks, native Windows input and silent playback checks do not constitute direct listening or physical laptop/monitor acceptance.
