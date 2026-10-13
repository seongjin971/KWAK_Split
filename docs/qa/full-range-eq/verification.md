# Full-range EQ bands

Date: 2026-10-13. Delivery: compact-fix27, ready for direct user review.

## Change

All three frequency controls, graph handles and arrow-key edits span 20–20,000 Hz.
Removed the application error that rejected High Pass at or above Low Pass.
Crossed pass filters are valid but can strongly attenuate sound. Gain remains
±24 dB; slope, Q and reset defaults are unchanged. The processing engine already
accepted the shared frequency range, so its DSP implementation did not change.

## Verification

- `pytest.xml`: 35 live-EQ audio cases passed, including both frequency endpoints,
  crossed 48 dB/oct pass filters, live/export PCM agreement and live changes beyond
  the old per-band limits. The numeric suite in this run had 14 passes and one
  intermittent Tk initialization error.
- `full-range-final.xml`: the final real-Tk full-range regression passed. It checks
  numeric entry and graph dragging to both ends for each band, arrow-key bounds,
  project save/open, and building audio effects with crossed pass frequencies.
- `ctrl-reset-isolated.xml`: the reset case affected by a later Tk setup failure
  passed in its own process.
- `frozen-numeric-reset.json`: all seven fields passed generated-input reset,
  Undo/Redo and held-gesture checks at the current 2000x1400 / 200% display.
- Frozen `--smoke-test` exited with code 0.
- `frozen-source-verification.json`: all 26 packaged modules match source.
- `session-migration/manifest.json` and `session-restore/restored-session-results.json`:
  copied the fix26 session into fix27 and verified its original audio, four stems,
  edits, 0–207.456-second range and Save folder. Isolated restore caused no callback
  errors and left the session/audio hashes unchanged. Original fix26 files remain.

## Existing failures and limits

The broader `pytest-ui-final.xml` run had 18 passes, six failures and one Tk setup
error. All six failures reproduced after restoring both changed production methods
from HEAD in memory (`baseline-existing-failures.xml`): three obsolete hidden-label
expectations and three waveform-selection expectations. These are outside this EQ
change and were not modified. The earlier numeric text-entry test also failed its
isolated rerun with `0.04.00` instead of `0.04` (`isolated-1.xml`), after failing to
initialize Tcl in the first batch. The full suite is therefore not reported green.

These checks use generated audio and Tk events. Physical input, subjective listening
and additional display sizes were not verified in this task. No automatic commit or
push was made. The launcher selects fix27; Ctrl+Shift+R restores the copied session.
