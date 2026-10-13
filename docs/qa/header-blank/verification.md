# Blank header correction

Date: 2026-10-03. Status: `USER_REVIEW_READY` — compact-fix23.

Scope: remove the white bar shown beside the logo. Preserve task feedback and
the current interaction/layout. Check the current display only.

## Reproduction and change

The source app reproduced a white 1052x34-pixel rectangle at the status label
after startup. Tk reported that the label was unmapped and contained no text;
its configured background was already the correct dark header color. This was
a stale display region, not a progress bar.

HeaderStatus now keeps the empty label mapped and painted. Empty status uses
the arrow cursor, has no keyboard focus and ignores activation. Text, percent,
Cancel, saved-file links and full error details remain available when needed.
The before/after source windows were inspected using native Computer Use at
the current 2000x1400 client size / 200% scale. The white rectangle disappeared.

## Verification

[Source check](source-header.json) passed startup, generated audio loading and
WAV export, six feedback states, cancellation, saved-file/error activation and
return to empty status after Ready/Playing/Stopped messages. Geometry and edits
stayed stable with no callback errors. Empty-area clicks open no dialog.

The current-display QA option reuses the existing header checks without running
the FHD/QHD/4K matrix. No new general-purpose tests or display expansion.

[Frozen header checks](frozen-header.json) and [startup/exit](frozen-checks.json)
passed with development Python excluded. The final packaged startup window was
also inspected through native Computer Use: the header is dark, the logo and
buttons are visible, and the white rectangle is absent. All [24 frozen modules](frozen-source-verification.json)
match the final source. No audio engine changes or resolution matrix were needed.

[Session migration](session-migration/manifest.json) copied the latest fix22
source-only session with matching audio hashes. [Isolated restoration](session-restore/restored-session-results.json)
preserved edits, the 0..238.956563-second selection and Save folder, without
playing or exporting user audio. The root launcher selects fix23. Earlier
release/settings/session hashes and final documentation copies are checked in
[final delivery verification](final-delivery-verification.json).
