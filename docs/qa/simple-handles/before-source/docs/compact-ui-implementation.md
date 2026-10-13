# Approved compact desktop UI implementation

Date: 2026-09-17

## Authorization and preservation

The user approved the UI and requested a completed application, documentation, a baseline commit before implementation, and resizing support from 1920×1080 through 3840×2160. Continue through implementation, validation, and a separate local release. Preserve the earlier release, runtime/models, user settings/audio/projects, all previous source work and QA evidence. Do not reset, stash, force-push, or modify the promotional site.

Accepted design sources (preserve and track all three):

- `output/ui-preview/kwak-split-compact-v2.html`: exact body/style/script fragment.
- `output/ui-preview/kwak-split-preview.html`: independent IDE preview with escaped iframe srcdoc.
- `output/ui-preview/filter-preview/index.html`: decoded inner document, served on localhost:8769.

The fragment must occur unchanged in both inner documents; decoded srcdoc and index must match. These remain the design reference, not the production audio interface.

## Product contract

- The October 3 trackpad update adds click then Shift+click to select between
  source positions. The last explicit click/drag seek is a fixed anchor, unaffected
  by playback or zoom, and does not carry across different audio sessions. Before
  an explicit seek, use the current playhead. Left-drag blue boundaries/the top
  grip to resize/move; a tap there still seeks. Body seeking stays immediate and
  does not switch modes when crossing a handle during a held drag. Shift+click
  keeps the current stream running and changes the next play/loop/export range.
  Preserve right-button behavior, history, point selections and stem limits.
  Evidence: `qa/trackpad-selection/verification.md`.

- The October 3 waveform selection update adds wide, proportional targets for
  independently dragging either blue boundary with the right button. Right-drag
  the small top grip to translate the range without changing its exact length;
  right-drag elsewhere to draw a new range. A click alone preserves the range.
  Off-canvas dragging pans a zoomed timeline. `[` / `]` mark the current audio
  playhead as start/end while playback continues; the new range is used on the
  next playback, loop or export. Keep left-button seeking, input/dialog focus,
  complete-stem bounds and one Undo action per gesture/mark. Display stays at
  two decimals; movement and history preserve precise file/stem boundaries.
  Evidence: `qa/waveform-selection/verification.md`.

- The October 2 resize performance request uses a temporary in-memory editor
  image during native border dragging. Capture the complete client before its
  parent can clip it, scale the original image through a native Windows child,
  then restore live controls once at the final size. Playback keeps its stream;
  cursor/spectrum/status visuals catch up after the drag. Keep aspect/bounds,
  DPI support and no-scroll composition. Batch redundant geometry and drawing.
  Evidence: `qa/smooth-resize/verification.md`.

- Top row: KWAK Split, Open Audio, Settings icon, WAV, MP3.
- Above the stereo waveform: filename, length/channel information; Start, End, selection duration; Play/Pause at right. Left click or left drag seeks; right drag selects; wheel zoom follows the pointer; keyboard shortcuts remain usable without hijacking text entry.
- The October 2 seek request keeps the output player open. A background worker prepares another decoder at the requested source position, then a 10 ms PCM crossfade hands over without restarting the output device. A held drag completes in-flight preparation and retains only the latest pending position. Source cursor and spectrum follow the output clock; EQ, mixer, partial-stem offsets and selection fades survive the handoff. See `qa/live-seek/verification.md`.
- The October 1 waveform request removes L/R text and its reserved left space. Keep the upper/lower stereo channels and draw samples from the visible left edge, including the beginning of zoomed and panned views. Preserve source-time mapping, selection, cursor and fades.
- Equalizer left, Stem Mixer right; Split Stems at the right of the mixer heading. The October 1 request supersedes narrow-window stacking: keep these panels side by side and uniformly shrink fonts, controls, spacing and graphs to fit. Speed, Pitch, Fade in, Fade out are one row under EQ.
- No extra transport bar, selection panel, Project/preset/Loop/Undo/Redo buttons or duplicate persistent status. Loop and output preferences are in Settings. History uses Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z. Existing project data and recovery remain compatible without restoring rejected main-screen controls.
- Low Shelf/High Pass, Mid Bell, High Shelf/Low Pass. Shelf/Bell gain spans ±24 dB in the controls, graph and audio engine. Pass knobs select 12/24/36/48 dB/oct. Q controls resonance separately in Advanced; the response curve and audio filters use the same filter model.
- The September 30 addition overlays a live post-effects output spectrum behind the EQ curve. Left dB labels describe EQ gain; the right fixed -90–0 dBFS axis describes actual stereo output. It follows the player's audio clock and clears on stop/restart. See `realtime-spectrum.md`.
- Production starts with flat shelves and a zero-gain bell, so loading a file does not automatically remove low/high frequencies. The accepted demonstration's 120 Hz / 8000 Hz, 24 dB/oct state remains available by selecting Pass. New audio resets adjustments unless Keep adjustments is enabled. Fades default to 0.02 seconds with 0.01-second steps.
- Stem faders span silence through +12 dB, with 0 dB at 33% from the top and the accepted scale labels. The later October 1 request replaces their double-click reset with Ctrl+click, following the Cubase Windows control default. EQ knobs/value labels and stem faders/value labels reset with Ctrl+click: 0 dB for gain/volume, 24 dB/oct for Pass slope. Reset once per Undo step without starting a drag or jumping the fader track; disabled controls remain inactive. Mute is yellow and Solo red. Mute takes precedence over Solo, matching the accepted preview. Playback and mixed export use the same stem selection.
- Before splitting, play/export use the loaded audio and the stem controls are disabled. Split Stems defaults to the selected source-time range (initially the entire file). Settings offers Full track for one longer split followed by unrestricted selection edits. As of 2026-09-26, complete stems constrain all selection editing and restored history to their available range; choose Full track and explicitly split to expand coverage. Incomplete/unavailable stem audio retains the safety guard and is never silently substituted. No automatic separation.
- Time inputs retain two decimal places by the user's explicit choice. Numeric values support vertical dragging and wheel adjustment; Start/End increments follow the visible timeline span down to 0.01 seconds. Preserve typing, supported-value limits, disabled states and one Undo per drag.
- Show fades by attenuating the waveform and drawing amber envelope lines. A small endpoint marker keeps subpixel fades discoverable without exaggerating their duration. Preview and export fades stay anchored to the selected source range, including after seeking and at different speeds.
- WAV/MP3 export the current selection and mix directly to the shared Save folder with the selected encoding options. Browse opens the real Windows folder chooser. Cancel retains the old folder. Preserve existing files using numbered names. Show completion/path or errors beside the logo; hide the text when idle without moving the header buttons.
- The later four-track-export request adds Export beside Split Stems and Settings > Stem format (WAV/MP3). Save all four stems individually using the selection, faders and shared effects, ignoring Mute/Solo. A silent fader still produces a file. Peak Normalize is independent per stem. Require complete, in-range stems; publish only after all four renders succeed. Keep the accepted HTML references unchanged as historical design sources.
- Playback resumes from the paused cursor. Speed adjusts playback time independently of original selection coordinates; pitch remains independent. Normalize applies on export; limiter and effects apply to monitoring and export consistently.
- Show loading/splitting/export progress and cancellation only while needed. Retain setup/environment/log access in Settings and contextual failures. Keep the UI responsive during work. Delete-working-audio only removes owned temporary audio after successful output, never the source or project assets.

## Responsive desktop contract

- The approved October 1 window policy uses a fixed 10:7 client aspect and a 1000x700 reference composition. Scale fonts, controls, spacing and graphs together when resizing, with EQ and Stem Mixer side by side and no main-editor scrollbar.
- Use monitor work area and DPI to choose the initial window. Bound all windows/dialogs to available space. Scale fonts, targets and drawn controls together.
- The October 2 header decision replaces the lower status reservation with one line between the logo and Open Audio. Show task text and a real percentage when known, with a small Cancel button while busy; omit the progress bar. Keep header height and action-button positions fixed, shorten long text while preserving the percentage, and expose full details on click. Saved-file text opens its folder. Give the reclaimed lower height to EQ/mixer while retaining the 10:7 window ratio. Audio loading, filenames, progress and errors must not change editor geometry or fonts. See `qa/header-status/verification.md`.
- At 100% DPI, use nominal 760x532 minimum, 1000x700 startup and 1400x980 maximum client sizes. Scale these by monitor DPI, subtract decorations and margins from its work area, and reduce even the minimum when necessary to fit. Windows edge/corner resizing and maximization must preserve 10:7 and these bounds; maximize to the bounded size centered in the work area. This supersedes the earlier 480x360 minimum.
- Verify FHD 1920×1080, QHD 2560×1440 and 4K 3840×2160 work areas at Windows-equivalent 100%, 125%, 150%, 175% and 200% scaling. Check startup/minimum/maximum sizes, maximization, reachable controls and contextual progress/errors. Settings and Advanced retain independent sizing and scrollable viewports. See `qa/aspect-bounds/verification.md`.
- Do not change the user's desktop resolution or global Windows scaling during automated QA. Distinguish app viewport/scaling tests from physical multi-monitor/DPI transition acceptance.

## Ordered delivery and evidence

1. U01: inspect baseline; synchronize/check the accepted design; commit existing work and this document.
2. U02: implement shared EQ response/filter coefficients, slope parameters, fader mapping and validation/history support, and real stereo peak extraction. Validate generated audio with objective response/channel/gain checks.
3. U03: implement the approved Tkinter surface, reflow/DPI behavior and functional dialogs; wire real open/selection/play/split/export, settings persistence and context states. Retain earlier backend capabilities and project compatibility.
4. U04: run meaningful existing and new regressions, real generated-audio split/export/playback workflows, inspect actual app captures at viewport/scaling variants, create a separate release, smoke-test it, update launcher/README/project and record evidence.

Automated tests, actual window captures, silent playback-process checks and direct human listening are distinct. Report observed results and any remaining device-specific limits accurately. Final aesthetic acceptance remains the user's judgment; the implementation must already match the accepted design before delivery.

## Implementation record

- U01 checkpoint: `388e2db`, including all earlier dirty/untracked application work, documentation, tests and three accepted previews. No reset, stash or push.
- Native surface: `backend/compact_ui.py` and `backend/compact_widgets.py`; existing processing and project services remain in use through the main app.
- Slopes are cascaded two-pole filters with independently adjustable Q. The response model matches FFmpeg's actual bass/treble coefficient convention as well as Bell and Pass; generated audio validates the curves. Limiter now honors its ceiling without automatic makeup gain or an added output tail.
- Version-1 project input remains supported; omitted slope fields retain the earlier 12 dB/oct behavior. Version 2 stores new slopes and the wider fader range. Existing project assets are preserved.
- Startup and minimum sizes share the same work-area bounds; this avoids a 1080p/200% minimum-height clamp expanding the window beyond the screen.
- The new release bundles a separate interpreter and standard library with isolated import paths, removing the development venv's absolute Python dependency. The original runtime and earlier release remain untouched.
- Detailed results and remaining physical-device checks are in `docs/qa/compact/verification.md`.

## Loading and close correction

The user's subsequent report supersedes the earlier close guard: closing the window immediately cancels active work and closes, retaining a temporary recovery snapshot when possible. It does not require waiting for a job, pressing Cancel first, or responding to an unsaved-project prompt. Permanent projects still use Ctrl+S. A fractional-duration validation error that stranded loading after worker completion is fixed; worker result handling also remains alive after an unexpected UI exception. See `docs/qa/loading-fix/verification.md`.
