KWAK Split — Compact Windows Audio and Stem Editor
=================================================

Edition: 2026-10-13
Goals and status: project.md
Accepted UI and behavior: docs/compact-ui-implementation.md
Current verification: docs/qa/stabilization/verification.md
Continuous EQ: docs/live-eq.md
Playback spectrum: docs/realtime-spectrum.md
Status: FINAL - compact-fix30

Licenses and distribution
-------------------------
KWAK Split's original code is MIT licensed; see LICENSE.
Included libraries and tools have their own license records:
  - Component notices: THIRD_PARTY_NOTICES.txt
  - Demucs model: LICENSES/demucs-model/NOTICE.txt
  - Distribution and source materials: docs/license-compliance.md

The Demucs model weights are not included. The first Split Stems downloads them
(about 84 MB) from the official Demucs server. They are not covered by KWAK
Split's MIT license; the Demucs author provides them for research purposes.
Check that your use is permitted.

A public download must provide the prepared source/ materials for FFmpeg and
LAME beside the application. The original v1.0.0 ZIP remains a draft and must
not be re-published. Available published downloads are listed in GitHub Releases.

build.ps1 verifies these records and keeps model files out of public builds.
-LocalOnly marks a non-public development build.

Quick Start
-----------
1. Run "Run KWAK Split.cmd". It selects release/compact-fix30/KWAK Split/KWAK Split.exe,
   or runs the source through run_dev.ps1 when the build is unavailable.
2. Open Audio (Ctrl+O), or drop WAV/MP3/FLAC/M4A onto the window.
3. Drag the large blue left handle to set the start and the right handle to set
   the end. Handles only adjust the range; a plain click or tiny movement on one
   leaves the playback position alone. The waveform uses a normal arrow cursor;
   over the ends it becomes a left/right resize arrow.
   Num Lock, Caps Lock and Scroll Lock do not change these gestures.
   Range dragging keeps the paused cursor. During playback, releasing a drag
   applies the new bounds and fades from the current position while keeping
   the live output device open. If the current position falls outside the new
   range, playback starts at the new range start.
   Click a position in the waveform body, then Shift+click another to select between them.
   Repeated Shift+clicks keep the original seek point, even during playback or
   after zooming. Before the first seek click, the current playhead is the anchor.
   Drag either blue edge to adjust just that end, or the small top grip to move
   the range without changing its length. Either mouse button works on handles;
   a plain tap on a handle keeps the cursor and range. Shift+click keeps playback running and the
   new selection applies on the next play/loop/export.
   Right-drag the waveform body or edit Start/End also selects a range. The
   initial selection is the whole track.
   A right click alone keeps the selection. Drag beyond the canvas to pan when
   zoomed in. Press [ / ] to mark start / end at the playhead while listening;
   playback continues, and the marked range applies on the next play/loop/export.
   Each selection gesture or mark is one Undo action. Left-click or left-drag the
   waveform body to seek; Play/Space
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
   The first split downloads the Demucs model (about 84 MB) once, so it needs
   an internet connection; see LICENSES/demucs-model/NOTICE.txt for its terms.
   Settings > Split Stems > Full track separates the whole file once, so later
   selections can move freely. This takes longer than separating a short range.
   Loading audio never starts separation. Before splitting, play/export use the
   loaded audio directly.
5. Adjust EQ, Speed, Pitch, fades and the stem mixer. Advanced contains Q and
   Limiter. Settings contains output preferences, Loop, README and Environment Check.
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
9. Open or drop another audio file to replace the current one without a save prompt.
   New audio starts with default adjustments and a new Undo/Redo history. Close the
   app when done; each launch starts empty. Export audio to keep your result.

Help and Controls
-----------------
Hovering a control does not open a help popup. This README contains the control
instructions; Settings > README opens the local copy in your default text viewer.
Settings > Environment Check shows the available audio tools and local model/runtime.
Task progress, saved files, cancellation and errors stay in the top status area;
click a shortened message to see its full details, or a saved result to open its folder.

The settings/sliders icon beside Open Audio opens output and playback preferences.
M excludes a stem from the mix; S includes only soloed stems when any Solo is on.
Mute takes precedence over Solo. Q (Advanced) controls filter width/resonance:
higher values narrow the bell or increase pass-filter resonance. Speed is a
percentage (50% half speed, 200% double speed); Pitch is measured in semitones
and changes independently of Speed. See Editing and Monitoring and Output and
Settings below for reset gestures, EQ, fades and four-track export behavior.

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
- All three EQ bands, including High Pass and Low Pass, span 20 to 20,000 Hz.
  Frequency ranges can overlap; crossing High Pass above Low Pass can greatly reduce the sound.
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
- Ctrl+click a frequency number to reset Low/Mid/High to 120/1000/8000 Hz.
  Speed resets to 100%, Pitch to 0 st, and Fade in/out to 0.02 s. Each number
  resets separately with one Undo action, including when Num Lock is enabled.
  Normal clicks/double-clicks still edit/select text; arrows, wheel and vertical
  dragging still adjust the value. Busy or disabled inputs ignore resets.
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
Ctrl+click knob/fader  Reset EQ gain/slope or stem volume (also on its value)
Ctrl+click number      Reset frequency, Speed, Pitch or Fade to its default
Right-drag             Select a waveform range
Drag left/right edge   Adjust selection start/end (either mouse button)
Drag top grip          Move selection while keeping its length
Click / drag wave body Move playback position (left button)
Shift+click wave body  Select from the last clicked/dragged seek point
[ / ]                  Mark start/end at the playhead while listening
Mouse wheel on wave    Zoom at pointer
Shift+wheel on wave    Pan waveform
Drag / wheel on number Change value; Shift for finer steps
+ / - / 0              Zoom in / out / fit, while waveform has focus

Working with One File
---------------------
Open Audio (Ctrl+O) or drop a new audio file to switch immediately without a save
question. The current file is replaced after the new file loads successfully.
If loading fails, the previous audio and adjustments remain available. During
processing, a new file request cancels the current task and loads the latest
requested file after that task stops. Cancel can also cancel a pending switch.

Each file starts with default EQ, pitch, speed, fades, stem levels and selection.
Undo/Redo stores up to 100 edits for the current file, grouping each drag. Opening
another file starts a new history; a file switch or a split job cannot be undone.
The app has no project save/open or session recovery. Each launch starts empty.
Closing cancels processing and discards edits. Export WAV/MP3 to keep your result.

Output folder, format, audio quality and playback preferences are remembered.
Original input files and exported audio stay on disk. Working audio created by
this run is cleaned up after replacement or exit when its processing has stopped.
Previous releases and their saved files are not removed by this workflow.

Output and Settings
-------------------
WAV: 44.1 or 48 kHz, 16 or 24 bit PCM. MP3: 128/192/256/320 kbps.
Defaults: 48 kHz / 24 bit, MP3 320 kbps, Loop on, Normalize off, Limiter on.
WAV and MP3 share Save folder and preserve original Unicode filenames.
Working audio and stems from the bundled Demucs runtime use float32. Split Stems
preserves the model's original levels, including peaks above 0 dBFS, instead of
turning down each loud stem independently. The existing playback/export Limiter
still applies. Float32 stem files use about twice the space of 16-bit stems.
An executable-only external Demucs fallback retains its own level handling;
the processing log identifies this fallback.

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
export removes owned temporary audio and clears the current file. Original input
files and exported audio are preserved. Open the input again to start another edit.

Running on Another PC
--------------------
Copy the entire application folder, not just the EXE, to a writable folder on a
Windows x64 PC. It includes FFmpeg tools and an app-local Python/Demucs runtime.
Python imports are confined to that runtime; the package no longer relies on
the developer's Python installation path. Public packages do not include the
Demucs model, so the first split downloads it.
The local release/compact-fix30/KWAK Split folder contains the model downloaded
for local use: do not publish it. To publish, build a public package and provide
its source/ materials beside it; see docs/license-compliance.md.
Set Save folder for the destination PC. Open the input audio to start editing.
An independent laptop run, audio-device listening and physical DPI transitions
have not been observed by automated local QA.

Source and each release have their own settings, temporary audio, output and logs.
For current scope and final verification, see project.md and docs/qa/stabilization/verification.md.
Historical implementation records are available in Git history.
