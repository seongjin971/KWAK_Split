# Continuous waveform seeking verification

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix15.

Left-click and held left-drag waveform seeking keep the FFplay player open.
A separate decoder prepares audio at the new source position while the current
audio continues. A 10 ms linear PCM crossfade transfers playback. One in-flight
preparation finishes while additional requests coalesce to the latest pending
position, so rapid dragging continues to change the sound before release.
Source cursor mapping, EQ/mixer state, partial-stem offsets and selection fades
are retained. Right-drag selection and paused seeking keep their prior behavior.
See [implementation](../../live-eq.md).

## Source verification

- [Initial engine regression](engine-initial.txt): 36 passed and three subtests
  passed. An earlier local harness run needed the new drag-state field added to
  its mocked app; product initialization already supplied that field.
- [Initial UI run](seek-ui-tests.txt) found starvation during held dragging when
  every superseded preparation was discarded. The worker now finishes one
  prepared handoff, then picks the latest pending target. The [corrected run](seek-corrected-tests.txt)
  passed all 14 cases. Two unrelated Tcl setup failures from the first run are
  tracked in the regression reruns.
- [Initial source engine self-check](source-engine.json): generated multisection audio,
  four mixer inputs, forward/backward positions at 0.5x/1x/2x speed with pitch,
  export-level agreement, continuous player clocks and clean shutdown passed.
- [Final real Tk gesture evidence](ui-final/ui-checks.json): clicks and held left drags,
  four-stem Solo/gain plus EQ retention, paused seeking and cleanup passed.
  These are generated Tk events on the actual source UI, not OS mouse input
  against the frozen EXE. Captures were visually inspected.

- [Related regression](regression.txt): 175 passed and six subtests passed,
  with two failures and two Tcl setup errors. Coverage includes playback,
  EQ/mixer, selection/stem bounds, numeric gestures, fades, WAV/MP3 export,
  undo and existing interaction behavior.
- The first failure exposed coarse live-EQ pacing after collecting larger PCM
  blocks. Ordinary relay pacing now uses 256-frame blocks; only seeks collect
  a longer crossfade window. The [stream regression](stream-regression.txt)
  passed all 29 EQ, eight mixer, spectrum and playback cases; its remaining
  seek assertion was corrected as described next.
- The second failure compared a pitch-shifted low tone with an unrelated FFT
  window. [Diagnosis](pitch-reference-diagnostic.json) showed exact agreement
  with export at each matching sample position, while amplitudes varied across
  windows. The seek checks now compare that exact output window at the same
  0.3 dB tolerance. [All 12 final seek cases](seek-final.txt) passed, including
  offsets, sample alignment, selection fades, discontinuity smoothing,
  preparation timeout/failure recovery, near-end movement and cancellation.
- [Final UI reruns](ui-final.txt): all four passed, including the two Tcl setup
  cases and releasing pending EQ/mixer edits after a held seek. The shared
  fixture now releases patches/temp data even when Tcl setup fails.

[Aggregate](regression-summary.json): **179 unique tests and six subtests passed
across runs**, with no unresolved case. This is not a claim of a clean initial
full run. Earlier logs remain available above.

## Frozen package and preserved session

The [separate build](build.txt) passed app-local runtime imports.
[All 12 frozen modules](frozen-source-verification.json) match the tested source.
[Frozen seek checks](frozen-seek.json) passed 12 forward/backward handoffs at
0.5x/1x/2x and different pitches, with four mixer inputs, matching export FFT
windows, fast request bursts, concurrent EQ/mixer changes and clean shutdown.
The same player remained alive throughout each run. Output-clock response was
0.312–0.391 seconds and PCM forwarding gaps stayed below 48 ms, within lookahead.
[Frozen EQ/mixer checks](frozen-eq-mixer.json) passed gain/filter/slope and
Mute/Solo/gain changes. [Tk startup/exit](release-smoke.json) passed with
development Python excluded.

EXE SHA-256: `a98ed76db132a7e35ead86c54bfb0cfb846bf740a167013271ca4a4683293853`.

The latest fix14 session was [copied with five verified audio hashes](session-migration/manifest.json).
[Isolated restore](session-restore-qa/restored-session-results.json) preserved
edits, four stems, selection and Save folder. The prior EXE, settings, recovery
and five audio files retain their recorded hashes. The root launcher selects
fix15; fix14 remains available. Ctrl+Shift+R restores the transferred session.

Generated PCM and SDL dummy playback do not measure physical audio-device
latency or provide human listening acceptance. The existing 240 ms lookahead,
decoder preparation and device buffering still contribute delay. Native EXE
startup/self-checks and generated source-Tk gestures were verified separately.
