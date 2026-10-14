# Distribution licensing

Updated 2026-10-14. The owner chose MIT for KWAK Split's original code and,
after direct model comparison, adopted the historical official MIT declaration
for the existing Demucs checkpoint. The model-specific distribution hold is
removed. Third-party rights are not granted by the root MIT license.

## Current release basis and older release history

`LICENSES/distribution-status.json` records the project's adoption of the
historical MIT basis and exact model hash. `scripts/check_distribution.py`
checks the decision and retained evidence; it does not manufacture a license.
No fresh author permission, download receipt or explanation for the later
metadata deletion is required by this project's current policy. The model
remains pinned; any replacement requires reviewing its own license basis.
`build.ps1 -LocalOnly` still deliberately marks non-public development builds.

The initial hold preceded the direct model comparison. The previous GitHub
release `v1.0.0` (release ID 333222423) was changed from public
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
historical official declarations and includes the retained evidence. No inquiry
has been sent. The project relies on the model's own historical declaration,
not on the application's MIT grant or a fabricated new rights-holder approval.

## Historical model MIT evidence now preserved

The owner's later request to adopt and document the historical MIT basis is complete.
`LICENSES/demucs-model/NOTICE.txt` states the exact model, the official historical
revision, and the verified relationship between the files. `MIT-LICENSE.txt`
retains the upstream Demucs MIT text and copyright notice unchanged; its source
is identified separately from the model card's declaration about the weights.

The installed `.th` and the official MIT-marked `.safetensors` contain identical
533 tensor payloads (41,984,456 elements), with identical names, shapes, dtypes,
model class and constructor configuration. The two files' full hashes differ
because their serialization differs. The small source snapshots and exhaustive
comparison are retained in Git and the local package; the additional 84 MB
research model stays in ignored temporary storage rather than the repository.

The record distinguishes the owner's account from independent evidence and
does not invent an acquisition date. No download receipt is required by MIT;
missing one alone is not a reason to reject an otherwise valid historical grant.
The owner confirms MIT-era acquisition and explicitly adopted the historical
MIT basis after the comparison. A fresh permission is not required merely
because the author later deleted the metadata line. This records a project
reliance decision, not a new approval by the rights holder or a guarantee of a
legal outcome. The original model hold is superseded by that owner decision;
the separate legacy-FFmpeg/old-ZIP matter remains as described above.

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
The package includes MIT, the retained component notices and the historical
model evidence. `DISTRIBUTION_NOTICE.txt` explains the source-material delivery
requirements and distinguishes this reviewed package from the old ZIP.

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

The first command checks third-party materials; the second verifies local
records without evaluating publication approval. Omit `--local-only` to check
the adopted distribution decision and retained model evidence. These tools
check records; they do not grant third-party rights.
`--fetch` retrieves missing files from pinned sources; it must not silently
replace a file whose hash does not match.

## Verification and limits

- Historical MIT update: 52 distribution/license/source tests passed. The root
  and packaged public-distribution checks passed with all 14 pinned model
  evidence/notice files verified. Desktop and bundled runtime license checks
  passed, and all nine corresponding-source archives were reverified beside
  the package. The application executable and both installed model checkpoints
  retained their pre-update hashes. No new GitHub release was published.
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

## Conditions for distributing the reviewed package

- Keep the adopted historical model MIT declaration, attribution, license text
  and identity evidence with the exact reviewed checkpoint. This basis is now
  recorded; a new author reply is not a prerequisite.
- Recheck the final package's dependency identities and required notices.
- Include or publish the verified corresponding source and build materials
  with the executable download, and keep them available to recipients.
- Retain the component-specific Intel runtime terms without applying them to
  KWAK Split's MIT code or overriding other open-source license rights.
- Verify the actual final package and ship its source sidecar. The old v1.0.0
  ZIP is not the reviewed package and remains a draft. This update does not
  itself upload or publish a GitHub release.

This is a technical provenance and release record, not a legal opinion.

## Public-facing license wording

The FAQ now links to the original-code MIT license, component notices and model
license record. The blanket claim about use in commercial projects has been
removed at the owner's request. This wording change does not alter MIT's terms
or introduce a non-commercial restriction. Original upstream license texts and
historical evidence remain intact.

The other promotional HTML remains a design preview with download/platform
placeholders; it is not a release artifact or proof of published binaries.
GitHub Releases is the download listing. This source/documentation update does
not re-publish the legacy ZIP or include a separate promotional-site deployment.
