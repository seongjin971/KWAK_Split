lameenc 1.8.4 and LAME 3.100
==========================

The Python extension lameenc.cp311-win_amd64.pyd is licensed under
LGPL-3.0-or-later. It statically includes LAME 3.100, whose source uses
LGPL-2.0-or-later. The LGPLv3 and GPLv3 texts are also supplied at
LICENSES/LGPL-3.0.txt and LICENSES/GPL-3.0.txt. This directory preserves
the wrapper's LICENSE and LAME's COPYING, LICENSE and mpglib AUTHORS.

KWAK Split uses LAME through the Demucs runtime. LAME is developed by the
LAME project: https://lame.sourceforge.io/

The installed extension is byte-identical to the official PyPI Windows
CPython 3.11 wheel. That wheel records the exact source commit as
813cce2f818dbd6888c0e02bc229e764e6491be6 (SCM tag 1.8.4, clean working tree).
provenance.json records that source identity and all archive/binary hashes.

Corresponding source supplied with a distributable package
---------------------------------------------------------

source/lameenc/lameenc-1.8.4.tar.gz
source/lameenc/lame-3.100.tar.gz

The first archive contains the complete wrapper source and build scripts,
including CMakeLists.txt, setup.py, pyproject.toml, the CI workflow,
patch-lame.cmake and fixed-libmp3lame.sym. The second is the exact LAME
3.100 archive named and hashed by that CMakeLists.txt. No KWAK Split
changes were made to the extension or those source archives.

For repository developers these archives are cached at vendor-sources/lameenc/.
Run python -B scripts/prepare_license_materials.py --fetch to obtain missing
pinned files, or --verify to verify every notice and source archive. Archives
are intentionally excluded from Git history, but a binary distribution must
include them at the paths above or provide compliant equivalent access to
the complete corresponding source beside the binary download. A notice that
merely links to a project homepage is not a substitute for those materials.

Rebuild and replace
-------------------

BUILDING.txt describes reconstruction using these sources and replacement
of the independently loaded Python extension. You may modify the LGPL
components and debug such modifications subject to their license terms.
Nothing in KWAK Split's own license restricts those LGPL rights. The
extension is an ordinary file loaded by the bundled Python interpreter,
not encrypted into the application executable or locked to a signature.
