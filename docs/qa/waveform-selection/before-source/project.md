# KWAK Split Improvement Goals and Status

Baseline: main / 4babbf0 · Started: 2026-09-13

## Current delivery — smoother continuous resizing (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix19.** During native border dragging,
a complete in-memory picture scales through Windows drawing; release restores
sharp controls at the final size. Audio continues, while cursor/spectrum/status
visuals catch up after the drag. Duplicate layout and graph redraws are batched.
The same generated 44-step route improved from 580–590 ms median per step to
24–26 ms. Final reflow still takes a few tenths of a second; large 4K jumps cost
more than the normal-size route. Physical mouse latency was not measured.

Resize QA passed source/four-stem playback, native Enter/Escape completion,
failure fallback, resource cleanup and 15 FHD/QHD/4K DPI/bounds cases. Header QA
passed 45 sizes with six feedback states each. Focused regression and corrective
reruns passed 101 unique tests and seven subtests. All 21 frozen modules match
source; the isolated executable passed resize, header, Space transport and
startup/exit checks. The latest fix18 source-only session was copied with matching
audio hashes; isolated restore retained edits, selection and Save folder.
The launcher selects fix19; fix18 and its session remain preserved. See
[resize verification](docs/qa/smooth-resize/verification.md).

## Previous delivery — text status beside the logo (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix18.** Task text, numeric progress
and Cancel now occupy the space between the logo and Open Audio. The progress
bar and lower status reservation are removed; the 10:7 ratio stays fixed and
EQ/mixer receive the reclaimed height. Long messages shorten while percentages
stay visible. Saved-file text opens its folder; other messages expose full
details on click. Worker errors retain their original detail after completion.

Source QA passed 45 display/size combinations at FHD/QHD/4K and 100–200% app DPI,
with six status states, stable geometry, cancellation and detail/folder actions.
Focused regression plus isolated reruns passed 54 tests and 11 subtests; two
intermittent Tcl startup failures passed in fresh processes. Screenshots of
normal/minimum windows were inspected. All 18 frozen modules match source.
With development Python excluded, the EXE passed the same 45 header cases,
retained Space transport and startup/exit. The latest fix17 session contains
source audio only; it was copied with a matching audio hash, and isolated Tk
restore preserved edits, selection and Save folder. The launcher selects fix18;
fix17 is preserved. See [header status verification](docs/qa/header-status/verification.md).

## Previous delivery — prepared playback and retained pause (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix17.** The Windows output device
opens asynchronously and remains available for the app lifetime. Space pauses
its queued PCM, decoder and exact position; resume restarts the same stream.
One worker prepares idle source/mix playback and replaces obsolete prepared
audio after paused edits. An unfinished preparation can still delay playback;
the UI remains responsive and another Space cancels the pending start.

Muted real-device measurements with generated Tk events recorded median device
clock advance of 19.3 ms for source and 22.1 ms for four stems after prepared Play.
These are device-clock measurements, not physical key-to-speaker or listening
tests. Across full regression and corrective reruns, 350 unique tests and
22 subtests passed, with two skips and no unresolved failures. Complete PCM
comparisons cover retained pause at three speeds, pitch changes, EQ and four
stems. Native EQ/mixer/seek checks, paused edits, cancellation, recovery and
cleanup passed. All 16 frozen modules match source. With development Python
excluded, the EXE passed native transport/EQ/mixer/seeks, the FFplay fallback and
startup/exit. Prepared device response medians were 20.8 ms for source and
21.8 ms for four stems. The latest fix16 session was copied with all five audio
hashes verified; isolated restore retained edits, selection and Save folder.
The launcher selects fix17, and fix16 remains preserved. See
[prepared playback verification](docs/qa/warm-transport/verification.md).

## Previous delivery — Space transport response (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix16.** Play/Pause updates transport
without rebuilding waveform, EQ and editor geometry. Fixed-height status changes
no longer schedule a full layout. An explicit queue wake removes the idle FFT
worker's 100 ms shutdown wait. Space repeats are ignored until release or focus
loss; text inputs and dialogs retain their normal behavior.

Six-cycle source measurements reduced median UI paint response from 251.6 to
67.8 ms for play and 258.8 to 11.6 ms for pause. Four-stem results were 72.3 and
9.4 ms. These are generated Tk events with SDL dummy, not physical speaker latency.
Regression also exposed a scheduler-sensitive EQ mode crossfade; its weight
advance is now bounded per command, including delayed acknowledgements.
Across focused checks and corrective reruns, 184 unique tests and three subtests
passed. This includes real audio, held-key behavior, pause/resume state, live
EQ/mixer/seeking, status visibility, numeric gestures and display-size constraints.
All 13 frozen modules match source. The EXE passed real-Tk Space cycles for source
and four-stem playback, live EQ/mixer/seek checks and startup/exit with development
Python excluded. The isolated packaged benchmark measured play/pause UI medians
of 24/9 ms (source) and 25/9 ms (four stems). The fix15 session was copied with
five verified audio hashes and restored with edits, selection and Save folder
intact. The launcher selects fix16; fix15 remains preserved.
See [transport verification](docs/qa/transport-latency/verification.md).

## Previous delivery — continuous waveform seeking (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix15.** Left-click and held left-drag position
changes keep the FFplay output device open. One worker prepares the next source
position while current audio continues; the relay crossfades into real prepared
PCM. In-flight preparation completes while newer positions coalesce to the
latest pending request. Output-clock mapping preserves source cursor timing at
different speeds. EQ, mixer, partial-stem offsets and selection fades survive.

Across regression and corrective reruns, 179 tests and six subtests passed.
Checks cover forward/backward movement, tempo/pitch, transition continuity,
concurrent edits, alignment, fades, failures, cleanup and existing exports.
Real Tk gestures verify changes before mouse release. The frozen EXE passed
12 seeks, EQ/mixer commands and startup/exit without development Python; all
12 frozen modules match source. Silent-device seek response measured 0.312–0.391
seconds; physical device latency and listening remain for direct review.
The fix14 session was copied with all five audio hashes verified and restored
in isolation. The launcher now selects fix15; fix14 is preserved. See
[seek verification](docs/qa/live-seek/verification.md).

## Previous delivery — continuous stem mixer (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix14.** All available stem inputs keep
running, including muted/zero-gain tracks. Volume/Mute/Solo and Ctrl+click resets
apply as one atomic set of mixer weights with a short ramp on the existing
control worker. All-muted playback retains transport; unmuting stays aligned.

Across scoped runs and corrective reruns, 152 tests and six subtests passed,
including real PCM, initial/mid-playback silence, chirp cancellation/alignment,
Solo transition amplitude, held faders and reset gestures, concurrent EQ, exports
and cleanup. Initial analyzer-floor assertions were corrected and Tcl setup
failures passed in isolation. The frozen EXE passed EQ/mixer commands plus Tk
startup/exit without development Python; all 11 frozen modules match source.
The latest fix13 session was copied with all five audio hashes verified and
restored in isolation. The root launcher now selects fix14; fix13 is retained.
See [continuous mixer verification](docs/qa/live-mixer/verification.md).

## Previous delivery — continuous EQ mode and slope changes (2026-10-02)

**Status: `USER_REVIEW_READY` — compact-fix13.** Filter mode, pass enable/disable
and 12/24/36/48 dB/oct slopes now retain the running decoder/player. An inactive
EQ bank is prepared before one atomic pair of crossfade weights transfers audio.
Frequency/gain/Q edits continue on the active bank. Tempo/pitch changes and their
lookahead remain outside this extension.

Across scoped runs, 120 tests and three subtests passed, including PCM levels,
bounded transition peaks, rapid changes, export agreement, actual Tk mode/knob/
Ctrl+click events and existing playback/edit behavior. One Tcl setup error passed
in an isolated rerun. The frozen EXE passed gain and 12 mode/slope changes plus Tk
startup/exit without development Python. All 11 frozen modules match the source.
The latest fix12 session was copied with all five audio hashes verified; isolated
restore preserved edits, four stems, selection and Save folder. The root launcher
now selects fix13; the previous release is retained.
See [mode/slope verification](docs/qa/live-eq-modes/verification.md).

## Previous delivery — continuous EQ preview (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix12.** Frequency, gain and Q changes now
update the existing playback while dragging, including leaving 0 dB and moving
enabled pass-filter cutoffs. One latest-value worker, short parameter ramps and
bounded PCM buffering keep UI work independent of command acknowledgements.
Preview/export share f64 EQ stages and filter blocks. Filter type/slope and
other effect changes retain the previous restart path; tempo/pitch lookahead
can delay an EQ change without stopping playback.

Across the full regression and corrective reruns, 290 tests and 22 subtests
passed, with two permission-related skips. The initial full run found four
precision failures and two Tcl/Tk setup errors; all passed in the subsequent
82-test audio/precision run after the f64 correction. Real-Tk drag/reset/pass/
four-stem checks passed. The final EXE passed actual local EQ commands, measured
±12 dB PCM changes with the same processes, clock/continuity checks and startup/
shutdown without development Python. All 11 frozen modules match the source.
Latest fix11 audio, four stems and edits were copied with matching hashes and
restored successfully. The root launcher now selects fix12.
See [Continuous EQ verification](docs/qa/live-eq/verification.md).

## Previous delivery — Cubase-style control reset (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix11.** Steinberg's Cubase documentation confirms
Ctrl+click as the Windows default-value gesture for controls/faders. EQ knobs
and their value labels, plus all four stem faders and their values, now use it.
Gain/volume resets to 0 dB; Pass slope resets to its 24 dB/oct default. Removed
the old double-click reset from those controls and updated closed Help.
Resetting consumes the click before fader track jumps or value drags can start,
and remains one Undo step. All 30 related interaction checks passed across the
main run and isolated reruns; initial system-Tk setup and focus failures are
recorded in the evidence. Real-Tk Ctrl+click captures covered all 14 knob/fader/
value targets. The separate fix11 EXE passed startup/exit and nine-module source
matching. Latest saved fix10 audio, four stems and edits were copied with verified
hashes and restored successfully. The root launcher now selects fix11.
See [Control reset verification](docs/qa/ctrl-reset/verification.md).

## Previous delivery — waveform start visibility (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix10.** The upper/lower stereo waveforms now
start at the visible left edge. Removed L/R text and its 22-scaled-pixel reserved
space, exposing the beginning of the full track and of zoomed/panned views.
Sample times, channels, fades, seeking and selection retain their existing mapping.
The 10:7 aspect, size bounds and FHD/QHD/4K support remain in effect.
Twelve real-Tk full/zoom/pan and size/DPI checks passed, including left-edge
sample-time mapping and decoded channel amplitudes. Six existing fade/seek/
selection/keyboard tests passed. The separate fix10 EXE passed startup/exit and
nine-module frozen-source matching. Latest saved fix9 audio/settings/recovery
were copied with verified hashes; isolated restoration preserved edits, selection
and Save folder without changing user data. The root launcher selects fix10.
See [Waveform beginning verification](docs/qa/waveform-left-edge/verification.md).

## Previous delivery — fixed window aspect and display bounds (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix9.** The approved main-window policy is a
10:7 client aspect, nominal 760x532 minimum / 1400x980 maximum at 100% DPI, and
1000x700 startup. Monitor work area, window decorations and DPI bound every size,
including maximum and minimum on small high-DPI screens. Windows edge/corner
sizing and maximization use the same policy; dialogs retain independent sizing.
Fonts and graphs scale uniformly from the 1000x700 reference. The fixed status
space preserves composition while audio loads or messages change.

FHD, QHD and 4K at 100%, 125%, 150%, 175% and 200% passed 15 real-Tk simulated
work-area checks, including minimum/maximum, maximization, controls and no editor
scrollbar. Native Windows sizing messages and separate-dialog resizing passed.
The regression run passed 265 tests and 22 subtests; a system-Tk setup error and
one playback timing failure both passed isolated reruns (267 passing checks,
one permission-related skip across that suite). The updated session helper passed
24 tests, with two symlink-permission skips. All nine frozen modules match;
the EXE passed startup/exit without development Python. The saved fix8 source-only
session was copied with matching hashes and restored without changing user data.
The root launcher now selects fix9.
See [Aspect and display verification](docs/qa/aspect-bounds/verification.md).
The previous releases and their saved sessions remain preserved.

## Previous delivery — stable loading composition (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix8.** The main editor's fit scale depends
only on the client size and monitor DPI. A fixed 64-logical-pixel status area
keeps the waveform, EQ, mixer, fonts and controls in the same positions when
audio loads or progress, errors and completion feedback appear or disappear.
Its contents are hidden when idle; the main editor still fits without scrolling.
The root launcher selects fix8. Ten resize/loading checks and 41 relevant
workflow tests passed, with two transient system-Tk setup failures resolved by
isolated reruns. Thirteen viewport/DPI cases, EXE startup/exit and seven-module
frozen-source matching passed. The latest saved fix7 source-only session was
copied with verified hashes and restored in an isolated app.

See [Fixed composition verification](docs/qa/fixed-composition/verification.md).
The earlier compact-fix7 package and its latest saved session remain preserved.

## Previous delivery — proportional resizing (2026-10-01)

**Status: `USER_REVIEW_READY` — compact-fix7.** The root launcher selects fix7.
The full app suite passed 214 tests and 22 subtests, with 1 permission-related
skip. The subsequent source-only restore suite passed 22 tests, including two
new preservation/partial-stem checks, with the same permission-related skip.

The main editor now keeps EQ and Stem Mixer side by side and scales fonts,
buttons, spacing and graphs together when either client dimension becomes small.
The main editor has no scrollbars; its minimum client size is 480x360 device pixels.
Contextual progress, cancellation and errors remain visible. Resizing back uses
the original spacing measurements to avoid accumulated rounding drift.

See [Resize verification](docs/qa/proportional-resize/verification.md) for actual
Tk captures, DPI/resize regression checks and the separate compact-fix7 package.
Its EXE passed startup/exit and bundled-engine separation, export and transport
checks. All seven frozen source modules match. The latest fix6 recovery was
source-only; the original audio, selection 0–207.456 seconds, edits and Save
folder were transferred with verified hashes and restored in isolated real Tk.
Press Ctrl+Shift+R in fix7 to restore that state. Older releases are preserved.

## Previous delivery — post-effects playback spectrum (2026-09-30)

**Status: `USER_REVIEW_READY` — compact-fix6.** The live output spectrum follows
the same post-mix, post-EQ/effects PCM sent to the player. The existing editable
EQ curve remains above it, with separate EQ dB and fixed output dBFS axes.

- **208 tests passed, 1 skipped, 19 subtests passed.** Tests measured cuts/boosts,
  stereo polarity, stem gain/Mute/Solo, filters, pitch/limiter, bounded analysis,
  player-clock synchronization, pause/resume/seek/loop, fallback and cleanup.
- Real Tk captures cover 1000x700, 760x620, 640x480 and automatic 200% scaling.
- The separate fix6 EXE passed startup/exit. Bundled-engine separation, mixed
  and four-track WAV/MP3 export, playback and spectrum checks passed. Seven
  frozen source modules match the tested code; no new runtime dependency.
- The latest saved fix5 session was copied with verified hashes: source audio,
  four stems, edits, full selection **0–207.456 seconds** and the existing Save
  folder. An isolated real-Tk restoration passed without changing user files.
- The root launcher selects fix6. Close the old running app before launching the
  new version; use **Ctrl+Shift+R** to restore the transferred session.

See [Playback spectrum](docs/realtime-spectrum.md) for measurements and evidence.
Fix5 and the pre-change working-tree backup remain available. Listening, direct
native EXE input, physical DPI transitions and another-PC use remain direct checks.

## Previous delivery — relocation and selection bounds (2026-09-26)

Canonical project: `C:\Users\brian\Dev\active\Kwaksplit`.
The user approved returning the active project to C: after D: filesystem
operations stalled. The C: checkout contains all 139 tracked baseline files from
`main` / `dfb2ab5` plus the current fixes. D: originals remain preserved; historical
release folders and caches were not fully copied to C:. This is a restored active
project and a new release, not a verified migration of the entire D: tree.

At that delivery, implementation, automated validation and session restoration
were complete (`USER_REVIEW_READY`). The root launcher selected the package at
`release/compact-fix5/KWAK Split/KWAK Split.exe`.

- Complete four-stem coverage now bounds Start/End and waveform selections,
  numeric drags/wheels, split completion, recovery and Undo/Redo. Wider coverage
  requires explicitly choosing Full track and clicking Split Stems. Loading
  source audio and incomplete stems retain the source-track editing bounds.
- **192 tests passed, 1 skipped, and 19 subtests passed.** Eleven responsive
  viewport/scaling cases, fifteen startup work-area checks and five stem-export
  captures were recorded in new evidence folders.
- The new EXE passed startup/exit, frozen-source matching, isolated bundled
  runtime imports, actual four-stem separation, mixed WAV/MP3 and four individual
  files of each format, plus dummy-device play/pause/resume.
- Settings, recovery and five working-audio files were restored at their
  original C: paths from verified backups, then copied into fix5 with verified
  hashes and self-contained recovery audio. An isolated real-Tk restore preserved
  all edits, four stems, selection **5.76–67.60 seconds** and the existing Save
  folder, with Export enabled and no callback errors. Press **Ctrl+Shift+R** in
  fix5 to resume. Previous releases on D:, user source audio and the three
  byte-identical accepted HTML references are preserved.

Direct listening, native Windows mouse/key use, physical monitor/DPI transitions
and independent-PC execution remain user review checks. The native Computer Use
pipe was unavailable in this session; Tk events and captures are separate evidence.
See [Relocation and selection bounds](docs/qa/relocation-range/verification.md)
for results, integrity records and review instructions. No push or promotional-site
changes were made.

## Historical delivery — approved compact desktop UI (2026-09-17)

The following release paths, launcher selections and counts describe the
September 17 deliveries. The September 30 status above is current.

At that delivery, **four-track stem export with a persisted WAV/MP3 option** was added. Stem Mixer > Export saves separate vocals, drums, bass and other files; Settings > Stem format selects the encoding. The selection, faders and effects apply to all four stems, ignoring Mute/Solo. Existing outputs are preserved and unfinished batches are removed on cancellation/failure. **159 tests and 19 subtests passed.** The separate `compact-fix4` package passed bundled-engine checks and actual Windows button-driven export of four WAVs and four MP3s. The root launcher selected that release at the time. Previous releases and accepted HTML references were preserved. Post-split selection bounds were outside that addition and were completed in the September 26 revision above. See [Stem export](docs/qa/stem-export/verification.md).

Previous correction: **two-decimal time editing, zoom-aware numeric gestures, ±24 dB EQ, visible and correctly anchored fades, and nonmodal stem-range recovery**. Time precision remains at 0.01 seconds by the user's explicit choice. All editable numeric controls support vertical dragging; Settings exposes Selection / Full track splitting without automatic separation. Three independent agents verified numeric interactions, measured audio output, and split-range workflows. **146 tests and 19 subtests passed.** Its separate `compact-fix3` package passed startup, bundled Demucs/WAV/MP3/playback checks and native Windows drag/wheel/Undo verification; audio, stems, edit values and Save folder were restored. See [Editing corrections](docs/qa/precision-controls/verification.md).

Previous correction: **mouse-button focus and Space transport are fixed, with an independent three-agent interaction audit**. Confirmed defects in cancellation ordering, rejected project relinking, selection changes during playback, fader Undo, Advanced Q validation, crossed pass filters and duplicate playback status were also corrected. See [Interaction audit](docs/qa/interaction-audit/verification.md). Its `compact-fix2` package and native Windows Space input checks passed. Prior packages remain preserved.

Previous full regression suite: **108 tests and 19 subtests passed**. The earlier [loading/close correction](docs/qa/loading-fix/verification.md) fixed the 207.456-second track's rounded End input leaving the UI busy after loading had completed. Closing immediately cancels processing and preserves temporary recovery when possible, without a blocking dialog. That revision passed 83 tests and 19 subtests.

The user accepted the compact HTML UI and authorized completing the real Python/Tkinter application to match it, including responsive windows for 1080p through 4K displays. The previous preview-only restriction is superseded for this implementation. Preserve existing source changes, projects, audio, settings, runtime assets, historical evidence, and the three accepted preview documents.

Implementation order and acceptance criteria are in [Compact UI implementation](docs/compact-ui-implementation.md). First commit the current application, accepted preview, and this plan as a recovery checkpoint; then complete and validate each package in order. A local commit is authorized; pushing is not requested.

| Package | Scope | Status |
| --- | --- | --- |
| U01 | Preserve baseline and accepted UI; record implementation contract | Complete; checkpoint 388e2db |
| U02 | Real EQ slopes/Q, +12 dB mixer, stereo waveform, edit history compatibility | Complete; objective audio tests passed |
| U03 | Compact responsive Tkinter UI, Settings/Advanced, direct export and interaction wiring | Complete; native window and workflow checks passed |
| U04 | Audio/workflow and viewport/DPI verification, separate release build, updated usage/evidence | Complete; EXE startup and bundled-engine workflow passed |

Source validation: **79 tests and 19 subtests passed**. Eleven viewport/scaling cases, fifteen initial-work-area calculations, 1080p minimum-window checks at five scales, actual four-stem separation and direct WAV/MP3 export passed. See [Compact verification](docs/qa/compact/verification.md) for exact evidence and the distinction between app scaling and physical-device testing.

The initial compact package was delivered at `release/compact/KWAK Split/KWAK Split.exe`; later corrections use separate folders listed above. The earlier English release is preserved. The package includes an isolated app-local Python engine; startup, four-stem separation, 48 kHz/24-bit WAV, 320 kbps MP3 and dummy-device play/pause/resume passed with the development Python path excluded. The real monitor DPI was also detected automatically at 200%, producing a 2000×1400 client window within its work area. Physical laptop/monitor switching and direct listening remain device acceptance checks.

The G01–G08 sections below describe the preserved earlier application, not completion of U01–U04.

## Product goal

Build a Windows audio tool for loading audio, choosing stems and ranges, previewing adjustments, and exporting predictable results. Core controls must remain accessible in small windows, and users must understand the current task and output.

The user approved all eight UX improvements on 2026-09-13, then requested that everything be changed to English. Application-owned UI text, help, errors, and project documentation now use English. User filenames and existing project data retain their original content.

**G01–G08 implementation and local verification are complete.** Direct listening, physical display-scaling changes, and independent execution on another PC remain separate checks. English-pass results are recorded in [English verification](docs/qa/english/verification.md).

## Goal status

| ID | Goal | Priority | Status | Acceptance criteria |
| --- | --- | --- | --- | --- |
| G01 | Speed-aware playback time and cursor | Critical | Implemented; automated checks passed; listening pending | Track original positions at 50/100/200%, preserve slow playback and output tails, finish with the player, and measure fallback WAV duration. |
| G02 | Small-window support | Critical | Implemented; actual-window captures checked; physical DPI check pending | Keep load/play/export/settings accessible through responsive layout, collapsing, tabs, and scrolling on small or scaled displays. |
| G03 | Reset and preserve work | High | Implemented and tested | Default reset, explicit keep-adjustments option, saved projects with audio assets, recovery, and grouped Undo/Redo. |
| G04 | Distinguish monitoring from export | High | Implemented; workflow and captures checked | Show monitor source, export mix/range/effects, Normalize behavior, and individual stem rules. |
| G05 | Selection and loop workflow | Medium | Implemented; actual separation/playback checked | Consistent seeking, looping, zoom/pan, and full-track/selection separation with original-coordinate alignment. |
| G06 | Export formats and results | Medium | Implemented; real files checked | Result playback/folder/path actions and WAV 44.1/48kHz, 16/24bit settings that match output files. |
| G07 | Trustworthy EQ display | Medium | Implemented; captures checked | Remove the decorative spectrum and clearly identify the filter response curve. |
| G08 | Setup, guidance, and status | Medium | Implemented; English pass applied | Consistent English guidance/tooltips, environment checks, clear preparation/download/separation/export/failure stages. |

## Work packages

### G01 — Playback time and cursor

- Separate original-audio coordinates from speed-adjusted playback duration.
- Capture the applied speed at playback start and preserve position through edits, seeking, stopping, and restarting.
- Let actual FFplay completion drive live-preview completion; do not cut buffered audio or effect tails based on estimated time alone.
- Measure fallback WAV duration in the worker.
- Cover 50/100/200%, intermediate starts, stop/seek/restart, and normal/error completion.

### G02 — Small windows

- Fit the initial window to the display and allow resizing down to 640×480.
- Use editor tabs, waveform hiding, and horizontal/vertical scrolling.
- Rearrange EQ details when the outer workspace resizes, including while its tab is hidden.
- Check actual windows at 1280×720, 900×600, and 640×480. Physical Windows DPI switching is not yet checked.

### G03 — Reset and preserve work

- G03a: reset EQ, pitch, speed, fades, stem volume, Mute/Solo, and comparison monitoring by default. Offer explicit adjustment retention.
- G03b: save/open .kwaksplit documents with companion audio assets; reopen recent projects and recover temporary sessions. Explain relinking and missing stems.
- G03c: undo/redo major edits, with one drag treated as one step.
- Preserve user sources and old project assets. Temporary recovery is not a permanent backup.

### G04 — Monitoring versus export

- Display original comparison monitoring separately from the export mix.
- Explain that live monitoring skips Normalize.
- Explain volume/effect and Mute/Solo rules for individual stem export.
- Confirm the mix, range, effects, and output settings before export.

### G05 — Range editing

- Explain left-click seeking and right-drag selection; support loop, zoom, and pan.
- Starting playback from outside the selection returns to its start.
- Separate the full track or only the selection, retaining original time offsets.
- Reject playback/export outside the available separated-stem range.

### G06 — Use exported results

- List output files with playback, folder, and path-copy actions.
- Provide WAV sample-rate/bit-depth profiles and MP3 bitrate selection.
- Preserve existing output names using numbered suffixes.
- Keep selected WAV settings through final Normalize processing.

### G07 — EQ display

- Remove the fixed spectrum decoration and label the graph as filter response.
- A real spectrum analyzer was outside the original G07 scope; the September 30 addition above implements it.

### G08 — Guidance and status

- Use consistent English application labels, guidance, errors, and M/S/Q/comparison tooltips.
- Check FFmpeg, FFplay, Demucs, and model availability and explain setup actions.
- Prioritize actual stages, elapsed time, and measurable progress over decorative messages.
- Windows-owned dialog controls and OS errors follow Windows language settings.

## Verification and delivery

- Regression tests use generated audio in isolated temporary folders; user audio and exports are preserved.
- This is a Tkinter desktop app, not a browser app. Actual-window captures and internal UI tests are distinct from OS input and listening acceptance.
- FFmpeg, the CPU Demucs runtime, htdemucs weights, and a local EXE build are prepared; binaries are not tracked by Git.
- The original G01–G08 Demucs virtual environment referenced this PC's Python installation. Later compact releases replaced that dependency with an isolated app-local runtime; independent-PC acceptance remains unverified.
- Keep implementation, automated tests, captures, human checks, and remaining limitations separate in docs/qa/.
- No Git commit/push or promotional-site changes were requested or made during the original G01–G08 stage. Later local checkpoints are recorded above; no push was made.

## Checkpoints

- 2026-09-13: registered all eight goals; implemented G01 with 15 new regressions, 15 existing checks, and silent real FFplay checks at 50/100/200%. See [G01](docs/qa/G01-playback.md).
- 2026-09-13: completed G02–G08. The original integrated suite passed 46 tests and 18 subtests in 32.36 seconds.
- Real CPU Demucs separated original seconds 2–4 of a generated six-second WAV into four 2.000-second stems; all four individual exports were also 2.000 seconds. Cached runs took 20.046 and 50.797 seconds. This was a workflow check, not a music-quality/performance benchmark.
- Captured actual Tk windows at 1280×720, 900×600, and 640×480 plus Settings; fixed narrow EQ overflow and shutdown callback errors.
- The initial EXE startup/automatic-exit smoke test and copied Demucs CLI both returned 0.
- Direct OS input was unavailable because the native Computer Use pipe could not connect. Internal Tk tests and actual-window captures were completed; listening and physical DPI acceptance remain open.
- English follow-up: translated all application-owned Korean text and documentation; kept project schema, processing behavior, filenames, and prior evidence intact. Added source-string and live-widget/dialog regression checks.
- English verification: 48 tests and 18 subtests passed; actual Selection separation and four exports passed. The English EXE started and exited with code 0. At that stage the root launcher targeted release/english/KWAK Split/KWAK Split.exe, preserving the previous release and its data.
- Historical English build, test, and capture evidence: [English verification](docs/qa/english/verification.md). Current usage: [README](README.txt).
- All original G01–G08 goals were delivered. The separately approved live spectrum is recorded in the September 30 section above.
