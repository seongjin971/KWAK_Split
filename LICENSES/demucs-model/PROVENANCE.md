# Demucs model weights: distribution record

Updated 2026-10-14. This is a project decision record, not a legal opinion.

## Decision

KWAK Split does not redistribute the Demucs `htdemucs` weights. Public
packages contain no model files. On the first Split Stems, the bundled Demucs
4.0.1 runtime downloads the official checkpoint and checks it against the hash
prefix in its file name:

| Field | Value |
| --- | --- |
| Model | `htdemucs`, signature `955717e8`, four stems |
| URL | https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th |
| Size | 84,141,911 bytes |
| SHA-256 | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |
| Stored at | `models/torch/hub/checkpoints/` inside the app folder |

On 2026-10-14 the packaged runtime was run with an empty model folder. It
downloaded the checkpoint from the URL above, the SHA-256 matched, and all
four stems were written.

## Why the weights are not bundled

The Demucs **code** is [MIT licensed](https://github.com/facebookresearch/demucs/blob/v4.0.1/LICENSE).
The author has said that this does not cover the weights:

- 2022-01-04, [issue 267](https://github.com/facebookresearch/demucs/issues/267#issuecomment-1004721776):
  citing the MusDB dataset terms, "the pre-trained weights are mostly usable
  for research purpose", and making a real app is "out of the scope of those
  terms".
- 2022-05-23, [issue 327](https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611):
  "The model weights are not covered by the MIT license, and are provided only
  for scientific purposes."
- 2023-08-02, [issue 508](https://github.com/facebookresearch/demucs/issues/508#issuecomment-1663033356):
  "Weights are provided for research purpose!"

On 2026-07-11 the author's Hugging Face upload,
[adefossez/HTDemucs](https://huggingface.co/adefossez/HTDemucs), had a
`license: mit` line in its model card. That line is fixed template text in the
Demucs [conversion tool](https://github.com/adefossez/demucs/blob/ab872e10daf3316d3ee2f21fcd6f90a3cbd6216a/tools/export_hf.py).
After a user asked whether it was intentional, the author removed it on
2026-08-31 UTC ([commit](https://huggingface.co/adefossez/HTDemucs/commit/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003))
without further comment. KWAK Split does not rely on that removed line. An
earlier project record that adopted it as a distribution basis is superseded;
it remains in Git history (commit `6fdced2`).

## Consequences

- Public packages contain no model files. `build.ps1` leaves `models/` empty
  and `scripts/check_distribution.py --package` rejects any model file.
- The first split needs an internet connection and downloads about 84 MB.
  Users decide whether their use fits the model's terms; KWAK Split grants no
  rights to the weights.
- The developer's local `models/` folder and `release/compact-fix30` contain the
  checkpoint, and the draft v1.0.0 ZIP may too. They must not be published.
