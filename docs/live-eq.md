# Continuous EQ, stem mixer and waveform seeking

Frequency, gain and Q edits use named FFmpeg filter commands on the existing
decoder/player. This includes Bell/Shelf bands, moving from 0 dB, and the cutoff
and resonance of High Pass/Low Pass filters. The spectrum
continues to observe the same post-effects audio sent to the output device.

Filter kinds, pass enable/disable and 12/24/36/48 dB/oct slopes also keep the
same playback processes. Two permanent EQ banks each contain the Bell/Shelf
alternatives and four sections per pass filter. A mode/slope change configures
the inaudible bank, allows 30 ms for its state, then crossfades over a nominal
40 ms. The crossfade advances by at most 10 percentage points per acknowledged
command; delayed scheduling extends the fade instead of jumping over it.
Both weights are sent in one quoted `amix weights` argument and sum to
one. The previous filter continues to play during preparation, avoiding an
unfiltered intermediate signal. Rapid changes retain only the latest requested
state after the in-progress transition.

Stem volume, Mute, Solo and Ctrl+click resets also keep the running processes.
All available stem inputs stay in the graph, including muted and zero-volume
tracks, so unmuting preserves their sample position. One named `amix` receives
all weights in a single command with normalization disabled. A nominal 40 ms
linear-gain ramp changes the whole set together. This avoids intermediate
all-off/doubled levels when exchanging Solo tracks. All-muted playback continues
silently, including when Play starts with every track muted. Export retains its
existing audible-track selection and Mute-over-Solo rules.

Waveform clicks and left drags also keep the output player open. A background
worker opens another decoder at the requested source position while existing
audio continues. After receiving its first PCM block, the relay crossfades over
10 ms into the prepared audio. The output device, its clock and the spectrum worker
remain running; the decoder and its filter controller are replaced. All stem
inputs open at the same source-relative offset with the current EQ/mixer state
and selection-anchored fades. Edits arriving during preparation are forwarded
to the incoming controller as well.

One preparation can be in flight and one latest pending position is retained.
Completing the in-flight handoff lets audio change during fast held drags;
intermediate pending positions are coalesced. A continuous output timeline maps
each handoff back to source time, including half/double speed and pitch changes.
The cursor stays at the requested position until output reaches the handoff.
Spectrum frames still represent the PCM actually sent to the player. Source
replacement and full stop cancel pending work and release all decoders. Native
Space pause retains the decoder and output queue for immediate resume when
there is no unfinished seek/control update. Otherwise it prepares the latest
settings at the paused position. App close also releases the retained device.
Preparation has a three-second first-PCM deadline; failure keeps the current
playback and reports an error in context. The rendered-WAV fallback retains its
previous restart path. Right-drag selection keeps its established behavior.

Mixer and EQ retain separate latest values on the same command worker. Mixer
updates are serviced during EQ bank preparation/crossfading. Both UI throttles
are cancelled on pause/stop; changed input files or ranges use the rebuild path.

The UI schedules at most one update per 16 ms, including throughout a held drag.
One background worker owns the local ZMQ client and retains only the newest
desired values. A 40 ms parameter ramp uses logarithmic frequency/Q and linear
dB. This is a bounded command ramp, not sample-accurate DAW automation. Commands
have a two-second acknowledgement deadline and can be interrupted on stop.

The native Windows output keeps an approximately 120 ms queue, paced directly
from the device sample clock. The FFplay fallback retains 240 ms of output
lookahead: reducing its buffering to 120 ms caused silent-device underruns.
FFmpeg/player pipes are unbuffered, partial writes and stereo frame alignment
are handled, and output packets are flushed. Preview and export both retain
unity EQ stages in f64 precision and use the same 256-sample filter blocks; otherwise Rubber Band
can produce different results from different filter formats/block boundaries.
The explicit precision also preserves flat EQ and sample-accurate fade envelopes
when exporting or resuming a partial range.

Tempo, pitch, fades and limiter changes retain their previous
restart behavior. EQ/mixer edits while tempo/pitch are active keep playback running,
but Rubber Band's lookahead can delay the audible response, notably at half
speed. Neither queue setting is a measured end-to-end latency guarantee.

Missing PyZMQ in a source checkout retains the earlier restart behavior. A
command error is logged, shown in context and reapplies the latest settings
through that path. The packaged app includes the command client and DLLs.

References:
- [FFmpeg EQ runtime commands](https://www.ffmpeg.org/ffmpeg-filters.html#equalizer)
- [FFmpeg azmq](https://www.ffmpeg.org/ffmpeg-filters.html#zmq_002c-azmq)
- [FFmpeg amix weight commands](https://www.ffmpeg.org/ffmpeg-filters.html#amix)
- [PyZMQ thread ownership](https://pyzmq.readthedocs.io/en/stable/howto/morethanbindings.html#thread-safety)

Play/Pause changes only the transport button and cursor. Task status uses one
fixed-size header cell beside the logo without recomputing editor geometry. An explicit
sentinel wakes an idle spectrum worker on stop, removing its queue polling wait.
Repeated Space key presses are ignored until release; focus loss also releases
the latch. Text inputs and dialogs retain their normal key handling.

Verification: [prepared playback evidence](qa/warm-transport/verification.md),
[transport response evidence](qa/transport-latency/verification.md),
[waveform seek evidence](qa/live-seek/verification.md),
[stem mixer evidence](qa/live-mixer/verification.md),
[mode and slope evidence](qa/live-eq-modes/verification.md) and
[initial continuous EQ evidence](qa/live-eq/verification.md).
