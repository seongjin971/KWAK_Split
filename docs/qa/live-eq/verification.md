# Continuous EQ preview verification

Date: 2026-10-01. Status: `USER_REVIEW_READY` — compact-fix12.

Frequency/gain/Q updates now preserve the running FFmpeg/FFplay processes,
including the first move away from 0 dB and already enabled pass-filter cutoffs.
Filter types and slopes retain the earlier graph-restart behavior.
See [implementation and limits](../../live-eq.md).

## Audio and interaction evidence

- [Audio tests](audio-tests-v4.txt): 38 passed, including real generated PCM,
  export/preview matching, Bell/Shelf/Pass frequency and Q, gain ramps, fast
  latest-value updates, tempo/pitch combinations, failure reporting and cleanup.
- [Tk tests](ui-tests-v2.txt): seven passed. EQ edits preserve the player and
  spectrum; seek/pause/loop/source changes still clean up; active-drag updates,
  stop cancellation, command failure recovery and missing-client fallback passed.
- [Real Tk captures](ui/ui-results.json): generated drag events updated EQ before
  mouse release with unchanged PIDs, graph reset returned to unity, pass cutoff
  dragging retained slope/player, and four-stem mix EQ stayed continuous.
- [Source runtime check](source-self-check.json): actual ZMQ acknowledgement,
  measured ±12 dB changes, no silent PCM blocks, bounded sample transitions and
  normal audio-clock progress with a silent SDL output device.

The full regression run recorded 284 passes, two skips, four partial-range audio
failures and two Tcl/Tk initialization errors, plus 22 passing subtests. The
audio failures exposed integer precision in retained unity EQ stages. All EQ
stages now explicitly use f64 precision. The relevant audio/precision/export
suite and both setup-error cases then passed: **82 passed** in
[precision rerun](precision-rerun.txt). Across the suite and these reruns,
**290 tests and 22 subtests passed, with two permission-related skips**. The
original [full run](regression.txt) did not have a clean exit.

Initial measurements exposed FFplay underruns with 120 ms lookahead, and different
Rubber Band output when unity EQ stages/block sizes differed. The final path uses
240 ms lookahead and matching preview/export stages. Earlier runs are retained
in this folder. Half-speed Rubber Band also needs longer to reflect an upstream
EQ edit; tests include that case instead of treating it as immediate feedback.

These are generated-audio tests, generated Tk input and silent-device measurements.
They do not establish physical output-device latency or subjective listening
acceptance.

## Final package and session

The final [build](build.txt) includes PyZMQ 27.2.0/libzmq 4.3.5 and upstream
licenses. The first draft package was preserved under `.build/release-qa/`
before rebuilding with the precision correction.

The actual frozen EXE, with development Python excluded, passed
[live commands and PCM checks](frozen-self-check.json): +11.998/-12.001 dB,
unchanged decoder/player PIDs, no silent 512-sample blocks in the test signal,
normal clock speed and clean process/worker shutdown. The displayed spectrum
settled in approximately 0.48–0.55 seconds; this includes its analysis window
and buffering and is not a physical sound-card latency measurement.
[Tk startup/exit](release-smoke.json) passed and
[all 11 frozen modules](frozen-source-verification.json) match the final source.
[Bundled-engine Tk checks](bundled-ui/ui-results.json) also passed with captures.

The latest saved fix11 session was copied into fix12 with all five audio hashes
verified. Selection 0–207.456 seconds, edits, four stems and the existing Save
folder were retained. The original release/settings/audio remain preserved.
[Transfer manifest](session-migration/manifest.json),
[isolated restore](session-restore-qa/restored-session-results.json).

The root `Run KWAK Split.cmd` now selects fix12. Restart from that launcher and
use Ctrl+Shift+R to restore the transferred session.
