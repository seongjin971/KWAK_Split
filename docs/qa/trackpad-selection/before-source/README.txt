KWAK Split — Compact Windows Audio and Stem Editor
=================================================

Edition: 2026-10-03
Goals and status: project.md
Accepted UI and behavior: docs/compact-ui-implementation.md
Current verification: docs/qa/waveform-selection/verification.md
Resize verification: docs/qa/smooth-resize/verification.md
Header feedback verification: docs/qa/header-status/verification.md
Prepared playback verification: docs/qa/warm-transport/verification.md
Previous transport UI verification: docs/qa/transport-latency/verification.md
Waveform seek verification: docs/qa/live-seek/verification.md
Control reset verification: docs/qa/ctrl-reset/verification.md
Continuous EQ: docs/live-eq.md
Waveform start verification: docs/qa/waveform-left-edge/verification.md
Window aspect verification: docs/qa/aspect-bounds/verification.md
Loading composition verification: docs/qa/fixed-composition/verification.md
Proportional resize verification: docs/qa/proportional-resize/verification.md
Playback spectrum: docs/realtime-spectrum.md
Previous release verification: docs/qa/relocation-range/verification.md
Historical compact UI verification: docs/qa/compact/verification.md
Latest interaction audit: docs/qa/interaction-audit/verification.md
Latest editing corrections: docs/qa/precision-controls/verification.md
Four-track export: docs/qa/stem-export/verification.md
Active project: C:\Users\brian\Dev\active\Kwaksplit
Status: USER_REVIEW_READY — compact-fix20

Quick Start
-----------
1. Run "Run KWAK Split.cmd". It selects release/compact-fix20/KWAK Split/KWAK Split.exe,
   or runs the source through run_dev.ps1 when the build is unavailable.
2. Open Audio (Ctrl+O), or drop WAV/MP3/FLAC/M4A onto the window.
3. Right-drag the waveform or edit Start/End to select a range. The initial
   selection is the whole track. Right-drag either blue edge to adjust just that
   end, or the small top grip to move the entire range without changing its length.
   A right click alone keeps the selection. Drag beyond the canvas to pan when
   zoomed in. Press [ / ] to mark start / end at the playhead while listening;
   playback continues, and the marked range applies on the next play/loop/export.
   Each drag or mark is one Undo action. Left-click or left-drag to seek; Play/Space
   plays or pauses once per press; holding Space does not repeatedly toggle it.
   Pause keeps the prepared audio and exact position for quick resume. Loading
   audio or editing while paused prepares playback in the background. Pressing
   Play before that preparation finishes can still take longer.
   While playing, position changes keep the output device open
   and crossfade to prepared audio, including throughout a held drag.
   EQ/mixer settings, stem alignment and selection fades are retained.
   The upper/lower stereo waveforms start at the visible left edge, without
   L/R labels or reserved label space. Zooming and panning retain this alignment.
4. Split Stems separates the selected range into vocals, drums, bass and other.
   Settings > Split Stems > Full track separates the whole file once, so later
   selections can move freely. This takes longer than separating a short range.
   Loading audio never starts separation. Before splitting, play/export use the
   loaded audio directly.
5. Adjust EQ, Speed, Pitch, fades and the stem mixer. Advanced contains Q and
   Limiter. Settings contains output preferences, Loop, and closed Help.
   EQ frequency, gain, Q, filter type and 12/24/36/48 dB/oct slopes update
   during playback without restarting it. Active tempo/pitch processing can
   add response delay. See docs/live-eq.md for details.
   Stem volume, Mute, Solo and Ctrl+click resets also update during playback.
   Muted tracks retain their position; all-muted playback keeps time silently.
6. Set Save folder in Settings. Browse opens the Windows folder chooser;
   cancelling Browse keeps the existing path. Done saves the preferences.
7. WAV or MP3 immediately exports the current selection and mix to Save folder.
   Existing names get numbered suffixes. Click the saved-path status to open
   its folder. Task feedback appears beside the KWAK Split logo as one line of
   text, with a percentage when available and a small Cancel button while busy.
   Long text is shortened; click a message to read it in full. Errors stay visible
   until another action updates the status. There is no progress bar or footer.
8. To save the four tracks separately, choose WAV or MP3 in Settings > Stem format,
   then click Export beside Split Stems in the Stem Mixer. All four separated
   tracks must be available. This does not start another separation.
9. To resume the transferred session, press Ctrl+Shift+R in compact-fix20. Save with
   Ctrl+S to keep a permanent project and its companion audio assets.

Window Size and Displays
------------------------
The main editor keeps a 10:7 client-area aspect ratio during edge/corner resizing
and maximization. At 100% DPI, its nominal minimum is 760x532, startup size is
1000x700 and maximum is 1400x980. Windows scaling multiplies these sizes; the
actual monitor work area, title bar and margins limit them. On a small screen
at high DPI, even the minimum is reduced to fit. Maximization uses this bounded
size centered in the monitor work area.

Fonts, controls, spacing and graphs scale together from the 1000x700 reference.
EQ and Stem Mixer stay side by side, with no editor scrollbar. The header keeps
its height and button positions when task feedback changes. The former lower
status space now belongs to EQ and Stem Mixer. Loading, progress and errors never
change the editor's scale or proportions. Settings and Advanced resize
independently and can still scroll.

While a window edge or corner is being dragged, a temporary image of the editor
scales with the window. Releasing the drag restores sharp, interactive controls
at the final size. Playback continues; the cursor, spectrum and task text catch
up when the live editor returns. Duplicate layout and graph repaints are batched.

FHD (1920x1080), QHD (2560x1440) and 4K (3840x2160) were checked at 100%, 125%,
150%, 175% and 200% app DPI in real isolated Tk windows, with simulated monitor
work areas. Initial/minimum/maximum sizes, maximization and control bounds passed
in all 15 combinations. Windows display settings were not changed. Physical
monitor switching and another PC remain device acceptance checks.

Editing and Monitoring
----------------------
- Low Shelf / High Pass, Mid Bell, High Shelf / Low Pass. In Pass mode the knob
  selects 12/24/36/48 dB/oct; Q independently adjusts resonance in Advanced.
- Shelf/Bell gain spans -24 to +24 dB, matching the graph and audio processing.
- The blue curve shows EQ gain on the left dB axis. During playback, the teal
  spectrum shows the actual processed output on the right -90 to 0 dBFS axis.
  EQ cuts/boosts, stem gains/Mute/Solo, filters, speed/pitch, fades and limiter
  affect that spectrum. Its scale stays fixed so level changes remain visible.
  Pausing clears the spectrum; resuming or seeking starts fresh analysis.
  EQ and stem-mixer edits retain the current analysis stream.
  The spectrum follows the player's audio clock. It averages channel power, so
  opposite-polarity stereo does not disappear. Fallback playback analyzes the
  rendered WAV. Peak Normalize remains an export option.
- New audio starts with flat EQ unless Keep adjustments is enabled. Pass modes
  start at 120 Hz / 8000 Hz and 24 dB/oct. Fades start at 0.02 s, stepping 0.01 s.
- Fades reduce the displayed waveform and have amber envelope lines. Tiny fades
  remain marked when zoomed out; the marker's width is not the fade duration.
  Preview seeking/resuming keeps fades anchored to the full selection.
- Start/End display two decimal places. Drag any editable number vertically or
  use its wheel to adjust it; Shift gives finer steps where available. Time
  steps follow the visible zoom span, with 0.01 s as the smallest step. A click
  still allows typing, and a whole drag is one Undo action.
- Ctrl+click an EQ knob or its value to restore its default: Shelf/Bell gain to
  0 dB, High Pass/Low Pass slope to 24 dB/oct. Each reset is one Undo action.
- Stem faders span silence to +12 dB. Unity is one-third down the scale;
  Ctrl+click a fader or its value to reset it to 0 dB. Home also resets the
  focused knob/fader. Double-click is no longer a knob/fader/value reset.
- Mute is yellow; Solo is red. Mute wins if both are enabled. With any Solo
  active, only unmuted soloed stems play or export in the mixed result. An entirely
  excluded mix plays silently; exporting it is rejected with an error.
  Limiter prevents peaks above its ceiling without
  automatically increasing quiet audio. Peak Normalize applies on export only.
- Selection/cursor coordinates use the original track. Speed changes output
  duration independently of pitch. Play resumes from the paused cursor.
- When all four stems are ready, Start/End and waveform selection stay inside
  their available range, including numeric drags, Undo/Redo and restored sessions.
  The minimum selection is 0.01 seconds, or the entire available range when shorter.
  To edit a wider range, choose Full track in Settings and click Split Stems.
  Nothing splits automatically, and missing stem audio is never substituted.
  Loading new source audio restores full-track selection limits.
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
Ctrl+click knob/fader  Reset EQ gain/slope or stem volume (also on its value)
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

Stem Mixer > Export saves vocals, drums, bass and other as four separate files.
Settings > Stem format chooses WAV (default) or MP3 and is retained on restart.
It uses the same sample rate, WAV depth / MP3 bitrate and Save folder as mixed
export. Names include the source filename, selected range and stem name.
Selection, each fader, EQ, Speed, Pitch, fades and Limiter apply; Mute/Solo are
ignored so all four tracks are saved. A silent fader still produces a file.
Peak Normalize, when enabled, normalizes each stem independently. Disable it
to retain the relative levels between stems. Existing files are preserved with
numbered suffixes. Cancellation or a processing failure removes the unfinished
batch; working audio is kept unless the complete export succeeds and cleanup
was enabled. Click the saved-path status to open the folder containing all four.

Delete working audio after export is off by default. When enabled, successful
export removes owned temporary audio and ends that editing/recovery session.
The original source and saved project assets are preserved. Save a project first
if you want to resume. Settings also retains Keep adjustments and output options.

Running on Another PC
--------------------
Copy the entire release/compact-fix14/KWAK Split folder, not just the EXE, to a writable
folder on a Windows x64 PC. It includes FFmpeg tools, local model weights and an
app-local Python/Demucs runtime. Python imports are confined to that runtime;
the package no longer relies on the developer's Python installation path.
Keep saved projects/assets together. Set Save folder for the destination PC.
An independent laptop run, audio-device listening and physical DPI transitions
have not been observed by automated local QA.

The active project was restored to C:\Users\brian\Dev\active\Kwaksplit after D:
filesystem operations stalled. D: originals and historical releases remain
preserved. Historical release folders and caches were not fully copied to C:;
this is not a complete duplicate of the old workspace. The current compact-fix14
package has its own tools, model weights and isolated runtime.
Source and each release have their own settings, temp, output and logs. Use
saved projects and their companion assets to transfer work between installations.

Local Release Review
--------------------
The October 2 stem-mixer extension keeps the player running during volume,
Mute, Solo and Ctrl+click resets. Silent tracks retain their exact position,
and all-muted playback continues silently. Across scoped runs and reruns,
152 tests and six subtests passed. The fix14 EXE passed actual EQ/mixer commands
and startup/exit without development Python; all 11 frozen modules match source.
The saved fix13 session was copied with matching hashes and restored in isolation.
See docs/qa/live-mixer/verification.md for evidence and listening/timing limits.

The October 2 continuous-EQ extension keeps playback running through filter-kind
and 12/24/36/48 dB/oct slope changes, including pass enable/disable and Ctrl+click
reset. Across scoped runs, 120 tests and three subtests passed. The fix13 EXE
passed gain/mode/slope PCM checks and Tk startup/exit without development Python;
all 11 packaged modules match the source. The fix12 session was copied with
matching audio hashes and restored in isolation, preserving edits and Save folder.
See docs/qa/live-eq-modes/verification.md, including timing/listening limits.

The fixed-composition revision keeps scale and editor geometry unchanged during
audio loading and status updates. Four real audio-load cases and six existing
resize/DPI cases passed, plus 41 relevant workflow checks. Thirteen viewport
cases fit without scrolling. The fix8 EXE passed startup/exit with development
Python excluded; seven frozen source modules match. The latest fix7 saved
session was copied with verified hashes and restored in an isolated app.
See docs/qa/fixed-composition/verification.md for this revision's evidence.

The October 1 revision fits thirteen actual Tk viewport/DPI cases without an
editor scrollbar, including 480x360. The fix7 EXE passed startup/exit and bundled
separation, WAV/MP3 export and play/pause/resume checks. Its seven frozen source
modules match the verified source. The latest fix6 recovery was source-only:
that original audio, edits, 0–207.456-second selection and existing Save folder
were copied with verified hashes. Ctrl+Shift+R restores that state in fix7.
See docs/qa/proportional-resize/verification.md for current evidence.
The full app suite passed 214 tests and 22 subtests, with 1 Windows symlink
permission skip. The subsequent session-restore suite passed 22 tests, including
two new source-only/partial-stem checks, with the same permission skip.

The September 30 checks passed 208 tests and 19 subtests, with 1 skipped test
(Windows symbolic-link permission). Generated-audio tests measured EQ cuts and
boosts, mixer levels, filters, pitch, limiter, playback-clock synchronization,
pause/resume/seek/loop, fallback analysis and cleanup. Actual Tk captures cover
1000x700, 760x620 and 640x480; automatic 200% scaling was also checked.
The packaged EXE started and exited successfully; bundled-engine checks completed
real four-stem separation, mixed WAV/MP3 and four individual exports of each format.
Seven packaged source modules match the tested source. The bundled tools and
model match fix5. The spectrum adds no third-party runtime dependency.

Source Tk events and real-window captures were checked; direct mouse/key use of the new EXE,
music listening/separation quality, physical display/DPI changes and another-PC
execution remain user checks. The transferred session passed an isolated real-Tk
restore: edits and all four stems were preserved, selection remains 0–207.456 s,
and Export is available. Its Save folder remains the original
C:\Users\brian\Dev\active\Kwaksplit\release\compact-fix1\KWAK Split\output.
All seven new session files retained their verified hashes during that check.

Development and Build
---------------------
Verified development Python: 3.11.9 with Tkinter. Commands below affect only the
PowerShell process execution policy, not the system policy.

  python -m pip install -r requirements-runtime.txt
  powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dev.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
  .\.build\qa\Scripts\python.exe -B scripts/qa_compact.py --all-sizes --real-demucs --evidence-dir docs/qa/local-check
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
