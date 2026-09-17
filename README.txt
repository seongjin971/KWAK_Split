KWAK Split — Windows Audio and Stem Editor
==========================================

Goals and status: project.md
Workflow verification: docs/qa/G02-G08-workflow.md
English UI verification: docs/qa/english/verification.md
Local edition: 2026-09-13

Quick Start
-----------
1. Run "Run KWAK Split.cmd" from this folder.
   It opens release/english/KWAK Split/KWAK Split.exe when a build is available,
   otherwise it runs the source using Python on PATH.
2. Click Open Audio to choose WAV/MP3/FLAC/M4A, or drop audio onto the window.
3. Right-drag on the waveform or use Start/End to select a range.
   Left-click and the Now slider change the playback start position.
4. Choose Full Track or Selection beside Split, then click Split Stems.
5. Adjust vocals/drums/bass/other volume, Mute, and Solo in the mixer.
   The other tabs contain presets, pitch, speed, fades, and EQ.
6. Preview with Play/Space, then choose Export WAV or Export MP3.
   Check the selected stems, range, effects, and format in Confirm Export.
7. Select an entry in Exported Files to play it in the default player,
   open its folder, or copy its path.

Use the right/bottom scrollbars in smaller windows. The waveform can be hidden,
and EQ details rearrange with the window width. Settings can also be resized
and scrolled. Very narrow windows require horizontal scrolling.
Application labels, help, status, and errors are in English. Windows-owned
file pickers, standard dialog buttons, and OS error details follow Windows settings.
User filenames are preserved in their original language.

Monitoring and Export
---------------------
- Before separation, playback uses the original audio; afterward it uses the mix.
- M (Mute) excludes a stem. S (Solo) uses only selected stems.
  Solo takes priority when enabled.
- Original comparison changes monitoring only. Export still uses the current mix.
  Current effects also apply to original comparison; it is not a dry A/B mode.
- Live FFplay monitoring skips Peak Normalize. Export applies it when enabled.
- Individual stem export writes every stem to a separate WAV.
  Each volume, EQ, pitch, speed, fades, and Normalize applies; Mute/Solo is ignored.
  A stem at 0% volume is exported as silence.
- Normal mix export follows Mute/Solo. A mix with all stems excluded is rejected.
- The EQ graph shows filter response, not an audio spectrum analysis.
- Waveform/Now positions use the original timeline. At 50% speed, playback lasts
  twice as long; at 200%, half as long. Completion follows the actual player.
- Loop Selection repeats the selected range. Stop also cancels a pending repeat.
  Starting playback from outside the selection returns to its start.
- Zoom +/Zoom −, Fit Selection/Fit All, and the waveform scrollbar aid navigation.
- Selection-only separation retains original time coordinates. To export outside
  the separated range, narrow the selection or separate the required range again.

Projects and Recovery
---------------------
- Save Project (Ctrl+S) stores settings, the working source WAV, and separated
  stems in a .kwaksplit document and its matching .assets folder.
  Example: song.kwaksplit + song.kwaksplit.assets/
  Keep both together when moving or backing up a project.
- Resume with Open Project (Ctrl+O) or Recent Project.
  Missing source audio prompts relinking; missing stems prompt separation again.
- Restore Session uses temporary audio references in temp/recovery.json.
  It is not a permanent project backup and cannot recover deleted working audio.
- New Project, opening another audio file, and closing check for unsaved changes.
- New projects/audio reset EQ, speed, pitch, fades, and stem adjustments by default.
  Enable "Keep adjustments for new audio/projects" in Settings to retain them.
- Undo (Ctrl+Z) and Redo (Ctrl+Y) retain up to 100 major edit states.
  One drag is one step. Audio replacement and separation jobs are not undoable.
- Audio assets are deduplicated by content hash. The project document is replaced
  only after saving succeeds. Older audio assets are not automatically deleted,
  so repeated source changes can increase disk usage.

Output Settings
---------------
- WAV: 44.1kHz or 48kHz, with 16bit or 24bit PCM.
- MP3: 128/192/256/320kbps. WAV bit depth does not apply to MP3.
- Standard profile: 44.1kHz/16bit. DAW profile: 48kHz/24bit.
- Working WAV uses float32 at the source sample rate to avoid unnecessary
  intermediate 16bit quantization.
- Existing export names receive (1), (2), etc., preserving earlier results.
- "Delete working audio after export" is off by default. Enabling it removes the
  current working audio and prevents continued editing or temporary recovery.
  Save a project first if you need to resume later.

Development Setup
-----------------
Python 3.11 with Tkinter was verified here (3.11.9).
These PowerShell commands allow scripts only for that process. They do not change
the system-wide execution policy or require a particular D: drive layout.

  powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dev.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\download_ffmpeg.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_demucs_runtime.ps1

- Tools in bin/ take priority over PATH. Prepare ffmpeg.exe, ffprobe.exe, and ffplay.exe.
- The Demucs script installs demucs 4.0.1 and CPU torch/torchaudio 2.5.1 in the
  backend/demucs_runtime virtual environment.
  Pass -PythonExe 'full path' to use a specific Python installation.
- The first split may require a model download; the app prompts first.
  Models stay in models/ and installation caches in temp/pip-cache/.
- Setup requires free disk space. Runtime/bin/models are not tracked by Git.
- FFmpeg, the CPU runtime, and model weights are prepared in this local checkout
  and its packaged build.

Tests and Build
---------------
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
  .\.build\qa\Scripts\python.exe -B scripts/qa_workspace.py --real-demucs
  powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1

Tests use generated audio in isolated temp/ folders. Pillow, included in the test
dependencies, captures the test application's own window.
build.ps1 builds in .build/ and copies tools, models, runtime, and documents to
release/english/KWAK Split/KWAK Split.exe. Keep working projects backed up before replacing
a release folder. Source edits need a rebuild, or use run_dev.ps1 to run them directly.

The English edition has a separate release folder to preserve the previously open
version and its working files. Existing preferences are copied for this delivery;
temporary session data remains in the original folder. Saved .kwaksplit projects
can be opened from either edition. The root launcher now selects the English build.

The current Demucs virtual environment references this PC's Python installation.
EXE startup/shutdown and the bundled runtime were verified locally, not as a fully
standalone package capable of separation on another PC without Python.
Keep the entire package and verify separation, playback, and export on target PCs.

Troubleshooting and Storage
----------------------------
- Settings → Environment Check / Setup shows FFmpeg/FFplay/Demucs/model availability.
- During separation, check the stage, elapsed time, progress, and log.
  CPU separation can take a while; running jobs can be cancelled.
- Failure details appear in the screen log and logs/app.log.
- If output is quiet or silent, check M/S, volume, Normalize, and Limiter.
- App-local folders: bin/ tools, backend/demucs_runtime/ engine, models/ weights,
  temp/ working files/recovery, output/ default exports, logs/ logs,
  and settings.json preferences.
- Source and EXE runs each use their own application folder for settings and data.
  Run from a writable folder rather than an administrator-only Program Files path.

Important Usage Notice
----------------------
Use this tool only with audio you own, audio you recorded yourself, or samples
you are legally allowed to edit. Do not use it to transform someone else's
copyrighted work without permission or to bypass copyright protections on any
platform.

Third-Party Notices
-------------------
See THIRD_PARTY_NOTICES.txt and the LICENSES folder before redistributing.
