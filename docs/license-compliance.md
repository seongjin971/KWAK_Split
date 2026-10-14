# Distribution licensing

Updated 2026-10-14. This is a technical release record, not a legal opinion.

## Current basis

- KWAK Split's original code is MIT licensed ([LICENSE](../LICENSE)). The MIT
  grant does not relicense third-party components; their notices are in
  [THIRD_PARTY_NOTICES.txt](../THIRD_PARTY_NOTICES.txt) and `LICENSES/`.
- The Demucs model weights are **not redistributed**. Public packages contain
  no model files; the app downloads the official checkpoint on the first split.
  The author provides the weights for research purposes, outside the Demucs MIT
  license. See the [model record](../LICENSES/demucs-model/PROVENANCE.md). This
  replaces the earlier reliance on a Hugging Face `license: mit` line that the
  author removed; that superseded record remains in Git history (`6fdced2`).
- FFmpeg (GPL-3.0-or-later) and LAME through lameenc (LGPL) are bundled. Every
  public download must provide their verified corresponding source. FFmpeg is
  rebuilt without DVD support, so the DVD decryption library libdvdcss is not
  included ([source notes](../LICENSES/ffmpeg/SOURCE-README.txt)).

`LICENSES/distribution-status.json` records the decision.
`scripts/check_distribution.py` checks it; with `--package` it also fails if a
built package contains any model file. These tools check records; they do not
grant third-party rights.

## Publishing a public release

1. Build without `-LocalOnly`, using a new release name:
   `.\build.ps1 -ReleaseName <name>`. The build verifies notices, runtime
   identities and FFmpeg/LAME source, leaves `models/` empty, rejects a package
   that contains model files and stages `release/<name>/source/`.
2. Zip the `release/<name>/KWAK Split` folder. GitHub allows up to 2 GiB per
   release file; the folder is about 1.8 GB before compression.
3. Attach to the same GitHub release: the app ZIP, every archive under
   `release/<name>/source/` (seven FFmpeg and two LAME archives, about 2.2 GB in
   total) and `SHA256.json`.
4. In the release notes, state that KWAK Split is MIT licensed, that the FFmpeg
   and LAME corresponding source is attached to the release, and that the
   Demucs model is downloaded on the first split and is not covered by the MIT
   license (link `LICENSES/demucs-model/NOTICE.txt`).
5. Keep the source assets available for as long as the app ZIP is offered. A
   later release with the same FFmpeg build may link to the release that holds
   that source instead of uploading it again.

Never publish `release/compact-fix30` or any `-LocalOnly` package: they contain
the local model checkpoint. Do not re-publish the draft v1.0.0 ZIP.

## Published releases

- [v1.1.0](https://github.com/seongjin971/KWAK_Split/releases/tag/v1.1.0),
  2026-10-14: the public package (no model files) with all nine source
  archives, `SHA256.json` and the FFmpeg package
  `ffmpeg-n8.1.3-18-g46d899d7a0-win64-gpl-8.1-nodvd.zip`. Keep these assets
  while the package is offered.

## Earlier release

The previous GitHub release `v1.0.0` (release ID 333222423) was changed from
public to draft on 2026-10-14; its ZIP asset ID 436372026 was preserved, and an
unauthenticated API check then returned no public releases. Before/after
receipts are retained locally under `backups/license-remediation-20261014/`,
excluded from Git. That ZIP used a Gyan FFmpeg 8.1.1 build whose complete
corresponding source was never attached. [The legacy record](../LICENSES/ffmpeg/LEGACY-GYAN.txt)
keeps the local binary identities and an unsent supplier request. The
replacement BtbN source bundle does not cover that older binary, so the old ZIP
must stay unpublished.

## Third-party materials

Notices under `LICENSES/` are copied into each package. Runtime dependency
provenance files identify official versions, file hashes, original archive URLs
and any corresponding-source archives. `vendor-sources/` is ignored by Git so
large source materials do not inflate the repository; preserve it and each
release's `source/` sidecar for as long as the matching binaries are offered.

The root and `release/compact-fix30/KWAK Split` copies use FFmpeg
`n8.1.3-18-g46d899d7a0-kwak-nodvd`, rebuilt on 2026-10-14 by
`.github/workflows/ffmpeg-nodvd.yml` from BtbN's recipes, FFmpeg commit and
dependency image with DVD support disabled. Apart from that and the version
suffix, its configure command is identical to BtbN's 2026-10-13 build; the
three executables contain no libdvdcss code. All six copies match the pinned
hashes and version. The previous BtbN binaries are kept locally under
`backups/`.

Nine source archives (seven FFmpeg/build/dependency archives and two LAME
archives), totaling 2,188,531,846 bytes, are verified by
`scripts/prepare_distribution_sources.py`. The FFmpeg materials cover the 95
dependency source stages linked into the executables, matched to the
dependency build log, and 275 rav1e crates recovered from the same cache layer
as the built library. `release/compact-fix30` no longer carries a source
sidecar because it must not be published; a public build stages its own.
Release v1.1.0 provides these archives publicly.

Verify acquired notices and runtime identities with:

```powershell
.build/qa/Scripts/python.exe -B scripts/prepare_license_materials.py --verify --runtime 'release/compact-fix30/KWAK Split/backend/demucs_runtime'
.build/qa/Scripts/python.exe -B scripts/check_distribution.py --local-only
```

Omit `--local-only` to check the public decision; add `--package <folder>` to
check a built package. `--fetch` retrieves missing files from pinned sources;
it must not silently replace a file whose hash does not match.

## Verification and limits

- Model exclusion, 2026-10-14: the packaged runtime downloaded the official
  checkpoint into an empty model folder (matching SHA-256) and wrote four stems.
  The package check rejects `release/compact-fix30` for its checkpoint and
  reports nothing else there.
- No-DVD FFmpeg, 2026-10-14: all three executables report
  `n8.1.3-18-g46d899d7a0-kwak-nodvd`, contain no libdvdcss strings and lack the
  dvdvideo demuxer; the azmq, rubberband, equalizer, alimiter and showspectrum
  filters and the libmp3lame encoder are present. `download_ffmpeg.ps1
  -ValidateOnly` passed for both bin folders.
- With that `bin/` first on PATH, the full suite reported 459 passed and two
  skipped (the existing Windows symlink-permission skips), with 22 subtests
  passed. Keep `bin/` first when testing: the fixtures otherwise use whatever
  FFmpeg PATH provides, such as a separately installed WinGet build.
- `scripts/qa_compact_release.py` on `release/compact-fix30` with the new tools
  passed: EXE smoke test, confined runtime imports, a real two-second split into
  four stems, 48 kHz 24-bit WAV and 320 kbps MP3 mixes, four separate WAVs and
  MP3s, and play/pause/resume on the silent device.
- Runtime license materials verified: five components, 16 files, two LAME
  source archives, three native binaries and 28 pinned runtime packages.
- Audio tests used the silent SDL device; physical-device listening was not
  performed. Source provenance checks are not a bit-for-bit rebuild.

## Public-facing wording

The promotional site describes a Windows-only portable ZIP, a one-time model
download on the first split and the license terms above; it makes no
commercial-use claim. Its feature copy and screenshots match the current
compact UI (three-band EQ, mute/solo mixer, four-track export; no presets). Its download links and checksums are placeholders until
a public release exists. GitHub Releases is the download listing.
