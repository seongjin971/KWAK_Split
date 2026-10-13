# Post-effects playback spectrum

Final version: compact-fix30. The spectrum follows the same post-mix,
post-EQ/effects PCM sent to the player, with a fixed dBFS scale.

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

The [final regression and package checks](qa/stabilization/verification.md)
include the spectrum tests. Generated PCM and FFmpeg/FFplay tests cover fixed
levels, antiphase stereo, EQ, gain/Mute/Solo, pass filters, pitch, limiter,
playback clocks, bounded buffers and pause/seek/loop/close behavior. An injected
analyzer failure must leave playback running.

Earlier per-feature captures, timing observations and session migration records
are historical Git material. This final package starts empty and does not
restore projects. Subjective listening and another-PC verification remain
outside the recorded automated checks.
