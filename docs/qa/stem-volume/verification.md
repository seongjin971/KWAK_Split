# Stem volume preservation

Date: 2026-10-13. Delivery: compact-fix29, ready for direct user review.
Scope: remove automatic per-stem attenuation during separation.

## Agreed scope

Use the existing htdemucs model, shifts=1, overlap=0.25 and CPU jobs policy.
Save raw model outputs as IEEE float32 WAV, without Demucs peak rescaling or
integer-WAV clipping. Preserve Selection/Full track timing, cache coverage,
playback/export effects and the existing Limiter. Selection context, optimization
and broader stabilization are deferred by the user. Existing releases and their
audio remain unchanged; no commit or push is included.

## Implementation and validation plan

- Run a standalone app-owned script with the selected Python runtime and `-I -B`.
  Keep the existing process cancellation, progress, environment and error path.
  Executable-only external Demucs fallback remains compatible and logs its
  original output-level behavior.
- Package the runner as a real file and verify its hash alongside the frozen
  separation module.
- Verify float WAV decoding above unity, actual model gain preservation, timing,
  playback and WAV/MP3 output with the existing Limiter.
- Run focused regressions and record the full-suite outcome separately from
  previously documented failures. Do not repair unrelated failures in this task.

## Source verification

- `focused.xml`: the initial 16 new tests passed. Covers float samples above
  unity and negative full scale, FFprobe format/rate/channel checks, exact sample
  bytes/frame counts, runtime routing, process progress/failure/cancellation,
  mixed and individual output levels, WAV/MP3 Limiter behavior and dummy playback.
- `regression.xml`: 44 passes and the already documented status-label expectation
  failure in `test_coverage_notice_tracks_scope_and_clears_for_valid_selection`.
  Selection crop/reuse and four-file WAV/MP3 exports passed. That unrelated
  expectation is unchanged.
- `runtime/runtime.json`: actual htdemucs with shifts=0 processed the same four-
  second float input at full level and 1/16 level. All stems have exactly 176400
  stereo frames at 44100 Hz and use `pcm_f32le`. Gain-equivariance error ranges
  from -81.16 to -136.52 dB. The old CLI reproduced per-stem attenuation: bass
  peak 1.71305 became 0.99005 (about 4.76 dB reduction). The new output retains
  1.71305; old outputs match the predicted rescale/int16 quantization within one
  int16 step.
- Normalization guard checks use real Torch tensors with mocked inference for
  silence, a single frame, DC and antiphase stereo. Empty/NaN inputs are rejected.
  These are not full-model pathological-input or subjective listening checks.
- Independent spec/standards reviews found one current-interpreter fallback issue:
  ordinary `find_spec` could see a package excluded by `-I`. The fallback now
  probes the isolated interpreter with a timeout and rejects a frozen app EXE.
  Two regression cases cover this correction; focused review found it resolved.

## Full-suite result

`full-suite.xml`: **412 passed, 8 failed, 2 skipped, 1 setup error and 22 subtests
passed** (436.40 seconds). All 18 new volume/routing tests passed. The eight
failures match the existing status-label/waveform cases listed in
`../lightweight-workflow/verification.md`; none were modified in this task.
The setup error is the previously observed intermittent Tcl initialization issue
in `test_initial_window_and_minimum_fit_1080p_work_area[1.5]`. It passed in a fresh
process (`tk-isolated.xml`, 1 pass). The full suite is not reported green.

## Packaged engine and real-track comparison

Built `release/compact-fix29/KWAK Split` using the verified fix28 runtime without
dependency installation or edits to third-party Demucs code. All 30 frozen
module comparisons pass, including separation. The standalone runner's source
and shipped SHA-256 hashes also match (`frozen-source-verification.json`).

`packaged-runtime/runtime.json` repeats the gain/format/guard checks using the
packaged Python and runner with only bundled FFmpeg/System32 on PATH. The real
206.31-second source identified in the original analysis was also split with the
normal shifts=1 setting. It produced 9098241 frames per stem and finished in
60.03 seconds on this machine; this is not a speed benchmark or optimization claim.

| Diagnostic | Historical output | New float output |
| --- | ---: | ---: |
| Drums peak | 0.990051 | 1.436950 |
| Drums least-squares gain needed to fit source | 1.441018 | 1.004392 |
| Other peak | 0.990051 | 1.063876 |
| Other least-squares gain | 1.091791 | 1.019084 |
| Four-stem sum residual, relative to source | -14.80 dB | -32.47 dB |

All four new fitted gains lie between 0.99865 and 1.01908. Historical/random-shift
conditions differ; these are reconstruction diagnostics, not recording ground
truth or a perceptual separation-quality score. The controlled shifts=0 gain
test establishes the storage correction independently of that comparison.

## Application integration and delivery

`packaged-ui/release-results.json` records packaged EXE startup/exit and real
source Tk UI checks using the bundled Python/Demucs/FFmpeg assets. Four selected
stems each retained the exact two-second range. Mixed WAV/MP3 and all four
individual WAV/MP3 exports passed, including rate/depth/bitrate and Speed/Pitch
effects. Dummy-device play/pause/resume passed. The GUI split was exercised in
source Tk with bundled engines, not by physical input into the frozen EXE.
Frozen module identity and actual packaged runner execution are checked separately.

The root launcher selects fix29. Filtered output preferences were copied from
fix28; no editing session or historical stems were migrated. README/project/QA
documents were copied after final verification so the package carries the final
report. `preserved-inputs.json` records hashes of the historical source/four stems
and source/fix28 Demucs audio code; final checks confirm no changes.

No subjective listening or other-PC test was performed. Float stems take about
twice the temporary disk space of int16 stems. The executable-only external CLI
fallback still uses its original level handling and is explicitly logged. No
Selection context changes, general optimization/stabilization, commit or push
are included.
