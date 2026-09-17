KWAK Split — Compact Windows Audio and Stem Editor
=================================================

Edition: 2026-09-17
Goals and status: project.md
Accepted UI and behavior: docs/compact-ui-implementation.md
Verification: docs/qa/compact/verification.md
Latest interaction audit: docs/qa/interaction-audit/verification.md
Latest editing corrections: docs/qa/precision-controls/verification.md

Quick Start
-----------
1. Run "Run KWAK Split.cmd". It selects release/compact-fix3/KWAK Split/KWAK Split.exe,
   or runs the source through run_dev.ps1 when the build is unavailable.
2. Open Audio (Ctrl+O), or drop WAV/MP3/FLAC/M4A onto the window.
3. Right-drag the waveform or edit Start/End to select a range. The initial
   selection is the whole track. Left-click seeks; Play/Space plays or pauses.
4. Split Stems separates the selected range into vocals, drums, bass and other.
   Settings > Split Stems > Full track separates the whole file once, so later
   selections can move freely. This takes longer than separating a short range.
   Loading audio never starts separation. Before splitting, play/export use the
   loaded audio directly.
5. Adjust EQ, Speed, Pitch, fades and the stem mixer. Advanced contains Q and
   Limiter. Settings contains output preferences, Loop, and closed Help.
6. Set Save folder in Settings. Browse opens the Windows folder chooser;
   cancelling Browse keeps the existing path. Done saves the preferences.
7. WAV or MP3 immediately exports the current selection and mix to Save folder.
   Existing names get numbered suffixes. Click the saved-path status to open
   its folder. Errors and progress appear in the same contextual area.

Window Size and Displays
------------------------
The initial window fits its monitor's work area and DPI. Fonts, controls and
graphs scale together. Widening the window expands the editors; a narrow window
stacks EQ above Stem Mixer. Short windows scroll vertically while the top
Open Audio / Settings / WAV / MP3 row remains available. No horizontal scroll
is required. Settings and Advanced also fit the work area and can scroll.

The layout was checked at 1080p–4K equivalent app sizes and 100–200% app scaling,
including a 640x480 window. These checks do not change Windows display settings.
Physical monitor switching and a separate laptop remain device acceptance checks.

Editing and Monitoring
----------------------
- Low Shelf / High Pass, Mid Bell, High Shelf / Low Pass. In Pass mode the knob
  selects 12/24/36/48 dB/oct; Q independently adjusts resonance in Advanced.
- Shelf/Bell gain spans -24 to +24 dB, matching the graph and audio processing.
- The graph shows the actual filter response, not a spectrum analyzer.
- New audio starts with flat EQ unless Keep adjustments is enabled. Pass modes
  start at 120 Hz / 8000 Hz and 24 dB/oct. Fades start at 0.02 s, stepping 0.01 s.
- Fades reduce the displayed waveform and have amber envelope lines. Tiny fades
  remain marked when zoomed out; the marker's width is not the fade duration.
  Preview seeking/resuming keeps fades anchored to the full selection.
- Start/End display two decimal places. Drag any editable number vertically or
  use its wheel to adjust it; Shift gives finer steps where available. Time
  steps follow the visible zoom span, with 0.01 s as the smallest step. A click
  still allows typing, and a whole drag is one Undo action.
- Stem faders span silence to +12 dB. Unity is one-third down the scale;
  double-click or Home resets a focused fader to 0 dB.
- Mute is yellow; Solo is red. Mute wins if both are enabled. With any Solo
  active, only unmuted soloed stems play/export. An entirely excluded mix is
  rejected with an error. Limiter prevents peaks above its ceiling without
  automatically increasing quiet audio. Peak Normalize applies on export only.
- Selection/cursor coordinates use the original track. Speed changes output
  duration independently of pitch. Play resumes from the paused cursor.
- After selection-only separation, extending beyond the stems' coverage
  shows an inline notice. Click Split Stems for the required range, or choose
  Full track in Settings and split once. Nothing splits automatically, and
  missing stem audio is never substituted. Returning inside coverage clears
  the notice and allows playback/export again.
- Loading, separation and export run in workers. Cancel is shown during a job.
  Audio processing and model preparation messages remain visible when relevant.

Keyboard and Waveform
---------------------
Space                  Play / Pause (outside text inputs and dialogs)
Tab / Enter            Focus a button / activate it; mouse clicks leave no button selection
Ctrl+O                 Open Audio
Ctrl+Z                 Undo
Ctrl+Y / Ctrl+Shift+Z   Redo
Ctrl+S                 Save session/project
Ctrl+Shift+O           Open session/project
Ctrl+Shift+R           Restore last temporary session
Right-drag             Select a waveform range
Mouse wheel on wave    Zoom at pointer
Shift+wheel on wave    Pan waveform
Drag / wheel on number Change value; Shift for finer steps
+ / - / 0              Zoom in / out / fit, while waveform has focus

Projects and Recovery
---------------------
A .kwaksplit document keeps edits and references its matching .kwaksplit.assets
folder. Keep both together when moving a project. Old version-1 documents remain
readable; the new version includes EQ slopes and the wider fader range.
Saving is atomic and existing audio assets remain untouched.

Temporary recovery uses temp/recovery.json; it is not a permanent audio backup.
Closing immediately dismisses the window and cancels active processing. The app
keeps a temporary recovery snapshot when possible, without a blocking dialog.
Save with Ctrl+S for a permanent project. Loading another file checks unsaved
changes. Undo/Redo stores 100
major edits, grouping each drag; file changes and separation jobs are not undone.
Project/history controls use shortcuts so the main UI stays compact.

Output and Settings
-------------------
WAV: 44.1 or 48 kHz, 16 or 24 bit PCM. MP3: 128/192/256/320 kbps.
Defaults: 48 kHz / 24 bit, MP3 320 kbps, Loop on, Normalize off, Limiter on.
WAV and MP3 share Save folder and preserve original Unicode filenames.
Working audio uses float32, avoiding intermediate 16-bit quantization.

Delete working audio after export is off by default. When enabled, successful
export removes owned temporary audio and ends that editing/recovery session.
The original source and saved project assets are preserved. Save a project first
if you want to resume. Settings also retains Keep adjustments and output options.

Running on Another PC
--------------------
Copy the entire release/compact-fix3/KWAK Split folder, not just the EXE, to a writable
folder on a Windows x64 PC. It includes FFmpeg tools, local model weights and an
app-local Python/Demucs runtime. Python imports are confined to that runtime;
the package no longer relies on the developer's Python installation path.
Keep saved projects/assets together. Set Save folder for the destination PC.
An independent laptop run, audio-device listening and physical DPI transitions
have not been observed by automated local QA.

The earlier release/english folder and its settings/output remain preserved.
Source and each release have their own settings, temp, output and logs. Existing
session data stays in its original folder; use saved projects to transfer work.

Development and Build
---------------------
Verified development Python: 3.11.9 with Tkinter. Commands below affect only the
PowerShell process execution policy, not the system policy.

  powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dev.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
  .\.build\qa\Scripts\python.exe -B scripts/qa_compact.py --all-sizes --real-demucs
  powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1

Prepare missing tools/runtime with scripts/download_ffmpeg.ps1 and
scripts/prepare_demucs_runtime.ps1. Tools in bin/ take precedence over PATH.
The runtime uses Demucs 4.0.1 with CPU torch/torchaudio 2.5.1. Model downloads
require confirmation and remain under models/. Runtime/model/tool binaries are
not tracked by Git. Tests use generated audio in isolated temporary folders.

build.ps1 creates a separate release/compact folder and refuses to overwrite an
existing release. Use -ReleaseName compact-next for another build, then select
the verified edition in the root launcher. -SkipDependencyInstall reuses the
prepared build environment. Source changes require rebuilding the EXE.

Troubleshooting and Notices
---------------------------
Settings > Help > Environment Check reports tools/runtime/model availability.
Settings > View Log and logs/app.log contain processing details. The contextual
status reports failed operations; a new action can be tried after correcting it.
App-local folders are bin/, backend/demucs_runtime/, models/, temp/, output/,
logs/ and settings.json. Run from a writable folder.

Use audio you own or are authorized to edit. Third-party component and source
notices are in THIRD_PARTY_NOTICES.txt and LICENSES/. Package-specific notices
remain with bundled dependencies. The Python runtime includes LICENSE.txt.
