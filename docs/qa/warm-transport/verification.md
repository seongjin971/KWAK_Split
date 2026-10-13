# Prepared playback and retained pause verification

Date: 2026-10-02. Status: `USER_REVIEW_READY` — compact-fix17.

## Playback changes

The app opens a Windows PCM output device asynchronously during startup and
keeps it for the app lifetime. While idle, one worker prepares the current
source/mix, selection, cursor and effects into a bounded paused queue. No audio
is sent to the speakers by preparation. One latest request replaces stale work;
generation checks prevent old workers from writing to or resetting a new stream.

Space pauses the device and retains its queued samples, decoder, filter state
and source clock. Resume restarts that same queue. Paused edits, seeking and
selection changes prepare fresh PCM at the paused/requested source position.
Pending live commands or seeks invalidate the old queue instead of relabelling
it with settings that have not yet reached the audio. Play can be cancelled while
preparation is still running. Device opening and decoding never block Tk.

The native output uses WinMM pause/restart and its sample clock. The queue is
bounded to approximately 120 ms, with a small additional handoff packet during
seeks. This differs from reducing FFplay's former buffering: playback is paced
directly from the native device clock. Buffer memory remains owned until the
driver returns it; reset releases buffers before files or the device are closed.
Export retains the existing FFmpeg rendering path. Unavailable native output
retains the FFplay fallback. No additional redistributable library is required.

## Measurements

[Source transport check](source-transport.json): real generated Tk Space events,
six source and six four-stem cycles, one retained Windows output device. The
device receives muted PCM; measurements use its real playback clock, without
claiming a physical key-to-speaker or listening test.

| Median | Source | Four stems |
| --- | ---: | ---: |
| Play handler | 1.7 ms | 1.6 ms |
| Play including paint | 2.5 ms | 2.9 ms |
| Device clock advances after Play | 19.3 ms | 22.1 ms |
| Pause including paint | 9.2 ms | 17.2 ms |

Observed maximum device advance was 30.0 ms for source and 39.3 ms for four stems.
All twelve cycles retained their decoder between pauses, froze the cursor/device
clock during pause and used the same device throughout source/mix changes.
[Additional device measurements](native-clock-diagnostic.json) recorded ten
resumes with 16–31 ms device advance. Initial device opening itself measured
about 664–828 ms on this driver; it occurs in the background during app startup.
Pressing Play before preparation finishes can still require that preparation.
The previous FFplay/SDL-dummy clock results use a different measurement path
and are not a direct physical-latency comparison.

## Source verification

[Native EQ/mixer self-check](source-native-eq.json) passed gain changes, twelve
filter/mode/slope changes, mixer gain/Mute/Solo, clock continuity and cleanup.
[Native seek self-check](source-native-seek.json) passed twelve forward/backward
handoffs at half/normal/double speed with pitch changes, matching export PCM
windows, concurrent edits and cleanup.

The retained-device engine tests compare the complete captured stereo PCM with
an uninterrupted reference across multiple pauses, four stems, EQ, three speeds
and pitch changes. They also verify cancellation, stale-session isolation and
releasing prepared input files before cleanup. UI checks cover paused edits,
rapid Space, pending-start cancellation and recovery from preparation/device
errors.

[Regression summary](regression-summary.json): 350 unique primary tests and
22 subtests passed, with two skips and no unresolved failures across the full
suite and targeted corrective reruns. Both skips require Windows symlink
creation privileges. The initial full run recorded eight
failures and one setup error. Old mocks and assertions assumed pause destroyed
the player or no silent preparation existed; those fallback fixtures now
explicitly select FFplay, while native tests verify retained PCM and clocks.
An intermittent Tcl initialization error passed in isolation. Original logs are
retained in [full run](full-regression.txt), [corrective run](corrected-regression.txt)
and [lifecycle rerun](final-lifecycle.txt).

The native engine fixture retains one device across cases, matching the app's
lifecycle. Reopening a device for each initial case had two first-resume timing
outliers above 150 ms; those original runs remain recorded. Retained-device
checks keep the same 150 ms bound and passed in the focused and full runs.
The response measurements above apply to prepared playback, not cold opening.

## Packaged verification

[Frozen-source verification](frozen-source-verification.json) confirms all
16 shipped modules match source. [Isolated release checks](release-smoke.json)
passed real-Tk transport, native EQ/mixer, native waveform seeking, FFplay
fallback EQ/mixer and startup/exit. Development Python and its search paths were
excluded. The packaged Demucs runtime import check also passed.

[Packaged transport measurements](frozen-transport.json) used one muted Windows
device across all twelve play/pause cycles:

| Median | Source | Four stems |
| --- | ---: | ---: |
| Play including paint | 2.1 ms | 2.5 ms |
| Device clock advances after Play | 20.8 ms | 21.8 ms |
| Pause including paint | 12.1 ms | 10.1 ms |

Maximum device advance was 30.3 ms and 34.0 ms, respectively. Every pause froze
the device clock and cursor; resume retained the same decoder. Held Space toggled
once and closing released the stream workers and output device. These are
muted clock checks, not an audible or physical keyboard-to-speaker test.

The build completed and produced the verified EXE. Its outer Windows PowerShell
redirection returned code 1 because PyInstaller's stderr INFO output was wrapped
as NativeCommandError; the retained build logs show completed EXE/COLLECT,
successful bundled-runtime imports and the final build-complete message.
All independent frozen-code and executable checks above passed.

## Session and delivery

The latest saved fix16 session changed during implementation, so migration used
a fresh [pre-migration snapshot](preserved-session-before-migration.json), keeping
the original snapshot as history. No source-release settings or recovery files
were overwritten. [Migration manifest](session-migration/manifest.json) verifies
all five copied audio files. [Isolated Tk restoration](session-restore-qa/restored-session-results.json)
preserved edits, the four stems, selection and Save folder without playback or
export of the user's audio. The root launcher selects fix17; fix16 is retained.
The [final delivery check](final-delivery-verification.json) records hashes,
session preservation, documentation sync and the launcher target.

## API references

- [Windows pause preserves the current position](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutpause)
- [Windows resume](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutrestart)
- [Device position and clock formats](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutgetposition)
- [Reset releases pending buffers](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutreset)
- [Buffer ownership and completion flags](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/ns-mmeapi-wavehdr)
