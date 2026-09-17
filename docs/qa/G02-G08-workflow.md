# G02–G08 Workflow Verification

Date: 2026-09-13 · Baseline: local improvements after 4babbf0

Status: all eight planned goals implemented and locally verified. Listening, physical DPI changes, and deployment to another PC remain unverified.
This is the historical workflow report, translated into English without changing its evidence. For the current English UI, see [English verification](english/verification.md).

## Implementation

| Goal | Changes | Evidence |
| --- | --- | --- |
| G01 Playback | Applied-speed cursor, actual FFplay completion, measured fallback WAV duration | Real 50/100/200% playback processes and regressions |
| G02 Small windows | Bounded initial size, 640×480 minimum, scrolling, three tabs, waveform hiding, responsive EQ details, scrollable Settings | Actual Tk tests/captures at 1280×720, 900×600, 640×480 |
| G03 Preserve work | Default reset/optional retention, .kwaksplit with audio assets, recent project/session recovery, unsaved-change prompts, Undo/Redo | Roundtrip/recovery, source-removal survival, cancelled-save preservation, grouped drag history |
| G04 Clarify targets | Monitor/export summaries, effect confirmation, Normalize notice, individual-export rules | Actual summary display and mix/individual export flows |
| G05 Ranges | Original coordinates, Full Track/Selection split, selection playback, loops, zoom/pan | Real Demucs selection split, equal decoded PCM for original/cropped renders, three actual FFplay loop starts and Stop cancellation |
| G06 Results | File list/play/folder/path actions, WAV 44.1/48kHz and 16/24bit, MP3 bitrate, profiles | Four WAV combinations checked by ffprobe, four real stem exports, result-action wiring |
| G07 EQ | Removed decorative spectrum; identified filter response | Actual EQ capture and existing curve tests |
| G08 Guidance | Main-action guidance, M/S/Q/comparison tooltips, environment checks, stage/time/progress | Actual download/separate/export workflow and EXE startup/shutdown |

The original pass used mixed-language guidance; the subsequent user-requested English pass replaces application-owned Korean text. A real spectrum analyzer, fully dry original A/B, and automated quality assessment are outside these goals.

## Automated tests

Environment: Windows, Python 3.11.9, pytest 9.1.1, FFmpeg/FFprobe/FFplay.

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
# With dependencies already installed:
.\.build\qa\Scripts\python.exe -B -m pytest tests -q --capture=sys -p no:cacheprovider
~~~

Historical full-workflow result: **46 passed, 18 subtests passed in 32.36s**.

- Existing audio helpers, musical settings, and EQ regressions.
- Fifteen G01 playback-state regressions plus actual audio-process checks.
- Project/schema validation, external-path escape rejection, nonfinite/malformed values, save cancellation, asset deduplication, and history branching.
- Ten real-Tk integration tests. Message/file dialogs used controlled responses; workers and callback exceptions were checked.
- Actual WAV output at 44.1kHz/16bit, 44.1kHz/24bit, 48kHz/16bit, and 48kHz/24bit, including Normalize-enabled combinations.
- A cropped stem with its original-time offset rendered identical decoded PCM to the corresponding original range. Out-of-coverage ranges produced a guidance error.
- A 0%-volume individual stem exported a silent WAV.
- os.startfile was mocked to check player/folder action wiring; actual external-player listening was not assessed.

Pytest's default file-descriptor capture caused intermittent Tcl initialization failures in this Windows/Tk environment. The complete passing run used --capture=sys.

## Real separation and export

~~~powershell
.\.build\qa\Scripts\python.exe -B scripts/qa_workspace.py --real-demucs
~~~

CPU runtime: demucs 4.0.1, torch/torchaudio 2.5.1+cpu. Model: htdemucs.

1. Generated an isolated six-second, 48kHz sine-wave WAV.
2. Selected original seconds 2–4 in the app and separated Selection.
3. Produced vocals/drums/bass/other at **2.000 seconds each**, retaining original coordinates (2.0, 4.0).
4. Set 48kHz/24bit and exported all four individual stems, each **2.000 seconds**.
5. Cached-model separation took **20.046 seconds** in an earlier run and **50.797 seconds** in the final original-workflow run. Timing varied; these are not music/long-track performance benchmarks.

Machine-readable original result: [workflow-results.json](workflow-results.json).
This proves real engine/range/export integration, not vocal/instrument separation quality on music.

## Actual-window captures

Pillow captured only the test application's own windows. The images were inspected. User applications, audio, and documents were not used.
These original captures predate the English pass and are retained as historical evidence.

- [1280×720 top](captures/desktop-top.png)
- [900×600 top](captures/compact-top.png)
- [900×600 EQ](captures/compact-eq.png)
- [640×480 results](captures/small-results.png)
- [Settings](captures/settings.png)

Fixed during inspection: EQ details forcing excess width after resizing while the EQ tab was hidden, mismatched dark combo/scroll styles, and shutdown callback errors. A 640px-wide window uses horizontal scrolling.

The native Windows Computer Use connection returned native pipe is unavailable (os error 2). Actual-window captures and internal Tk calls do not imply OS mouse/keyboard acceptance. Windows display scaling itself was not changed.

## Original local EXE

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
~~~

- Original output: release/KWAK Split/KWAK Split.exe.
- --smoke-test created the window and exited automatically with **code 0**.
- Copied backend/demucs_runtime/Scripts/python.exe -B -m demucs --help returned **code 0**.
- FFmpeg tools, model weights, CPU runtime, and usage documents were packaged.
- Original pre-English EXE SHA256: B3A1C626B56799F67EDD72389D3F3AA20F10D442E95D9D8A277228B2EF6753FC.
- The current English binary is documented separately in [English verification](english/verification.md).

The runtime references this PC's Python installation. Fully standalone separation on another PC without Python was not checked. Real Demucs integration was tested in the source app; the EXE received startup/shutdown and copied-runtime CLI checks.

## Preservation and remaining checks

- User originals and existing exports were neither used nor deleted. Generated audio stayed in isolated QA temporary folders and was cleaned after testing.
- temp/ui-smoke-t5h9d2yi/ retains small initial test settings/logs only. Its cleanup command was blocked by execution policy and was not retried; the folder contains no generated audio.
- No Git commit/push or promotional-site changes. Binaries, runtime, models, caches, and releases remain ignored by Git.
- Keep saved projects with their audio assets; old assets are not automatically removed. Temporary recovery is not a permanent backup.
- Remaining human checks: music listening/separation quality, physical display scaling and mouse operation, and standalone execution on the target PC.
- No required feature implementation is pending. See [project.md](../../project.md) before further changes.
