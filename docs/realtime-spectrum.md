# Post-effects playback spectrum

Date: 2026-09-30
Status: **USER_REVIEW_READY — compact-fix6**

The user requested a live spectrum that visibly follows audible EQ cuts and
boosts. The analyzer observes the same post-mix, post-EQ/effects PCM sent to
the player. It must not approximate output by multiplying an unprocessed display
by the EQ curve, or normalize every frame and hide changes in level.

## Delivery order

1. Preserve the existing working tree and fix5 package/session.
2. Add bounded, asynchronous PCM analysis and playback-clock synchronization.
3. Draw the output spectrum behind the existing editable EQ curve. EQ gain uses
   the left axis; output level uses a fixed dBFS scale on the right.
4. Verify measured cuts/boosts, filters, stereo, mix selection, speed/pitch,
   pause/seek/restart/loop/close, and responsive actual Tk captures.
5. Run regressions and build a separate `compact-fix6` package, verify it, copy
   the current session with hashes, and update the launcher.

All audio QA uses generated signals and isolated settings. Existing user audio,
projects, settings, output, accepted HTML references and historical releases are
preserved. A backup of the pre-change source is under
`backups/before-spectrum-20260930-020647`.

## Display and behavior

- Display the final audible preview mix, including stem gain/Mute/Solo, EQ,
  speed/pitch, selection fades and limiter. Export-only normalization retains
  its existing behavior.
- Use fixed 20 Hz–20 kHz frequency and -90–0 dBFS level scales. Never rescale to
  the loudest bin in each frame. Combine stereo channel power without cancelling
  opposite-polarity content.
- Keep EQ handles and the response curve readable above the spectrum. No new
  transport controls are needed.
- Clear old data on pause, source/selection changes and playback restart. Do not
  display decoded audio ahead of its playback time. Keep buffers bounded and
  audio forwarding independent of FFT work and Tk redraws.
- The fallback player analyzes its actual rendered WAV. Analysis failures must
  not stop audible playback and must be reported without repeated dialogs.

## Verification

All five delivery steps above are complete. Evidence: `docs/qa/spectrum/`.

- `pytest-full.txt`: **208 passed, 1 skipped, 19 subtests passed**, 240.13 seconds.
  The skip requires Windows symbolic-link permissions. No OS setting was changed.
- Tests use generated PCM and real FFmpeg/FFplay. They verify fixed dBFS gain,
  antiphase stereo, EQ ±12 dB, gain/Mute/Solo, pass filters, pitch, limiter,
  exact matching windows of processed audio, player clock, bounded memory,
  pause/resume/seek/source changes, loop, fallback and worker/process shutdown.
  An injected analyzer failure leaves playback running.
- `ui-results.json`: the same 1 kHz tone plus noise measured **+12.05 dB** and
  **-12.06 dB** after ±12 dB EQ edits. `bundled/ui-results.json` measured
  **+12.10 dB / -11.89 dB** using the release's engines. Noise varies between
  successive windows; the pure-tone regressions use a tighter 0.12 dB tolerance.
- Actual Tk captures show flat/boost/cut and paused states, 1000x700, 760x620 and
  640x480 windows. Labels stay inside the canvas and EQ handles remain usable.
  The release QA also captured automatic 200% app scaling. Captures are in
  `captures/`, `bundled/captures/` and `release/captures/`.
- An 8192-sample Hann window is analyzed asynchronously using a standard-library
  stereo FFT. Mean FFT work was about **14–16 ms** in these captures. Audio
  forwarding has no FFT or Tk work, the analysis queue holds at most two windows,
  and decoded lookahead is bounded to 350 ms. This is local timing, not a
  benchmark for every PC or music track.

## Package and preserved session

- Package: `release/compact-fix6/KWAK Split/KWAK Split.exe`.
- EXE SHA-256: `d6777e7309791bd1b20cd93368e2d9059929f79aa4e4428e21f1117703f4bf2f`.
- `frozen-source-verification.json`: all seven relevant modules match the tested
  source. `bundled-assets.json`: three FFmpeg tools and the Demucs model match
  the verified fix5 package. No additional dependency was introduced.
- `release/release-results.json`: EXE startup/exit 0, isolated packaged runtime,
  actual four-stem separation, mixed WAV/MP3 and four individual files of each
  format, dummy-device play/pause/resume. The generated two-second separation
  took 31.203 seconds; this is a workflow check.
- `session-migration/manifest.json`: the **latest September 30 saved session**
  was copied, including five audio files (226,044,392 bytes), settings and recovery.
  Original files are preserved; the new recovery refers to audio within fix6.
- `restored-session-results.json`: edits, all four stems, selection
  **0–207.456 seconds**, Save folder and available Export were retained in an
  isolated real-Tk restore. The seven transferred files kept their hashes.
- The launcher selects fix6. Close the old app, run `Run KWAK Split.cmd`, and
  press Ctrl+Shift+R to resume. Save with Ctrl+S for a permanent project.

## Verification limits

The EXE was smoke-tested; workflow and spectrum tests used real source Tk with
the bundled audio engines. Frozen-source matching confirms the code is packaged.
These checks do not claim native mouse/key acceptance of the EXE, human listening,
physical monitor/DPI transitions or another-PC operation. Tests used a silent
dummy audio device and did not play, re-split or export the user's music.
