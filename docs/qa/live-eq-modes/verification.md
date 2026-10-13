# Continuous EQ mode and slope verification

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix13.

Filter kinds, pass enable/disable and 12/24/36/48 dB/oct slope changes retain
the running decoder/player. The inactive EQ bank is configured before an
atomic pair of crossfade weights transfers playback. Frequency/gain/Q edits
then target whichever bank is active. See [implementation](../../live-eq.md).

## Audio and UI

- [Audio checks](audio-tests-corrected.txt): 28 passed. Actual FFmpeg commands
  cover kinds/slopes in both directions, enabled/disabled passes, rapid changes,
  final export levels, continued clocks/processes, bounded transition peaks,
  gain/frequency/Q, half-speed/pitch combinations and worker/process cleanup.
- [Tk checks](ui-tests.txt): nine passed, including actual combobox selection,
  slope knob wheel events and Ctrl+click reset on both pass bands while playing.
- [Related regression](regression.txt): 82 passed and three subtests passed.
  One Tk interpreter setup failed to read the existing `init.tcl`; that exact
  case [passed in isolation](regression-tcl-rerun.txt). All 83 cases passed across
  these runs, including parameter edits after switching to either EQ bank,
  spectrum, playback, fade precision, export, curves, numeric gestures and Undo.
- [Real Tk captures](ui/ui-results.json): held graph drag, graph reset, pass
  cutoff, both mode menus/all slopes/Ctrl reset, and a four-stem EQ update passed.
  The windows were visually checked for graph/knob values and layout.
- [Source self-check](source-self-check.json): gain and 12 mode/slope updates
  reached the expected generated-tone export levels with unchanged PIDs and
  continued clock progress. All audio/control workers closed.

Total: 120 passing test cases and three subtests across the scoped runs. The
first mode test run exposed an unquoted ZMQ command argument: only one `amix`
weight was parsed. The corrected run passes the actual PCM checks; the initial
[failure log](audio-tests.txt) is retained. No product code changed for the Tk
setup rerun.

These are generated audio, generated Tk events and SDL dummy-device checks.
Physical sound-card latency and subjective listening are not measured. Tempo,
pitch, mixer and other non-EQ edits retain their existing restart behavior;
Rubber Band lookahead can delay an EQ response without stopping the player.

A stricter exploratory 0.98–1.02 clock-ratio check did not pass on the dummy
device (0.937). The follow-up [constant-setting/mode comparison](clock-comparison.json)
measured 0.921–0.947 in both cases. A [static-filter baseline](clock-baseline.json)
also measured 0.942 versus 0.955 for the dual bank, so the tighter threshold is
not a reliable acceptance criterion for this local silent device. Neither test
reported a control error or stopped process. The package check retains the
existing 0.9–1.1 bound; these figures do not establish physical-device timing.

## Package and session

The separate [fix13 build](build.txt) completed with app-local runtime imports
verified. Its [frozen self-check](frozen-self-check.json) measured gain changes
and all 12 kind/slope updates against generated-tone export levels, retaining
the same decoder/player PIDs and closing every audio/control worker. The final
gain error was below 0.004 dB and mode checks reached the 0.2 dB acceptance band.
[Startup/exit](release-smoke.json) passed with development Python excluded;
[all 11 frozen modules](frozen-source-verification.json) match the tested source.

EXE SHA-256: `e0f3569890e2b881124e9ca3a7d86fb87bd7012feb95cb8ef2e6dd70f81cb8a7`.

The latest saved fix12 session was [copied with matching audio hashes](session-migration/manifest.json).
[Isolated restore](session-restore-qa/restored-session-results.json) preserved
edits, four stems, selection 0–207.456 seconds and the existing Save folder.
All user-session hashes remained unchanged during verification. The previous
compact-fix12 release is retained.

The root `Run KWAK Split.cmd` now selects fix13. Use Ctrl+Shift+R to resume the
transferred session after launching it.
