# Compact desktop application verification — 2026-09-17

Accepted UI: the three unchanged HTML files listed in `docs/compact-ui-implementation.md`.
Baseline preservation commit: `388e2db`. Earlier G01–G08/English evidence is retained separately.

## Source and behavior

Command: `.build\qa\Scripts\python.exe -X utf8 -B -m pytest tests -q --capture=sys -p no:cacheprovider`

Result: **79 passed, 19 subtests passed in 50.41 seconds**.

- Real FFmpeg measurements match the response display for 12/24/36/48 dB/oct, independent Q, Low/High Shelf and Bell. Pass cutoff and stopband samples are checked; opposite-polarity stereo channels remain distinct.
- Fader mapping preserves 0 dB at 33% from the top, silence and +12 dB endpoints. Mute overrides Solo; drag history and double-click reset are checked.
- Limiter preserves quiet gain, enforces a measured ceiling and preserves output duration. Live preview and rendering use the same limiter/filter implementation; export-only peak normalization remains explicit.
- Numeric input remains readable, rejects empty/invalid values and participates in history. Settings folder cancellation preserves the prior path. Direct WAV/MP3 exports do not prompt for a filename and preserve an earlier same-name file byte-for-byte.
- Existing project/recovery, selection timing, speed, loop/cancellation and generated-audio integration regressions pass. Version-1 project compatibility is covered.

## Actual native windows

Command: `.build\qa\Scripts\python.exe -X utf8 -B scripts/qa_compact.py --all-sizes`

`ui-results.json` records 11 actual Tk viewport cases and 15 startup-size calculations. `captures/` contains native window captures inspected directly.

| App case | Scaling | Result |
| --- | --- | --- |
| 1000×700, 760×620 | 100% | EQ/mixer side by side; no scroll required |
| 640×480 | 100% | Stacked panels; vertical scroll reaches mixer bottom; fixed header |
| 1840×960 | 100% | 1080p equivalent layout |
| 1760×930, 1760×900 | 125%, 150% | 1080p equivalent layout |
| 1760×900, 1760×880 | 175%, 200% | Fixed header; vertical editor scroll |
| 2400×1280 | 150% | 1440p equivalent layout |
| 3640×1980 | 175%, 200% | 4K equivalent widget bounds; same-scale visible-window captures |

Actual monitor work area was 2880×1704. Windows resolution, global scaling and unrelated windows were not changed. A full 4K viewport extends beyond that physical display, so its layout is verified by widget bounds; its screenshots show a fully visible normal window at the same scale (1750×1225 / 2000×1400). They are not presented as full physical-4K screenshots. Settings and Advanced were also captured; narrow-window bottom reachability is checked.

Separate regression checks exercise actual startup/minimum window geometry against a 1920×1040 work area at 100/125/150/175/200%. This caught and fixed a minimum-height conflict at high scaling.

## Real separation and exports

`audio-results.json`: actual local Demucs split of source seconds 2–4 completed in 42.562 seconds, producing four stems, followed by successful direct WAV and MP3 exports. Inputs were generated test audio; no user audio was uploaded or modified.

The source UI verification uses a controlled Tk fixture. Tests of FFplay use SDL's dummy audio device. Process behavior and cursor state are checked; they are not a human listening test.

## Release

Target: `release/compact/KWAK Split/KWAK Split.exe`.

The build is separate from `release/english` and refuses to overwrite an existing release. It includes FFmpeg tools, model weights and an app-local Python/Demucs runtime with imports restricted by `python311._pth`. The original runtime/model sources and earlier release are preserved.

Command: `.build\qa\Scripts\python.exe -X utf8 -B scripts/qa_compact_release.py --release "release/compact/KWAK Split"`

`release-results.json` records:

- Packaged EXE startup and clean shutdown: exit 0. SHA-256 `9a93862b7ad9c8e8d9bd00ede37a47b4987eea17ad58c674639d08f464dc428a`.
- Bundled interpreter imports remain inside the release even with an intentionally invalid PYTHONHOME and a PATH excluding the development Python installation.
- The source UI, using the packaged Demucs/FFmpeg/models, separated source seconds 2–4 into four exactly 2.0-second stems in 30.344 seconds.
- At 125% speed, +3-semitone pitch, HP/LP EQ and 0.04-second fades, WAV and MP3 exports both measure 1.6 seconds: WAV 48 kHz/24-bit PCM and MP3 48 kHz/320 kbps.
- Play/pause/resume succeeds with SDL's dummy audio device. This verifies process and cursor behavior, not listening.
- Without a DPI override, the actual monitor reports 200% and the app opens at a fully visible 2000×1400 client size. `captures/automatic-dpi.png` shows the real native window.

The root launcher selects this verified compact edition. Python/Torch/Demucs package notices match the bundled environment. README/project/verification documents are copied into the release after final validation.

## Verification limits

Direct human listening, physical monitor/DPI transitions and an independent laptop run remain unobserved. The app-level resizing/scaling checks, actual native captures, objective audio tests and local packaged-engine checks are distinct evidence. The user's final aesthetic and device acceptance is separate from these automated results.
