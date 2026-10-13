# Cubase-style knob and fader reset

Date: 2026-10-01. Status: `USER_REVIEW_READY` — `compact-fix11`.

## Reference and behavior

Cubase's documented default modifier for restoring controls is Ctrl on Windows,
and its MixConsole instructions specify Ctrl+click on a fader. This request
adopts that gesture for KWAK Split's EQ knobs and stem volume controls.
[Steinberg control modifiers](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/preferences/preferences_editing_tool_modifiers_r.html),
[Steinberg MixConsole volume](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/mixconsole/mixconsole_setting_volume_c.html).

- Ctrl+left-click on an EQ knob or its value: Shelf/Bell gain to 0 dB, or
  High Pass/Low Pass slope to the app's 24 dB/oct default.
- Ctrl+left-click on any stem fader or its value: volume to 0 dB.
- The prior double-click reset is removed from those knobs, faders and value
  labels. Ordinary clicking/dragging/wheel input and text-field editing remain
  available; Home remains the focused knob/fader's keyboard reset.
- Reset consumes the click without jumping the fader track. Moving the mouse
  after resetting, even after releasing Ctrl, does not start a parameter drag.
- Each reset is one Undo action. Busy/disabled controls and unavailable stems
  reject reset input. The default-closed Help now describes Ctrl+click.

This is the requested knob/fader reset convention. Cubase's graphical EQ editors
have additional gestures; for example, StudioEQ documents Ctrl-drag on a graph
handle as gain adjustment. No graph gesture was remapped by this change.
[Steinberg StudioEQ](https://www.steinberg.help/r/cubase-pro/cubaseplugref/15.0/en/_shared/topics/plug_ref/studio_eq/studio_eq_r.html).

## Verification

Targeted native-Tk gesture checks cover all 14 EQ knob/stem fader/value targets,
gain and Pass defaults, one-step Undo/Redo, movement after resetting, ordinary
double-click behavior, disabled/busy states, and normal fader track dragging.
The first targeted run passed three tests with one system-Tk setup error;
that exact test passed in isolation.
[Targeted run](targeted-tests.txt), [targeted rerun](targeted-rerun.txt).

The broader numeric/keyboard/workflow/edit suite recorded 28 passes, one keyboard
focus assertion failure, and one system-Tk initialization error. The focus test
passed in isolation. The remaining test passed using the release's bundled
Tcl/Tk libraries after the installed Python library read failed again. All
**30 tests passed across those runs**; the initial run did not have a clean exit.
[Interaction run](interaction-tests.txt), [rerun](interaction-rerun.txt),
[bundled-Tk rerun](bundled-tk-rerun.txt).

Real Tk windows with generated audio and fixture stem references verified
Ctrl+click on every requested target and recorded
[before](captures/before-reset.png)/[after](captures/after-reset.png) captures.
[UI results](reset-ui-results.json). These are generated Tk events and source-app
captures, not claims of direct native mouse acceptance in the EXE.

The separate fix11 package built with the verified fix10 app-local runtime.
Its EXE started and closed normally without development Python; all nine frozen
modules match the tested source.
[Build](build.txt), [build stderr](build-stderr.txt),
[EXE smoke](release-smoke.json), [frozen source](frozen-source-verification.json).

## Saved session and launch

The latest saved fix10 snapshot contains the source audio and four separated
stems, selection 0–207.456 seconds, edits and the existing Save folder. All five
audio copies and JSON writes have matching SHA-256 hashes. The older release's
source files, settings and recovery were preserved.
[Transfer manifest](session-migration/manifest.json).

Isolated recovery restored all four stems with Export enabled, preserved edits
and selection, and reported no callback errors or changes to user-session hashes.
[Restore result](session-restore-qa/restored-session-results.json).

Close the old app and run the root `Run KWAK Split.cmd` to launch fix11.
Press **Ctrl+Shift+R** to restore the transferred saved session.
