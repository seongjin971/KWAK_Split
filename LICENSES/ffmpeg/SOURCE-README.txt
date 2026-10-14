FFmpeg corresponding-source material for KWAK Split
===================================================

Applies only to the three executables identified by manifest.json:
FFmpeg n8.1.3-18-g46d899d7a0-kwak-nodvd, win64-gpl-8.1, GPLv3-or-later.
They were rebuilt from BtbN/FFmpeg-Builds with the FFmpeg commit and
dependency image of BtbN's 2026-10-13 release, but without DVD support:
libdvdcss, libdvdread and libdvdnav are not linked. Neither BtbN's original
2026-10-13 binaries nor the older Gyan 8.1.1 build is covered; for the latter
see LEGACY-GYAN.txt.

What is preserved
-----------------
The release's source/ffmpeg directory must accompany the application download:

* FFmpeg-46d899d7a02bc63237472cc4897258d5ddf274ac.tar.gz: exact FFmpeg source.
* FFmpeg-Builds-63ac3265b0789ea16c7b1f8351cd2ad195a28722.tar.gz: original build
  recipes, patches, Dockerfiles and workflow. Original MIT license retained.
* dependencies-part1.zip through dependencies-part3.zip: the 95 dependency
  source stages linked into these executables, at .cache/downloads/*.tar.xz.
* rav1e-cargo-sources.zip: the 275 original Rust crate source archives recovered
  from the same Docker build-cache layer as the built librav1e.a.
* source-metadata.zip: inventory, checksums, configuration, provenance, the
  KWAK Split recipe patch, build script, workflow and build log, reconstruction
  notes, and the application-side original license notices.

How these executables were built
--------------------------------
build/build-nodvd.sh fetches FFmpeg-Builds at 63ac3265, applies
build/btbn-nodvd.patch and runs ./build.sh win64 gpl 8.1. The patch uses the
dependency image ghcr.io/btbn/ffmpeg-builds/win64-gpl-8.1@sha256:79ffe8aa0a517bb5a4fbeb718c798b88033b1d853e82b0e936ee4edd95a0f2be,
checks out FFmpeg 46d899d7a02bc63237472cc4897258d5ddf274ac, replaces
--enable-libdvdread/--enable-libdvdnav with --disable-libdvdread and
--disable-libdvdnav, and sets the version suffix kwak-nodvd. The workflow
.github/workflows/ffmpeg-nodvd.yml ran it on GitHub Actions:
https://github.com/seongjin971/KWAK_Split/actions/runs/38508865689
Its build log, image digest and checksums are in source-metadata.zip.

Large archives are kept locally in vendor-sources/ffmpeg and excluded from Git.
Their exact sizes, SHA-256 hashes and release locations are in manifest.json.
The source/ffmpeg directory is staged and hash-checked by
scripts/prepare_distribution_sources.py. Public distribution requires actually
delivering these files; a source-tree notice or transient upstream link alone
is not a substitute. Retain source access while providing the binaries.

Provenance and selection
------------------------
BtbN release whose FFmpeg commit and dependency image are reused:
https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-13-13-05
BtbN build run that produced the dependency image:
https://github.com/BtbN/FFmpeg-Builds/actions/runs/38396239770
Source-cache artifact ID: 11811473165 (download-cache).
Original artifact SHA-256:
ae912701a3fc2f92473c5bd16deb8fedadcdd3720badd96d72284637b5d55ffc

The original cache covers multiple variants. 98 active source stages were
selected, and all 98 filenames match the actual win64 GPL 8.1 build log. The
no-DVD executables do not link libdvdcss, libdvdread or libdvdnav, so those
three stage archives are left out; build/rebundle_nodvd.py copied the other 95
unchanged and records the three under excluded_unlinked_stages in
source-inventory.json. Unused stages, including fdk-aac/nonfree variants, are
excluded. The original whole cache remains private acquisition evidence, not a
release artifact.

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
FFmpeg-Builds archive; the KWAK Split patch and script are in build/. Use a
Linux Docker build environment, not the application's Windows Python
environment. Rebuilds may produce different binary hashes.

With BtbN's published dependency image, run build/build-nodvd.sh (this is what
the workflow did). To rebuild that dependency image from the supplied source:

1. Unpack the FFmpeg-Builds archive into a build directory. Unpack all three
   dependency ZIPs into that directory, preserving .cache/downloads paths.
   The tar.xz filenames encode upstream download-command hashes. The cache is
   intentionally limited to the selected GPL target, so do not run a script
   that fetches all variants before using it. Disable the three scripts.d/50-dvd
   stages (make ffbuild_enabled return -1): they are not linked, and their
   sources are not supplied.
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
5. Run build/build-nodvd.sh with the IMAGE line of btbn-nodvd.patch pointing
   at the rebuilt image. It builds FFmpeg 46d899d7a02bc63237472cc4897258d5ddf274ac
   with the configure command recorded in build-provenance.json, DVD disabled.
   To build offline, replace its git checkout with the supplied FFmpeg archive.

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
