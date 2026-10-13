# Lightweight single-file workflow

Date: 2026-10-13. Delivery: compact-fix28, ready for direct user review.

## Behavior

- Open Audio, Ctrl+O and file drop replace the current audio without a project-save
  prompt. A successful load resets adjustments, selection, stems and Undo/Redo.
- A failed load preserves the current source, adjustments, stems and history.
- Opening audio during a job cancels it and loads the latest requested file after
  the job finishes. Stale worker results cannot replace the new file. Cancel can
  also dismiss a pending replacement.
- Each launch starts empty. Project open/save/recent/recovery controls, shortcuts,
  background recovery writes and Keep adjustments are removed from the app.
- Output/playback preferences and current-file Undo/Redo remain. WAV, MP3 and
  individual-stem exports remain available. Mixed exports use a temporary sibling
  file until rendering succeeds, so cancellation does not leave a partial result.
- Cleanup is limited to temporary audio owned by the current invocation. Existing
  source audio, completed exports, historical project/recovery data and old release
  folders are preserved. fix28 receives filtered output preferences only.

`backend/edit_state.py` now owns in-memory defaults, validation and Undo history.
The legacy `backend/project_store.py` format helpers remain for historical tests;
the production app does not import them and the packaged PYZ does not contain them.

## Verification

- `final-focused.xml`: five workflow cases plus crossed-pass-filter acceptance
  passed. The restart case hit intermittent Tcl initialization failure when
  creating another Tk root; it passed in a fresh process
  (`final-restart-isolated.xml`). All six workflow cases therefore passed, including
  replacing audio during an export and removing only its unfinished output.
- `final-export-and-marking.xml`: two passes. Real WAV and MP3 exports work without
  prompting and preserve existing output; the source playback/bracket-marking case
  that lost keyboard focus in the full run passed in isolation.
- `close-isolated.xml`: closing during a job cancels the child process promptly,
  creates no recovery file and preserves source audio.
- `source.json` and `frozen.json`: real Tk with generated MP3s and isolated paths
  passed replacement, reset/history, empty restart, output preference retention,
  WAV export, cleanup and preservation of an existing recovery file. Settings
  widget text and removed shortcuts were checked. Window-only captures show the
  loaded and empty states at the current 2000x1400 client size.
- `frozen-source-verification.json`: all 29 checked packaged modules match source.
  Packaged startup/exit is recorded in `smoke.json`.
- Two independent read-only reviews covered requested behavior and repository
  standards. Both identified the mixed-export cancellation issue; staging output
  fixed it. The standards reviewer rechecked the patch with no remaining findings.

## Full-suite result and limits

`full-suite.xml` records **392 passed, 10 failed, 2 skipped and 22 subtests passed**.
It ran before the last export-staging patch; the focused export and packaged QA
above exercise that final patch. The full suite was not rerun after those checks.

The ten failures were:

- Six `test_audit_audio.py` status-label/waveform cases already reproduced against
  pre-change production methods during the EQ task. See
  `../full-range-eq/baseline-existing-failures.xml`.
- `test_crossed_pass_filters_report_validation_and_recover` still expected the
  high-pass/low-pass restriction removed by the earlier EQ request. Updated to
  assert the authorized behavior; the renamed test passed in the final focused run.
- `test_coverage_notice_tracks_scope_and_clears_for_valid_selection` and
  `test_context_errors_and_progress_remain_visible_without_editor_relayout` expect
  the empty status label to be unmapped. The unchanged `HeaderStatus.display`
  deliberately keeps it painted to avoid the previously fixed white rectangle.
  Their other state assertions passed before that expectation. These two cases
  were not independently rerun on the baseline.
- `test_marking_during_playback_keeps_stream_clock_and_applies_next_play[1]`
  lost Tk keyboard focus; it passed in the fresh-process follow-up above.

The suite is not reported fully green. Tests use generated audio, Tk events and
mocked slow jobs for cancellation. Physical drag/drop, subjective listening and
additional monitors are still direct user checks. No commit or push was made.
