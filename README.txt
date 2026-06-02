KWAK Split Portable
===================

Purpose
-------
KWAK Split is a portable Windows audio tool for preparing original recordings,
self-owned music, and legally usable samples for AI music production workflows.

Important Usage Notice
----------------------
Use this tool only with audio you own, audio you recorded yourself, or samples
you are legally allowed to edit. Do not use it to transform someone else's
copyrighted work without permission or to bypass copyright protections on any
platform.

Current Scope
-------------
Implemented:
- Load wav/mp3/flac/m4a files.
- Drag and drop audio files into the app window.
- Convert input audio to an internal working WAV.
- Show the waveform.
- Select a range by dragging, sliders, or numeric Start/End inputs.
- Select the full range.
- Run Demucs-based 4-stem separation:
  - vocals
  - drums
  - bass
  - other
- Per-stem volume, mute, and solo.
- Per-stem volume percentage and 100% reset.
- Source preview, current mix preview, and individual stem preview.
- Realtime preview via ffplay.exe when available.
- Top Play/Stop button and Space key playback.
- Playback position marker on the waveform.
- Now bar above Start/End for choosing the next playback start position.
- Stem preset buttons:
  - Full Mix
  - Vocal Only
  - Instrumental
  - No Drums
  - No Bass
- Cancel long conversion, separation, and render tasks.
- Render only the selected range to WAV or MP3.
- Fade in / fade out.
- 3-band EQ with frequency, Q, and shape controls.
- High-pass / low-pass filters.
- Pitch and Speed controls using FFmpeg rubberband.
- Peak normalize, limiter, and limiter ceiling settings.
- Save rendered files to the output folder.
- Open the output folder.
- Write logs to logs/app.log.
- Show or hide detailed logs.
- Clean the current project temp files.
- Root launcher: Run KWAK Split.cmd.

Folder Layout
-------------
StemSamplePrep_Portable/
|-- Run KWAK Split.cmd             launcher from the project root
|-- StemSamplePrep.py
|-- bin/
|   |-- ffmpeg.exe                 required
|   |-- ffprobe.exe                recommended
|   `-- ffplay.exe                 recommended for realtime preview
|-- backend/
|   |-- audio_processing/
|   `-- demucs_runtime/            portable Python + Demucs runtime
|-- models/                        Demucs model cache
|-- temp/                          working WAV and stem temp files
|-- output/                        render output
|-- logs/                          app.log
|-- LICENSES/
|-- settings.json
|-- README.txt
`-- THIRD_PARTY_NOTICES.txt

Storage Policy
--------------
The app is designed to keep working files inside the app folder instead of using
AppData, the system temp folder, or user document folders.

The app and child processes prefer these local paths:
- temp: temp/
- output: output/
- models: models/
- logs: logs/
- FFmpeg: bin/ffmpeg.exe
- FFplay: bin/ffplay.exe
- Demucs runtime: backend/demucs_runtime/

Developer and build scripts use these D: drive locations for caches:
- D:\DevCache\pip
- D:\DevData\PythonUserBase

Development Mode
----------------
PowerShell:
  cd StemSamplePrep_Portable
  .\run_dev.ps1

Direct run on the build machine:
  D:\DevTools\Python\Python313\python.exe .\StemSamplePrep.py

Preparing FFmpeg
----------------
The app first looks for bin/ffmpeg.exe and bin/ffplay.exe. If they are missing,
it falls back to executables on PATH. For a fully portable build, keep
ffmpeg.exe, ffprobe.exe, and ffplay.exe in bin/.

Automatic setup:
  cd StemSamplePrep_Portable
  .\scripts\download_ffmpeg.ps1

The script downloads the Gyan.dev Windows essentials ZIP to temp/downloads and
copies ffmpeg.exe, ffprobe.exe, and ffplay.exe into bin/.

Preparing the Demucs Runtime
----------------------------
4-stem separation requires Demucs or an equivalent engine. The app looks for
Demucs in this order:
1. backend/demucs_runtime/python.exe -m demucs
2. backend/demucs_runtime/Scripts/python.exe -m demucs
3. bin/demucs.exe
4. demucs on PATH
5. python -m demucs in the current Python environment

Portable releases should use option 1.

Setup script:
  cd StemSamplePrep_Portable
  .\scripts\prepare_demucs_runtime.ps1

The script installs demucs/torch/torchaudio into backend/demucs_runtime and
patches Demucs WAV writing to use Python's standard wave module on Windows.

Notes:
- Demucs and PyTorch are large. Several GB may be needed during setup.
- If Python 3.13 wheels are unavailable in your environment, prepare a Python
  3.11 or 3.12 runtime on D: and pass it via -PythonExe.
- On first separation, Demucs may need model weights. The app points TORCH_HOME,
  HF_HOME, and DEMUCS_CACHE into models/.

Offline / Fully Portable Release Checklist
------------------------------------------
On the build machine:
1. .\scripts\download_ffmpeg.ps1
2. .\scripts\prepare_demucs_runtime.ps1
3. Run one 4-stem split with a test audio file so the model cache is populated.
4. .\build.ps1
5. Distribute the whole release\KWAK Split folder or the tester ZIP.

Users only need to run one of these:
- StemSamplePrep_Portable\Run KWAK Split.cmd
- release\KWAK Split\Run KWAK Split.cmd
- release\KWAK Split\KWAK Split.exe

Portable EXE Build
------------------
PyInstaller build:
  cd StemSamplePrep_Portable
  .\build.ps1

Build output:
  StemSamplePrep_Portable\release\KWAK Split\KWAK Split.exe
  StemSamplePrep_Portable\release\KWAK Split\Run KWAK Split.cmd

build.ps1 creates:
- .build/: build venv and PyInstaller work files
- release/: portable output

How To Use
----------
1. Run KWAK Split.cmd or KWAK Split.exe.
2. Click Insert to choose a wav/mp3/flac/m4a file, or drop an audio file into
   the app window.
3. Select a range by dragging on the waveform or using the Start/End controls.
4. Click Stem Split.
5. Adjust stem volume, mute, and solo, or use the Stem Presets.
6. Adjust EQ, high-pass/low-pass, Pitch, and Speed if needed. Fade in/out,
   peak normalize, limiter, and output location are in Render Settings.
7. Use Play (Space) or the Space key to preview the selected range.
   - Before stem separation: previews the original selected range.
   - After stem separation: previews the current stem mix.
   - Press again while playing to stop.
   - The red marker and Now bar show the current playback position.
   - Moving the Now bar changes the next playback start position.
   - If bin/ffplay.exe is available, preview plays without creating a temp WAV.
8. Click WAV Render or MP3 Render.
9. After rendering, the completion popup can open the output folder.

Troubleshooting
---------------
FFmpeg not found:
- Check bin/ffmpeg.exe.
- Run .\scripts\download_ffmpeg.ps1.

Demucs runtime not found:
- Check backend/demucs_runtime/python.exe.
- Run .\scripts\prepare_demucs_runtime.ps1 or use the tester ZIP that already
  includes the portable Demucs runtime.

Model download prompt appears:
- The models/ folder is missing model weights.
- If internet is available, continue and let Demucs download the model into
  models/.
- For offline distribution, populate the model cache on the build machine first.

The app appears stuck:
- Demucs separation can take a long time on large files.
- Check the progress indicator and log area.
- The same messages are written to logs/app.log.

Rendered audio is too quiet or silent:
- Check whether all stems are muted.
- If solo is enabled, only soloed stems are rendered.
- Check whether volume is set to 0%.

Third-Party Notices
-------------------
See THIRD_PARTY_NOTICES.txt and the LICENSES folder before redistributing.
