# Distribution licensing

Updated 2026-10-14. The owner chose MIT for KWAK Split's original code, retained
the existing Demucs model and separation quality, and put public executable
distribution on hold until the model's redistribution permission is resolved.
Third-party rights are not granted by the root MIT license.

## Public release hold

`LICENSES/distribution-status.json` records the decision and exact model hash.
`scripts/check_distribution.py` rejects public builds while this decision is on
hold. `build.ps1 -LocalOnly` is for non-public development and marks its output
`DO_NOT_DISTRIBUTE.txt`. Omitting the weights is not a workaround: the unchanged
Demucs runner can download the same model on first use.

The previous GitHub release `v1.0.0` (release ID 333222423) was changed from public
to draft on 2026-10-14. Its ZIP asset ID 436372026 was preserved. An unauthenticated
API check then returned no public releases. Before/after receipts are retained
locally under `backups/license-remediation-20261014/`, excluded from Git.
This prevents new public downloads; it does not erase earlier copies or resolve
historical obligations. Do not re-publish the old ZIP as a substitute for the
remediated package.

The previous Gyan FFmpeg build's complete corresponding source is still
unresolved. The replacement BtbN source bundle does not satisfy obligations for
that older binary. [The legacy record](../LICENSES/ffmpeg/LEGACY-GYAN.txt) retains
the local binary identities and an unsent supplier request. The old public ZIP
was not downloaded in this audit, so its binary hashes are not assumed to match
the retained local Gyan files. Keep the old release on hold and preserve its
asset while obtaining the source/build materials applicable to its recipients.

The [model provenance record](../LICENSES/demucs-model/PROVENANCE.md) explains the
conflicting official statements, includes evidence links, and contains unsent
questions for the rights holder. No permission request has been sent and no
model permission has been invented or inferred from the application's MIT grant.

## Reproducible third-party materials

Notices under `LICENSES/` are copied into each package. Runtime dependency
provenance files identify official versions, file hashes, original archive URLs,
and any corresponding-source archives. `vendor-sources/` is ignored by Git so
large source materials do not inflate the source repository. They are release
materials and must be preserved separately while relevant binaries are supplied.

The root and `release/compact-fix30/KWAK Split` copies now use BtbN FFmpeg
`n8.1.3-18-g46d899d7a0-20261013`. All six executable copies match the pinned
hashes and version. The original app executable and both Demucs checkpoints
remain byte-identical; this remediation did not rebuild or change the editor.
The package includes MIT, the retained component notices and
`DO_NOT_DISTRIBUTE.txt`.

Nine source archives (seven FFmpeg/build/dependency archives and two LAME
archives), totaling 2,189,133,958 bytes, were verified and staged at
`release/compact-fix30/source/` with `SHA256.json`. The FFmpeg materials cover
the 98 dependency source stages matched to the actual build log and 275 rav1e
crates recovered from the same cache layer as the built library. The manifest
records local verification separately from public publication; no public source
or executable release was published. Preserve both `vendor-sources/` and the
release source sidecar for future source delivery.

Verify acquired notices and runtime identities with:

```powershell
.build/qa/Scripts/python.exe -B scripts/prepare_license_materials.py --verify --runtime 'release/compact-fix30/KWAK Split/backend/demucs_runtime'
.build/qa/Scripts/python.exe -B scripts/check_distribution.py --local-only
```

The first command checks the third-party materials; the second verifies the
local decision record. Neither grants model rights or approves public release.
`--fetch` retrieves missing files from pinned sources; it must not silently
replace a file whose hash does not match.

## Verification and limits

- Runtime verification passed for 16 upstream material files, two LAME source
  archives, three native binaries and all 28 pinned runtime packages. Desktop
  PyZMQ/Pillow/PyInstaller identity and notice checks also passed.
- Candidate FFmpeg regression checks passed: 112 tests, seven subtests and six
  WAV/MP3 export cases, using the candidate tools throughout. These cover live
  EQ, rubberband speed/pitch processing, processed spectrum and silent playback.
- The complete `pytest tests` run reported 443 passed, one failed, two skipped
  and 22 passed subtests. The failure was the existing ffplay startup-clock race
  in `test_live_tap_uses_player_clock_and_processed_audio[-12-0.5]`. All 13
  spectrum tests passed on focused rerun. An in-memory reproduction confirmed
  that the unchanged `AnalyzedPlayback.position_seconds` can fall from its
  elapsed-time estimate to the first ffplay timestamp. The same code exists at
  baseline `f62e5f9`; the Windows native output path uses its device clock and
  does not take this fallback. No application code was changed to hide the
  failure. This is a recorded existing limitation, not a fully green suite.
- The 18 new license/release-source tests passed. Full-run evidence is retained
  locally in `temp/license-remediation/full-suite.xml`; focused results are in
  `spectrum-focused.xml`, and candidate audio evidence is in `ffmpeg-qa/`.
  These generated records are excluded from Git.
- Audio tests used the silent SDL device; physical-device listening was not
  performed. Source provenance checks are not an independent bit-for-bit
  rebuild or a legal determination.

## Conditions before public distribution can resume

- Record an applicable model license or written permission for the exact
  included checkpoint and intended general-purpose use and redistribution.
- Recheck the final package's dependency identities and required notices.
- Include or publish the verified corresponding source and build materials
  with the executable download, and keep them available to recipients.
- Retain the component-specific Intel runtime terms without applying them to
  KWAK Split's MIT code or overriding other open-source license rights.
- Verify the actual final package and update the hold record only after the
  underlying rights and distribution conditions are satisfied.

This is a technical provenance and release record, not a legal opinion.

The promotional HTML under `promo/vercel-site` remains a design preview, not a
cleared download or licensing page. Its older availability/commercial-use copy
must be corrected before publication. The attempted copy correction was rejected
by automatic approval review (`blocked by policy`, no detailed reason supplied);
no promotional file was changed. This record and the component notices state
the current rights and hold status.
