Intel OpenMP Runtime 2024.2.1
===========================

The two files under backend/demucs_runtime/Lib/site-packages/torch/lib are:
- libiomp5md.dll
- libiompstubs5md.dll

Both files were verified byte for byte against Intel's official
intel_openmp-2024.2.1-py2.py3-none-win_amd64.whl. Their SHA-256 values,
the exact wheel URL, wheel SHA-256 and archive member paths are recorded
in provenance.json. The earlier 2024.2.0 comparison is superseded by this
exact 2024.2.1 match.

LICENSE.txt and third-party-programs.txt were copied unmodified from that
same wheel. The main license is the Intel End User License Agreement for
Developer Tools, April 2023. The third-party notice includes the separate
terms for the software listed there, including LLVM OpenMP and ITT.
The PyTorch BSD license does not replace these Intel and third-party terms.

REDISTRIBUTION.txt supplies the end-user terms specifically for these two
Intel Redistributables. It does not change KWAK Split's own source license.

fredist.txt is the redistribution designation from Intel's official
w_ifort_runtime_p_2024.2.1.1084.exe package. It names both 64-bit DLLs.
The same installer contains byte-identical copies of both distributed DLLs.
The installer was opened as data (ZIP / read-only MSI / CAB); it was never
installed or executed. Its URL, SHA-256, nested archive hashes and notice
member names are recorded in provenance.json.

The OpenMP notice references additional oneTBB notices. The 2021.13.0 and
2021.13.1 upstream oneTBB third-party texts are identical; the latter is
included as oneTBB-third-party-programs.txt. TCM's license and third-party
notice are also supplied from the same 2024.2.1 Intel runtime installer.
These supplemental notices preserve the referenced terms without claiming
that a separate oneTBB or TCM DLL is bundled in KWAK Split.

Keep all these notices and terms with any permitted redistribution. The DLLs may
not be presented as being licensed solely under KWAK Split's own license.

Official origin:
https://pypi.org/project/intel-openmp/2024.2.1/
https://www.intel.com/content/www/us/en/developer/articles/tool/compilers-redistributable-libraries-by-version.html
