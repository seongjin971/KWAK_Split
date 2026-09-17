# KWAK Split Improvement Goals and Status

Baseline: main / 4babbf0 · Started: 2026-09-13

## Current work — approved compact desktop UI (2026-09-17)

The user accepted the compact HTML UI and authorized completing the real Python/Tkinter application to match it, including responsive windows for 1080p through 4K displays. The previous preview-only restriction is superseded for this implementation. Preserve existing source changes, projects, audio, settings, runtime assets, historical evidence, and the three accepted preview documents.

Implementation order and acceptance criteria are in [Compact UI implementation](docs/compact-ui-implementation.md). First commit the current application, accepted preview, and this plan as a recovery checkpoint; then complete and validate each package in order. A local commit is authorized; pushing is not requested.

| Package | Scope | Status |
| --- | --- | --- |
| U01 | Preserve baseline and accepted UI; record implementation contract | In progress |
| U02 | Real EQ slopes/Q, +12 dB mixer, stereo waveform, edit history compatibility | Pending |
| U03 | Compact responsive Tkinter UI, Settings/Advanced, direct export and interaction wiring | Pending |
| U04 | Audio/workflow and viewport/DPI verification, separate release build, updated usage/evidence | Pending |

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
- A real spectrum analyzer remains optional follow-up work, not a requirement for this goal.

### G08 — Guidance and status

- Use consistent English application labels, guidance, errors, and M/S/Q/comparison tooltips.
- Check FFmpeg, FFplay, Demucs, and model availability and explain setup actions.
- Prioritize actual stages, elapsed time, and measurable progress over decorative messages.
- Windows-owned dialog controls and OS errors follow Windows language settings.

## Verification and delivery

- Regression tests use generated audio in isolated temporary folders; user audio and exports are preserved.
- This is a Tkinter desktop app, not a browser app. Actual-window captures and internal UI tests are distinct from OS input and listening acceptance.
- FFmpeg, the CPU Demucs runtime, htdemucs weights, and a local EXE build are prepared; binaries are not tracked by Git.
- The bundled Demucs virtual environment references this PC's Python installation. Fully standalone operation on another PC without Python is not certified.
- Keep implementation, automated tests, captures, human checks, and remaining limitations separate in docs/qa/.
- No Git commit/push or promotional-site changes were requested or made.

## Checkpoints

- 2026-09-13: registered all eight goals; implemented G01 with 15 new regressions, 15 existing checks, and silent real FFplay checks at 50/100/200%. See [G01](docs/qa/G01-playback.md).
- 2026-09-13: completed G02–G08. The original integrated suite passed 46 tests and 18 subtests in 32.36 seconds.
- Real CPU Demucs separated original seconds 2–4 of a generated six-second WAV into four 2.000-second stems; all four individual exports were also 2.000 seconds. Cached runs took 20.046 and 50.797 seconds. This was a workflow check, not a music-quality/performance benchmark.
- Captured actual Tk windows at 1280×720, 900×600, and 640×480 plus Settings; fixed narrow EQ overflow and shutdown callback errors.
- The initial EXE startup/automatic-exit smoke test and copied Demucs CLI both returned 0.
- Direct OS input was unavailable because the native Computer Use pipe could not connect. Internal Tk tests and actual-window captures were completed; listening and physical DPI acceptance remain open.
- English follow-up: translated all application-owned Korean text and documentation; kept project schema, processing behavior, filenames, and prior evidence intact. Added source-string and live-widget/dialog regression checks.
- English verification: 48 tests and 18 subtests passed; actual Selection separation and four exports passed. The English EXE started and exited with code 0. The root launcher targets release/english/KWAK Split/KWAK Split.exe, preserving the open previous release and its data.
- Current English build, test, and capture evidence: [English verification](docs/qa/english/verification.md). Usage: [README](README.txt).
- No required feature implementation remains. A real spectrum analyzer is an optional extension.
