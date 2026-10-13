# Smooth window resizing

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix19.

Resumed after the user's safe-stop request and subsequent explicit resume.
The historical checkpoint and all earlier diagnostic artifacts are retained.

The editor is captured once before Windows starts sizing. During a border drag,
a native child scales the same bitmap with halftone filtering. It does not
rebuild every control/graph for each intermediate size. When sizing ends, the
real editor is laid out once and revealed; text and controls become sharp and
interactive again. The picture temporarily freezes cursor/spectrum/status
animation, while audio and background work continue. Final drawing can still
take a few tenths of a second after release.

The snapshot stays in memory and comes from this editor's client HWND. All GDI
capture handles are released, and image/native-window callbacks are cleaned up
on close. Capture or image-allocation failure retains normal live layout.
Redundant geometry, font/style, metadata and canvas repaints are also batched.
The existing 10:7 bounds, proportional controls and no-scroll layout remain.

## Measured source response

The same 44 generated native size changes were measured in isolated Tk windows
with generated audio. These are completed UI-frame timings, not physical mouse
latency or a guarantee of constant refresh rate on every computer.

| Loaded state | Before median / p95 | After median / p95 |
| --- | --- | --- |
| Flat EQ | 580.2 / 666.5 ms | 23.7 / 28.0 ms |
| Active EQ | 590.1 / 679.8 ms | 25.6 / 28.7 ms |

Sources: [before](before.json), [after](after.json). Capture took 3.8–4.5 ms;
final reflow after release took about 311–317 ms in that comparison. Intermediate
batching alone was insufficient; its measurements remain in `batched.json`.

[Final source resize QA](source-resize-verified.json) checks empty and loaded
projects, source and four-stem playback, exact complete-snapshot pixel coverage,
capture/allocation fallback, updated status after release, and close with a
queued frame. Both playback cases retained the same audio stream and advanced
the native audio clock while resizing. Twenty repeated captures retained exactly
32 GDI objects before/after. Actual native SC_SIZE modal entry/exit passed for
both Enter and Escape, using generated size messages on the isolated QA HWND.
No physical mouse gesture or listening test was performed.

FHD/QHD/4K at 100/125/150/175/200% app DPI passed 15 resize/bounds combinations,
including a screen-limited window with no available resizing range. Work areas
and app DPI were simulated; Windows display settings were not changed. Large
size jumps are slower: the 4K/200% jump to 2800x1960 took about 89 ms in this run.
The earlier Tk image-copy prototype took about 170 ms for that case. The
[preview](source-resize-verified-preview.png) and
[restored controls](source-resize-verified-restored.png) were visually inspected.

[Header regression](source-header-status.json) passed 45 initial/minimum/maximum
display cases with six status states each, cancellation and full-detail actions.
[Regression summary](regression-summary.json) records 101 unique tests and seven
subtests passing across focused checks and corrective reruns. The initial run
had one intermittent Tcl startup failure (passed in a fresh process) and one
missing-client mixer test failure. That test now clears any prepared decoder
before injecting the missing client and asserts that the client is actually
absent; all four mixer tests then passed. Audio behavior was not changed for it.
Initial failures and rerun logs remain available.

## Package and session

[Build](build-result.json) completed successfully, including import verification
of the app-local Demucs runtime copied from fix18. [Frozen-source comparison](frozen-source-verification.json)
matches all 21 modules to the checked source. [Isolated executable checks](release-smoke.json)
passed with development Python and its search paths excluded:
[resize](frozen-resize.json), [45 header cases](frozen-header.json),
[Space transport](frozen-transport.json), and startup/exit. The packaged preview
and restored controls were also captured and visually inspected. The native
resize check retains one stream through resizing, and transport retains the
same device/decoder through pause/resume. Audio testing used muted generated
signals; no subjective listening result is claimed.

The latest saved fix18 session contains source audio and no separated stems.
[Session migration](session-migration/manifest.json) copied that current state
with a matching audio SHA-256, preserving fix18. [Isolated restore](session-restore-qa/restored-session-results.json)
confirmed edits, the 0–238.956563 selection and Save folder without playing or
exporting user audio. The root launcher selects fix19. [Final delivery checks](final-delivery-verification.json)
record module/EXE hashes, retained fix18 files, restored session, documentation
sync, license copy and launcher target.

Pillow 12.3.0 is included for image handling; the wheel's complete license is
preserved under `LICENSES/pillow/`. This implementation follows Microsoft's
[client bitmap capture pattern](https://learn.microsoft.com/en-us/windows/win32/gdi/capturing-an-image)
and Pillow's [Windows device-context drawing API](https://pillow.readthedocs.io/en/stable/reference/ImageWin.html).
