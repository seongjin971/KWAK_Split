# G01 — Speed-Aware Playback Verification

Date: 2026-09-13 · Baseline: local changes on top of 4babbf0

Status: implementation and automated verification complete. Direct input and listening checks remain open.
This historical record is translated into English; its original measurements are unchanged.
Current language-pass results are in [English verification](english/verification.md).

## Problem and changes

The original code treated elapsed playback time as original-audio time and stopped the player when it reached the original selection length. At 50% speed this cut playback short; at 200% it could leave the cursor and playing state active after the audio ended.

- Capture the applied speed at start: original position = start position + elapsed time × applied speed.
- Distinguish the current audio's speed from newly entered settings. Automatic restarts inherit the position calculated using the previous speed.
- Complete live preview when FFplay finishes, not when encoding or an estimated timer finishes. Preserve buffered audio and effect tails.
- Report abnormal player/encoder exits separately from successful completion.
- Measure the fallback WAV's actual duration in the worker when FFplay is unavailable.
- Preserve explicit seek positions through restarts.

## Automated verification

Playback regressions:

~~~powershell
python -B -m unittest discover -s tests -p test_playback.py -v
~~~

Result: 15 passed. Speed-adjusted cursor, early-stop, completion, and restart-position failures reproduced before the fix and passed afterward.

Coverage: 50/100/200% cursor progression, slow playback, output tails, fast completion, buffered playback after encoding, process errors, fallback WAV duration, stop, seek, and speed-change restart.

The 15 existing functions in test_audio_helpers.py, test_eq_curve.py, and test_musical.py were also run directly and passed. At this initial stage pytest was not installed; isolated project temp/ paths were supplied for tmp_path. These initial checks were not a pytest-runner result.

Actual audio-process verification:

~~~powershell
python -B -m unittest discover -s tests -p test_playback_audio.py -v
~~~

Selected original seconds 5–9 from a generated 12-second WAV. FFmpeg rendered real WAV files, and actual FFplay ran with SDL_AUDIODRIVER=dummy so completion and app state could be checked without speaker output.

| Speed | Original selection | Output WAV duration | Observed FFplay completion | Final original cursor |
| --- | --- | --- | --- | --- |
| 50% | 4s | 8.000s | 8.438s | 9s |
| 100% | 4s | 4.000s | 4.406s | 9s |
| 200% | 4s | 2.000s | 2.375s | 9s |

Player and encoder exit codes were 0 at all three speeds. At 50%, playback continued beyond the original four seconds; at 200%, it reflected actual completion without waiting four seconds. Observed times include startup and buffering.

git diff --check passed. Each test cleaned its temporary folder. User audio and existing exports were not used.

## Remaining direct checks

The Windows Computer Use connection returned:

~~~text
Computer Use native pipe is unavailable ... (os error 2)
~~~

OS clicks/drags, actual Windows audio-device output, and audible quality were not verified. Automated success does not substitute for these checks.

With Python and FFmpeg tools available:

~~~powershell
python -B .\StemSamplePrep.py
~~~

- [ ] Play a 12-second selection at 50/100/200%; hear approximately 24/12/6 seconds through the end and verify the Play button resets.
- [ ] Check that Now uses original coordinates, moving slower at 50% and faster at 200%.
- [ ] Change speed during playback, then stop/resume without an unexpected cursor jump.
- [ ] Seek with the waveform and Now slider during playback; resume from the requested original position.
- [ ] In an isolated environment without FFplay, listen to the fallback WAV through its actual output duration.

Cursor tracking remains elapsed-time based, not sample-accurate synchronization compensating for device latency. Natural completion snaps to the original selection end while FFplay plays the full output.

## Original-stage notes

- One stdout-handle ResourceWarning was observed in the existing FFmpeg _run_checked render path. Tests and child-process exits passed. That resource-management path was not changed in G01 alone.
- The EXE was not built during G01 alone; source changes required a later build.
- Demucs installation, model download, and actual stem-separation quality were not checked in G01 alone.

## Follow-up after G02–G08 (2026-09-13)

The later full-workflow pass superseded those initial limitations where stated:

- Installed pytest and passed 46 tests plus 18 subtests.
- Tested actual FFplay loop restarts and cancellation after Stop through a real Tk application using silent output.
- Captured actual windows at several sizes; this did not substitute for OS input or listening.
- Closed FFmpeg/Demucs stdout handles to address the resource warning.
- Installed the CPU runtime/model and completed actual separation of generated audio.
- Built the updated EXE and verified startup/automatic shutdown with exit code 0.

See [G02–G08 workflow verification](G02-G08-workflow.md) and [project.md](../../project.md) for current status and remaining checks.
