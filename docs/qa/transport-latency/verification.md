# Space transport response verification

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix16.

## Diagnosis and change

Transport status was scheduling a complete compact layout at the next Tk idle,
including waveform and EQ redraws. Action-state refresh also redrew unchanged
controls. Stopping playback waited for an idle FFT worker's 100 ms queue timeout.

Status now uses its existing fixed-height area without requesting layout. Play
and pause update only transport; other state changes still run the full refresh.
Unchanged enabled states avoid redundant redraws. Spectrum shutdown explicitly
wakes its queue before joining. All audio processes and workers still close.
Repeated Space presses are ignored until release, and focus loss releases the
latch. Existing text-entry and dialog guards remain in effect.

## Measured response

The same [real-Tk benchmark](../../../scripts/qa_transport_latency.py) dispatched
Space press/release events and measured handler return plus completion of idle
painting. Each result is the median of six cycles using generated audio and SDL
dummy. This is UI timing, not physical keyboard-to-speaker latency.

| Measurement | Before | After, source | After, four stems |
| --- | ---: | ---: | ---: |
| Play handler | 84.6 ms | 65.0 ms | 67.1 ms |
| Play including idle paint | 251.6 ms | 67.8 ms | 72.3 ms |
| Pause handler | 114.6 ms | 7.3 ms | 6.5 ms |
| Pause including idle paint | 258.8 ms | 11.6 ms | 9.4 ms |

Evidence: [before](before.json), [after](after.json),
[four-stem mix](after-four-stems.json), [packagable source self-check](source-self-check.json).
Playback setup, decoder processing and audio-device buffering remain part of
audible startup. UI-observed first PCM and positive clock timings are included
in the JSON; they do not substitute for a physical latency measurement.

## Regression findings

The transport test exercises real playback, pause and resume with four stems,
Solo/gain and EQ. Selection and edits survive, the paused cursor resumes, spectrum
clears, and no full layout/waveform/EQ redraw is requested. Contextual errors,
progress and Cancel remain visible in the reserved status area. The idle-worker
test disables queue timeout polling and proves that close explicitly wakes it.

The initial transport assertion caught its own delayed edit-history commit.
The fixture now commits setup edits before tracing transport redraws; product
history behavior was preserved. Initial Tcl initialization failures in repeated
Tk instances passed in separate processes. Earlier logs remain available.

The audio regression exposed an existing EQ mode-transition step that sometimes
exceeded its PCM continuity bound. Isolated repetition also reproduced it;
injecting a 60 ms command delay [reproduced a 695-unit sample step](eq-delay-reproduction.txt)
against the unchanged 500-unit bound. Wall-clock progress could skip most of a
crossfade after a delayed acknowledgement. Each command now advances at most
10 percentage points; both normal and delayed cases [pass](eq-delay-corrected.txt)
without relaxing the test. Under scheduling load the crossfade can take longer
than its nominal duration, while the player remains open.

[Aggregate](regression-summary.json): **184 unique tests and three subtests
passed across the scoped runs and corrective reruns**, with no unresolved case.
This is not a claim of a clean initial full run. The final [audio regression](audio-corrected.txt)
passed all 63 tests, including delayed mode transitions. The [UI regression](regression.txt)
passed 86 cases with one Tcl setup error that [passed in isolation](regression-rerun.txt).
All [10 workflow cases](workflow.txt) passed. The initial [focused run](focused.txt)
had the setup-edit assertion and two Tcl setup errors described above; all three
passed in isolated [transport](corrected-0.txt), [status](corrected-1.txt) and
[keyboard](corrected-2.txt) checks.

## Package and session

The [separate build](build.txt) passed app-local runtime imports. All
[13 frozen modules](frozen-source-verification.json) match source. The packaged
[transport check](frozen-transport.json) passed six source and six four-stem
play/pause cycles through real generated Tk Space events, held-key behavior and
complete worker/player shutdown. Its isolated harness measured UI paint medians
of 24.2/8.9 ms for source play/pause and 25.5/9.2 ms for four stems. This is a
separate harness from the instrumented before/after comparison above.

The EXE also passed [12 continuous seek handoffs](frozen-seek.json),
[EQ/filter/slope/mixer commands](frozen-eq-mixer.json), and
[startup/exit](release-smoke.json), all with development Python excluded.
Generated PCM and SDL dummy do not provide physical-device latency or human
listening acceptance. The packaged gestures are generated Tk events, not OS
keyboard input.

EXE SHA-256: `e6ecfae06271caa50000d750cdb0566201a236a96ef0e82314fd04ca684ed179`.

The latest fix15 session was [copied with five verified audio hashes](session-migration/manifest.json).
[Isolated restoration](session-restore-qa/restored-session-results.json) preserved
edits, four stems, selection and Save folder. The prior fix15 EXE, settings,
recovery and five audio files retain their [recorded hashes](preserved-session-before.json).
The root launcher selects fix16; fix15 remains available. Ctrl+Shift+R restores
the transferred session. [Final delivery checks](delivery-verification.json)
verify source/package identity, session hashes, launcher and packaged documents.
