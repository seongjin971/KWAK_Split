# Loading completion and immediate close — 2026-09-17

Baseline: `fb37122`. Current release: `release/compact-fix1/KWAK Split/KWAK Split.exe`.

## Reproduced fault

The reported local MP3 has duration 207.456 seconds. Its End input displays 207.46. The initial implementation compared this rounded display against the exact 207.456 maximum and threw `ValueError: A numeric input is outside its allowed range`. The exception escaped the UI worker-queue handler before it processed the queued completion event. Loading had finished internally in about three seconds but `busy` remained true, controls stayed disabled, Cancel kept waiting and Close showed the blocking Task in Progress dialog.

A generated 6.006-second stereo WAV reproduced the same failure. A separate test injected a result-handler exception and reproduced the stranded completion event. Both tests failed before the correction and pass afterward.

## Changes

- Display limits permit centisecond rounding; actual selection/audio bounds remain clamped to the exact duration.
- Each worker result is handled defensively and the queue timer is rescheduled in a finally block. An unexpected result-handling exception is logged and the completion event is still processed.
- Close immediately hides/destroys the window, signals cancellation and terminates only the app's owned audio process trees. It never waits for an audio process or opens a blocking close/save dialog. Late process registration after closing is also handled.
- Existing source files and project assets remain untouched. Temporary session recovery is retained on close when possible; permanent project saves remain explicit.

## Verification

`.build\qa\Scripts\python.exe -X utf8 -B -m pytest tests -q --capture=sys -p no:cacheprovider`

**83 passed, 19 subtests passed in 68.50 seconds.** New regressions verify fractional-duration completion, active controls/hidden progress, no automatic separation, exception-safe completion, immediate close during a real child process, preservation of recovery/source audio and termination of a process registered after close.

`scripts/qa_loading_fix.py` checked the reported MP3 without modifying it. `reported-file-results.json` records 4.884 seconds until controls were ready and 0.031 seconds of CPU over a subsequent 1.5-second idle interval, with zero callback errors and automatic 200% DPI. This is a local measurement, not a universal performance guarantee.

Computer Use also checked the newly packaged EXE through the real Windows file chooser. Its log records START Open Audio at 15:04:08.515 and Loaded at 15:04:12.228 (3.713 seconds). The waveform appeared, Play/Split/WAV/MP3 became usable and the loading/cancel area disappeared. No split ran as a side effect of opening audio.

For the close check, Split Stems was explicitly started, the processing status was observed, and Alt+F4 closed the app without a modal. A subsequent window listing was empty and process inspection found no app or bundled Demucs child remaining. The recovery snapshot was retained. The stuck previous version was then terminated by its verified PID/path; its release and audio files remain preserved.

EXE SHA-256: `a534a1c7f4199cb00fc23849085ea2b94b3ba4f1c92f8cd3a498fe8808f225be`.
The root launcher selects this correction. No preview HTML changed and no push was made.
