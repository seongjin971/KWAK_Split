# Ctrl+click reset for numeric inputs

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix26.

Scope: the seven numeric inputs shown in the user's screenshot. Current display
only; no additional resolution/scaling matrix. UI instructions remain in README.

## Change

Ctrl+left-click resets the clicked input using shared project defaults:

| Input | Default |
| --- | --- |
| Low frequency | 120 Hz |
| Mid frequency | 1000 Hz |
| High frequency | 8000 Hz |
| Speed | 100% |
| Pitch | 0 st |
| Fade in / Fade out | 0.02 s each |

The value changes on press; release commits one Undo action. The gesture consumes
the native spinbox action and subsequent drag even if Ctrl is released before
the mouse. Disabled/busy controls do not reset. Normal typing, double-click text
selection, arrows, wheel and vertical scrubbing retain their existing behavior.
Existing variable traces continue to handle effect updates.

## Verification

[Focused real Tk tests](pytest.xml): **14 passed**. Coverage includes all seven
defaults with Num Lock on/off, one-step Undo/Redo, repeated resets adding no
history, Ctrl released before a held drag, clicks over spin arrows, incomplete
text recovery, busy/disabled guards, and existing numeric/knob/fader gestures.

[Source QA](source-numeric-reset.json) and [frozen QA](frozen-numeric-reset.json)
passed all seven numeric resets at the current 2000x1400 client / 200% scale.
Both use generated Tk events with Ctrl+Num Lock (state 12), generated audio and
isolated settings. Range/cursor stayed unchanged; no callback errors occurred.
These are widget event checks, not physical mouse or listening tests.

[Frozen startup/exit](frozen-checks.json) passed with development Python excluded.
All [26 embedded modules](frozen-source-verification.json), including numeric
gestures and their packaged QA entry point, match current source.

EXE SHA-256: `ea5036f38004e4844282aaf4f580b390ef450d898f1c616fcc58a98ffd052c38`.

[Session migration](session-migration/manifest.json) copied the latest fix25
source-only session with matching audio hashes. [Isolated restoration](session-restore/restored-session-results.json)
preserved its edits, 20.24..238.956563-second selection and Save folder without
playing or exporting user audio. Earlier files remain intact. The root launcher
selects fix26; its packaged launcher uses the adjacent executable. Source,
package, documents and session integrity are recorded in [final verification](final-delivery-verification.json).
