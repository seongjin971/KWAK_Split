# Numeric editing, EQ, fades and stem coverage

Date: 2026-09-17

## Requested behavior and diagnosis

- Keep Start/End and selection length at two decimal places. Cubase supports milliseconds and samples, but the user explicitly chose centiseconds for this lightweight tool.
- Make time wheel/drag increments follow zoom. A roughly 207-second view uses 2-second wheel steps; a 1-second view reaches the 0.01-second minimum. Shift refines coarse steps without adding displayed decimal places.
- The graph already covered ±24 dB, but UI gain was capped at ±12 and the FFmpeg helper at ±18. Both now use ±24. Pass slopes remain 12/24/36/48 dB/oct; Advanced Q retains its independent meaning.
- The compact waveform previously drew unfaded amplitudes. It now shows attenuated peaks plus amber envelopes and visible endpoint markers for subpixel fades. Seeking/resuming and shortened fallback previews previously restarted or compressed fades; fades now remain anchored to the full selection.
- Vertical scrubbing and wheel editing cover Start/End, frequencies, Speed, Pitch, fades, Q, EQ/fader readouts and numeric output choices. Normal text input, dropdown arrows, bounds, disabled controls and grouped history are retained.
- A selection-only split contains no stem audio outside its original range. Crossing that range now shows an inline action instead of a blocking preview/render dialog. Settings offers Selection (existing default) and Full track. Neither loading nor range changes starts separation. Valid selections clear the notice; invalid selections cannot silently play/export original audio in place of missing stems.

Official reference: [Cubase ruler display formats](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/project_window/project_window_ruler_display_formats_r.html) and [Cubase EQ](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/mixconsole/mixconsole_eq_r.html). The zoom-dependent editing increments are this app's design, not a claim about Cubase behavior.

## Verification

Commands:

```text
.build\qa\Scripts\python.exe -X utf8 -B -m pytest tests -q --capture=sys -p no:cacheprovider
.build\qa\Scripts\python.exe -X utf8 -B scripts/qa_precision_controls.py
```

**146 tests and 19 subtests passed in 191.19 seconds.** A final timeline-label correction (unique two-decimal labels and correct minute rollover) passed the seven numeric-input cases again in 18.26 seconds before building.

- Audio agent: 21 checks, including measured Shelf/Bell ±24 dB response, old project round-tripping, source-time fades at 50/100/200% speed, seeking within either fade, and shortened fallback playback. At matching 48 kHz, neutral-speed cropped fades match complete exports within a 2e-6 sample error. Rubber Band checks use settled envelope measurements instead of demanding identical startup transients from independently started stretches.
- Numeric agent: seven real Tk event checks cover all editable numeric fields, wheel deltas/Shift/zoom, single-step Undo/Redo, typing/double-click, disabled controls, output dropdown scrubbing, fader reset and fade canvas geometry.
- Workflow agent: ten checks cover split scope, persistence through the actual settings reader and startup initializer, selected/full source audio passed to a synthetic separator, cached coverage, no automatic split, nonmodal playback/WAV/MP3/individual export rejection, and stopping old playback after an invalid selection edit. This audit found a missing settings whitelist entry; it was fixed and retested.
- Six generated-audio window captures were inspected: 1000×700, 760×620, 640×480, the narrow scrolled mixer, a zoomed 20 ms fade, and Settings. No Tk callback errors occurred. Five waveform draws at 1000×700 took 4.55–6.49 ms on this PC; this is a local rendering measurement, not a device-wide performance guarantee.

## Release and native input

`release/compact-fix3/KWAK Split/KWAK Split.exe` was built separately, reusing the verified isolated runtime from fix2. `scripts/qa_compact_release.py --release 'release/compact-fix3/KWAK Split' --evidence-dir docs/qa/precision-controls` passed:

- EXE smoke startup/exit with the development Python path excluded and an invalid external PYTHONHOME.
- Python/Torch/Demucs imports confined to the release runtime.
- Actual bundled Demucs separation into four 2.000-second stems (28.546 seconds locally).
- Direct 48 kHz/24-bit WAV and 320 kbps MP3 export: 1.600-second outputs at 125% speed, with pitch/EQ/fades applied.
- Dummy-device play/pause/resume and automatic 200% DPI sizing (2000×1400 client area).

The new packaged EXE was then exercised with Windows Computer Use. The previous window closed without a dialog; its settings and recovery snapshot were copied to the new package. Restore completed in about three seconds. The real window showed the existing four stems and edits, plus the inline coverage notice. Space while outside stem coverage left Play idle and displayed no modal. A 30-logical-pixel upward Start drag changed 3.22 to 23.22; one Ctrl+Z restored 3.22. A wheel-up notch changed 3.22 to 5.22; Undo restored it. Settings visibly offered Selection and Full track; the existing Selection preference was retained.

After input checks, recovery JSON comparisons confirmed unchanged edits, all four stem references, original stem coverage, and Save folder. The new app remains open and paused. The selection remains exactly as the user left it, outside the previously separated range; splitting the required range (or explicitly choosing Full track) is still needed before that selection can play/export as stems.

Native checks used no new separation of the user's track and created no user-audio export. Physical laptop/monitor switching and direct listening were not repeated; the local regression suite retains the prior viewport/scaling coverage.

## Preservation

The accepted HTML references and earlier releases remain unchanged. Tests use generated audio and isolated workspaces. This revision is delivered in a separate `release/compact-fix3` folder, selected by the root launcher. No push was made.
