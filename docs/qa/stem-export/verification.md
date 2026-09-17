# Four-track WAV / MP3 export

Date: 2026-09-17

## Behavior

The compact Stem Mixer now exposes Export beside Split Stems. Settings > Stem
format chooses WAV (default) or MP3; the preference survives restart through the
actual settings reader and workspace initializer. The top WAV/MP3 buttons keep
their existing mixed-output behavior.

Export creates separate vocals, drums, bass and other files in Save folder.
It requires all four stems and a selection inside their available coverage.
It never starts separation automatically. Filenames preserve Unicode and include
the selected original-source range and stem name. Repeated exports add numbered
suffixes without replacing existing files.

All four tracks use the selection, their faders and common EQ/Speed/Pitch/fades,
Limiter, sample rate and WAV-depth/MP3-bitrate preferences. Mute/Solo do not remove
tracks from individual export. Zero gain creates a silent file. Peak Normalize
applies independently to each track, so it should be off when relative levels
need to be retained. The default remains off.

The worker renders into a temporary staging folder inside Save folder. Final
filenames appear only after all four renders succeed. Normal cancellation,
render failure and publication failure clean up this export's partial files,
preserving pre-existing files. Opt-in working-audio deletion runs only after the
complete batch succeeds, matching mixed export. Source/project assets are kept.

## Verification

Commands:

```text
.build\qa\Scripts\python.exe -X utf8 -B -m pytest tests -q --capture=sys -p no:cacheprovider
.build\qa\Scripts\python.exe -X utf8 -B scripts/qa_stem_export_ui.py
.build\qa\Scripts\python.exe -X utf8 -B scripts/qa_compact_release.py --release "release/compact-fix4/KWAK Split" --evidence-dir docs/qa/stem-export
```

**159 tests and 19 subtests passed in 234.56 seconds.** The 13 new export cases
passed independently in 21.23 seconds. They cover:

- Four actual files per operation at 48 kHz/24-bit and 44.1 kHz/16-bit WAV, plus
  48 kHz/320 kbps and 44.1 kHz/128 kbps MP3.
- Original-coordinate offsets after partial separation, 125% speed, measured
  pitch/fade/gain behavior, Unicode names, all tracks despite Mute/Solo, and a
  silent fader still producing a full-duration file.
- Settings choices and restart persistence through the actual reader/initializer,
  invalid stored-format fallback, busy/incomplete-stem controls, existing-file
  preservation, new-folder creation, unwritable destinations, and in-range validation.
- Render failure, cancellation and publication failure: no unfinished final
  batch, no loss of existing outputs, and retained working audio.
- Independent Normalize and opt-in cleanup after all four files succeed.
- Mixer heading geometry at 1000, 760, 740 and 640 pixels, including the reflow boundary.

Five generated-audio captures were inspected at 1000×700, 760×620 and 640×480,
plus Settings and the completed four-file result. Both heading actions fit;
the narrow mixer remains reachable through vertical scrolling. See
`ui-results.json` and `captures/`. No Tk callback errors occurred.

## Separate package and native Windows verification

`release/compact-fix4/KWAK Split/KWAK Split.exe` was built in a new folder using
the existing isolated runtime from fix3. The root launcher now selects fix4.
`release-results.json` records:

- EXE startup/exit with the development Python path excluded and an invalid
  external PYTHONHOME; runtime imports confined to the packaged engine.
- Actual bundled Demucs separation into four 2.000-second stems in 26.516 seconds
  on this PC; this is a workflow check, not a long-track performance benchmark.
- Mixed WAV/MP3 plus four individual WAV and four individual MP3 exports using
  bundled FFmpeg. All outputs were 1.600 seconds at 125% speed, 48 kHz, with
  pitch/EQ/fades applied; WAV was 24-bit PCM and MP3 was 320 kbps.
- Dummy-device play/pause/resume and automatic 200% DPI sizing (2000×1400 client).

Windows Computer Use additionally exercised the **actual packaged EXE** with a
separate generated-audio session: restored four fixture stems, clicked Export
for WAV, opened Settings, selected MP3, clicked Done, and clicked Export again.
All eight resulting files had the expected names, 0.800-second decoded duration
at 125% speed, 48 kHz, and either 24-bit PCM or 320 kbps MP3. The format preference
was written to settings. See `native-results.json`. The fixture and its outputs
were removed after inspection; no user-audio export or new user-track split ran.

The existing fix3 window was then closed normally. Its current settings and
recovery were copied to fix4 and restored. The four stem references, coverage,
edit values and Save folder were preserved. The new app remains open and paused
with the Export button available. Recovery resets the waveform viewport to the
whole track; it preserves the selection and edits. Earlier release audio remains
in place because restored stems reference those files.

Tests use generated audio and isolated settings/workspaces. Physical laptop or
monitor switching and direct listening were not repeated; existing responsive
and audio regressions passed in the full suite.

## Preservation

The separately discussed post-split selection clamp is not part of this change.
The three accepted HTML references and previous release folders are preserved.
A local commit is included; no push was requested or made.
