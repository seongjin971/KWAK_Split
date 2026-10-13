FFmpeg corresponding-source material for KWAK Split
===================================================

Applies only to the three executables identified by manifest.json:
BtbN n8.1.3-18-g46d899d7a0-20261013, win64-gpl-8.1, GPLv3-or-later.
The older Gyan 8.1.1 build is a separate unresolved historical matter; see
LEGACY-GYAN.txt. This material does not repair that older distribution.

What is preserved
-----------------
The release's source/ffmpeg directory must accompany the application download:

* FFmpeg-46d899d7a02bc63237472cc4897258d5ddf274ac.tar.gz: exact FFmpeg source.
* FFmpeg-Builds-63ac3265b0789ea16c7b1f8351cd2ad195a28722.tar.gz: original build
  recipes, patches, Dockerfiles and workflow. Original MIT license retained.
* dependencies-part1.zip through dependencies-part3.zip: the 98 dependency
  source stages actually used by win64 GPL 8.1, at .cache/downloads/*.tar.xz.
* rav1e-cargo-sources.zip: the 275 original Rust crate source archives recovered
  from the same Docker build-cache layer as the built librav1e.a.
* source-metadata.zip: inventory, checksums, configuration, provenance,
  reconstruction notes, and the application-side original license notices.

Large archives are kept locally in vendor-sources/ffmpeg and excluded from Git.
Their exact sizes, SHA-256 hashes and release locations are in manifest.json.
The source/ffmpeg directory is staged and hash-checked by
scripts/prepare_distribution_sources.py. Public distribution requires actually
delivering these files; a source-tree notice or transient upstream link alone
is not a substitute. Retain source access while providing the binaries.

Provenance and selection
------------------------
Upstream release:
https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-13-13-05
Build run:
https://github.com/BtbN/FFmpeg-Builds/actions/runs/38396239770
Source-cache artifact ID: 11811473165 (download-cache).
Original artifact SHA-256:
ae912701a3fc2f92473c5bd16deb8fedadcdd3720badd96d72284637b5d55ffc

The original cache covers multiple variants. Only the 98 active source stages
were selected, and all 98 filenames match the actual win64 GPL 8.1 build log.
Unused stages, including fdk-aac/nonfree variants, are excluded. The original
whole cache remains private acquisition evidence, not a release artifact.

AMF is header-only in this FFmpeg recipe: it copies amf/public/include.
The source sidecar keeps exactly those headers and AMD's original LICENSE.txt.
Unused AMF samples/implementations, including DeckLink SDK-generated headers,
are omitted. This filter and both original/distributed hashes are recorded in
source-inventory.json; no header used by the build was changed.

Most source commits are verified using the cached .git/HEAD. The upstream AMF
recipe removes .git, and libiconv removes the nested gnulib .git; those inputs
are identified by the recipe's fixed commits, exact download-command hashes
and the authenticated upstream artifact digest instead.

The rav1e recipe performs cargo update cc during its build. Its original lock
file alone is therefore insufficient. The retained OCI cache manifest is
sha256:e946dce215b73608c6b13d9579d56bf6a2bf8a20527eb57556a50bb26821baf2.
The exact Cargo source layer is
sha256:1c08284f51dfd343c3b9180ab15a1cd72fe2f3d1c3d035e25cb7b26e1ecaafe6.
That same layer contains librav1e.a and its 275 source crates. The original
Cargo.lock accounts for 272 matching archives; cc is 1.6.0, with new
find-msvc-tools 0.1.14 and shlex 2.0.1. Their package checksums are verified
against the actual cached registry metadata. See rav1e-cargo-inventory.json.
The archive includes build/test and platform alternatives as well as linked
crates; inclusion does not assert every crate is linked into the executables.

Build reconstruction
--------------------
The original upstream workflow and scripts are supplied unchanged in the
FFmpeg-Builds archive. Use a Linux Docker build environment, not the application's
Windows Python environment. No byte-for-byte rebuild was performed by this
audit, and modern toolchains may produce different binary hashes.

1. Unpack the FFmpeg-Builds archive into a build directory. Unpack all three
   dependency ZIPs into that directory, preserving .cache/downloads paths.
   The tar.xz filenames encode upstream download-command hashes. The cache is
   intentionally limited to the selected GPL target, so do not run a script
   that fetches all variants before using it.
2. Inspect generate.sh, scripts.d, util and the original workflow. Generate the
   dependency build with ./generate.sh win64 gpl 8.1. The recorded base image is
   ghcr.io/btbn/ffmpeg-builds/base-win64@sha256:f27c68da9e353b5fcef0396fb5d5112b969eb6c9fb02e8df484c0fea130016e7.
   Pin that image in the generated Dockerfile instead of resolving latest.
   The source archive also contains the general toolchain Dockerfiles/scripts.
3. Restore the supplied rav1e crate archives into the Cargo cache used by the
   build (/opt/cargo). Alternatively unpack them into a Cargo directory source
   and configure crates-io replacement. Select cc 1.6.0 precisely; do not repeat
   an unbounded cargo update. The original 50-rav1e.sh records all build flags.
   The librsvg source cache already includes its vendored Rust dependencies.
4. Build the dependency image using the supplied scripts. The original
   scripts.d recipes contain the modifications/patches and configure switches
   for every dependency. Build stages use the supplied cache tarballs.
5. Unpack the exact FFmpeg source archive. Use the recorded configure command
   in build-provenance.json and the original build.sh commands inside the
   dependency image. Do not let build.sh clone today's release/8.1 branch;
   use the supplied source at 46d899d7a02bc63237472cc4897258d5ddf274ac.
   Run make and make install as described by that original script.

Normal compilers, build utilities and their standard runtime/system libraries
are not claimed to be reproduced byte-for-byte here. Their version evidence
and applicable retained license notices are included; the original build
recipes document how the toolchain is assembled.

License notices
---------------
GPL-3.0.txt is the FFmpeg executable license. components/ preserves original
notices from the selected dependency sources, including vendored libraries and
supplemental header notices. Source archives retain their original license
files and copyright headers. Keep this entire LICENSES/ffmpeg directory in the
application even when distributing source archives as a separate sidecar.

FFmpeg is invoked as a separate executable by KWAK Split. Its GPL-covered
material retains its own license; KWAK Split's original source uses the license
declared at the project root. Do not remove third-party conditions or describe
the entire executable package as containing only MIT-licensed software.
