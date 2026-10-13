# Final verification - compact-fix30

Date: 2026-10-13. Final version accepted by the user. Baseline checkpoint:
`3a11256`; subsequent stabilization preserves the model, audio settings and
lightweight file workflow. Repository cleanup changes no application behavior.

## Results

- [Full suite](full-suite.xml): **426 passed, 2 skipped, 22 subtests passed**,
  478.39 seconds; no failures or setup errors. Both skips require Windows
  symlink permissions and were present before this work.
- [Frozen source identity](frozen-source-verification.json): all 30 embedded
  modules and the standalone Demucs runner match the verified source.
- [Frozen UI checks](frozen-checks.json): the actual EXE passes file replacement,
  edit reset, WAV export, owned-temp cleanup, empty restart, retained preferences,
  header feedback/cancellation and source/four-stem range-playback interactions.
- [Bundled engine integration](packaged-ui/release-results.json): EXE startup,
  isolated bundled runtime imports, then source Tk UI with bundled engines;
  actual separation into four two-second stems, mixed and individual WAV/MP3
  exports, and dummy-device play/pause/resume passed. The engine integration is
  distinct from the frozen UI checks above.
- Independent standards/correctness and spec reviews found no actionable issues.

## Stabilization and measured optimization

Float waveform preparation aggregates bucket extrema without changing channels,
frequency content, peaks above unity or bucket boundaries. A cancelled waveform
job exits before launching a probe/decoder; process cleanup is retained.

For the same 206.31-second file and 4096 stereo buckets, three measured runs per
version gave medians of **2.702 seconds before / 0.624 seconds after**. All peak
pairs matched exactly. [Measurement record](waveform-after.json). This stage is
4.33 times faster; the AI separation settings/speed were not optimized.

The eight older UI failures were obsolete expectations. Updated tests check the
accepted painted empty header, actual canvas gestures, right-click preservation
and stem coverage. A minimal Tk-only probe reproduced intermittent Tcl startup
errors with pytest FD capture (2 failures in 400). Python-output capture passed
400/400, and is now the default in pytest.ini. No retries, new skips or product
lifecycle/GC changes were introduced. Focused checks passed 23/23 before the full
suite. Earlier raw reproduction logs were moved out of the workspace during
final cleanup; the Windows Recycle Bin retains them for recovery.

## Scope and limits

Checks used generated audio, isolated preferences and muted/dummy playback.
Current-display EXE captures were inspected at 2000x1400 client size / 200% scale.
Physical input, other displays/PCs and subjective listening were not tested in
this pass. The 60.03-second historical split of a 206.31-second source was an
amplitude-validation run, not an optimized-speed benchmark.

Cleanup retains this summary and five small result files. Historical QA/source
snapshots through the checkpoint also remain in Git history; new QA output is
ignored unless it is an explicitly retained final result.

After cleanup, 16 focused tests passed and all 428 tests were collected. The
final executable still matches all 30 source modules and its standalone runner;
its SHA-256 is unchanged. A fresh frozen lightweight-workflow check passed file
replacement, edit reset, empty restart, retained preferences and WAV export.
Cleanup changed no application code. Local cleanup receipts and retained user
files are excluded from Git.
