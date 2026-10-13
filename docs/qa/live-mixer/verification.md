# Continuous stem mixer verification

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix14.

Stem faders, Mute, Solo and Ctrl+click resets update the existing playback.
Muted/zero-gain inputs continue decoding at the same position. All mix weights
are sent together with a short linear-gain ramp, using the existing EQ command
worker. Playback can start or continue with every track silent. Export retains
its existing track-selection rules. See [implementation](../../live-eq.md).

## Scoped source checks

- [EQ regression](eq-regression.txt): 29 passed.
- [Multi-stem PCM](audio-tests.txt): seven passed. Four independent tones verify
  gain/Mute/Solo levels against export, initial silence, return from silence,
  rapid latest-value updates, concurrent EQ bank changes, half-speed/pitch,
  identity validation and cleanup. Exchanging Solo between identical tracks
  kept constant PCM amplitude with no intermediate doubled/dropped level.
- [Alignment and cleanup](cleanup-alignment.txt): both passed. Opposite chirps
  cancel after unmuting, proving that initially silent inputs stay aligned.
- [Tk interaction](ui-tests.txt), [rerun](ui-rerun.txt) and the cleanup check:
  all 13 unique cases passed, including held fader updates, reset, all-muted
  start, Mute-over-Solo precedence, pause cancellation and failure fallback.
  The first silence assertion used a value below the analyzer's -90 dB floor;
  the corrected check uses that floor. Two Tcl setup errors passed in reruns.
- [Related regression](regression.txt): 100 passed and six subtests passed.
  Two Tcl setup cases passed separately: [effect builder](regression-source-builder-rerun.txt)
  and [pause/resume](regression-pause-resume-rerun.txt). Coverage includes fade
  precision, playback, exports, fader history/reset, stem offsets and selection.
- [Real Tk captures](ui/ui-results.json): all four held faders and all eight
  fader/readout Ctrl+click targets, Mute/Solo buttons and silent transport passed.
  Captures were visually checked for controls, status and graph layout.
- [Source runtime self-check](source-self-check-corrected.json): actual local
  EQ/mixer commands, gain/filter/slope changes and seven mixer states, including
  all-zero weights, preserved PIDs and closed every worker/process. The initial
  [self-check](source-self-check.json) used the incorrect silence floor and is
  retained with its timeout; the final check imports the analyzer constant.

Total: **152 unique test cases and six subtests passed across scoped runs**.
The initial Tk/regression runs did not have clean exits; their setup failures
and corrective reruns are recorded above. The product code needed no change
for Tcl setup failures.

Generated PCM and SDL dummy output were used. These checks do not establish
physical audio-device latency or subjective listening acceptance. Existing
buffering/Rubber Band lookahead can delay the audible response; tempo/pitch,
fades, limiter and source/range changes still use their existing restart path.

## Package and preserved session

The separate [fix14 build](build.txt) passed app-local runtime imports. Its
[frozen self-check](frozen-self-check.json) passed gain/filter/slope changes and
seven mixer states, including all-zero weights and unmuting, with unchanged PIDs
and clean worker/process shutdown. Measured mixer levels reached the expected
0.2 dB acceptance band. [Startup/exit](release-smoke.json) passed with development
Python excluded. [All 11 frozen modules](frozen-source-verification.json) match
the tested source.

EXE SHA-256: `8c744a9ac9c482a501d8bf91831fc302c83c8905ea1ef8efa9c10b46b4a3eb99`.

The latest fix13 session was [copied with five matching audio hashes](session-migration/manifest.json).
[Isolated restore](session-restore-qa/restored-session-results.json) retained
edits, four stems, selection 0–207.456 seconds and the existing Save folder.
The previous release and original session/audio remain unchanged.

`Run KWAK Split.cmd` now selects fix14. Use Ctrl+Shift+R to restore the transferred
session after launching the new version.
