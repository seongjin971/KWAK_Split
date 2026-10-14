# Demucs model provenance and historical MIT evidence

Reviewed: 2026-10-14. This is a provenance and release-decision record, not a
license grant or a legal opinion. The application's own license does not grant
rights to third-party model weights.

## Current model

| Field | Verified value |
| --- | --- |
| Engine | Demucs 4.0.1 |
| Model | `htdemucs`, signature `955717e8`, four stems |
| Local file | `models/torch/hub/checkpoints/955717e8-8726e21a.th` |
| Size | 84,141,911 bytes |
| SHA-256 | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |

The local model and the copy in `release/compact-fix30/KWAK Split` have the
same hash. They are excluded from the Git source repository.

Upstream provenance: [model definition](https://github.com/facebookresearch/demucs/blob/main/demucs/remote/htdemucs.yaml),
[checkpoint index](https://github.com/facebookresearch/demucs/blob/main/demucs/remote/files.txt),
and [original checkpoint URL](https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th).
The hash starts with the checksum prefix in the upstream filename. The installed
model was not replaced. An official historical safetensors artifact was obtained
only in an ignored investigation directory for the comparison below.

## Completed historical-license documentation

At the owner's request on 2026-10-14, the historical MIT declaration, original
copyright/license notice, and model-identity evidence are now retained with this
project and its local package. [NOTICE.txt](NOTICE.txt) gives the attributable,
fact-based statement; [MIT-LICENSE.txt](MIT-LICENSE.txt) preserves the exact
upstream Demucs MIT text and copyright notice. This is not a new license grant
by KWAK Split or an assertion that the rights holder gave us a separate approval.

The owner states that this model was obtained and used while it was MIT licensed.
This is recorded as the owner's account, not independent verification of a
particular model download date or URL. No date is invented.
MIT does not require a download receipt; absence of such a receipt alone is not
a finding that the owner lacks rights under an otherwise valid MIT grant.

## Verified model identity

The installed `.th` checkpoint was compared with the actual official artifact
from revision `bf35a81b663819a8255c8fefee17f9d812b786b5`, whose model card states
`license: mit` and expressly identifies the weights of `htdemucs`/`955717e8`.

| Check | Result |
| --- | --- |
| Official file | `955717e8.safetensors`, 84,025,440 bytes |
| Official LFS SHA-256 | `d9fa14133cfcc034a6758923bb3a8ca9f8dfd0b582134643bbf83f72c17576dd` |
| Tensor names, shapes and dtypes | All 533 match |
| Tensor payloads | All 41,984,456 elements match byte for byte |
| Model class and constructor arguments | Match, including normalized Fraction metadata |
| Installed and packaged legacy checkpoints | Both match the `.th` SHA-256 above |

The whole-file hashes differ because the serialization formats differ. The
comparison was exhaustive, not a sample or an audio-quality estimate. The
downloaded artifact's full hash matched the official revision's LFS identity.
The original checkpoint was read only after checking its full expected hash;
the safetensors file was parsed as data, without executing downloaded code.

The complete per-tensor results and exact comparison method are retained under
[evidence/](evidence/), indexed and hashed by [evidence.json](evidence.json).
Large model files remain excluded from the Git repository. This confirms the
same weights and declared configuration, not the legal validity of a grant.

## Historical declarations and later changes

- Demucs **source code** is [MIT licensed](https://github.com/facebookresearch/demucs/blob/v4.0.1/LICENSE).
  This does not by itself establish the license of its weights.
- In [issue 327, on 2022-05-23](https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611),
  author Alexandre Defossez distinguished the weights from the MIT source code
  and described their provision as limited to scientific purposes.
- In [issue 508, on 2023-08-02](https://github.com/facebookresearch/demucs/issues/508#issuecomment-1663033356),
  he answered a question specifically about commercial use of **htdemucs v4**
  by describing the weights as provided for research.
- The author's official Hugging Face model repository then included
  **`license: mit`** in its [2026-07-11 model card](https://huggingface.co/adefossez/HTDemucs/blob/bf35a81b663819a8255c8fefee17f9d812b786b5/README.md).
  This card explicitly identifies `955717e8.safetensors`; that revision includes
  the actual model file, its metadata, and `htdemucs.yaml`.
- On 2026-08-31 UTC (2026-09-01 in Korea), the author [removed the MIT metadata line](https://huggingface.co/adefossez/HTDemucs/commit/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003).
  The current card contains no model license. The related
  [clarification discussion](https://huggingface.co/adefossez/HTDemucs/discussions/1)
  has no author clarification as of this review.

The official commit API dates the upload to 2026-07-11 22:51:42 KST and the
removal to 2026-09-01 05:18:44 KST; both were made by `adefossez`. The model,
JSON configuration and YAML files are unchanged across those revisions. Only
the MIT line was removed from the card. The historical official
[conversion tool](https://github.com/adefossez/demucs/blob/ab872e10daf3316d3ee2f21fcd6f90a3cbd6216a/tools/export_hf.py)
also contained `license: mit` in its model-card template; this was not merely a
license badge guessed by the hosting site.

The project adopts the historical official MIT declaration as its distribution
basis for this exact, verified-identical checkpoint. It is not a code-only
notice. The later deletion is not treated as retroactively cancelling the
historical grant. The owner explicitly chose this basis after the identity
comparison; a new permission, a download receipt, or an explanation for the
metadata deletion is not a prerequisite imposed by this project's release policy.
This is a project reliance decision, not a new approval by the rights holder
or a guarantee of the legal outcome of a dispute.

No conclusion is made that training-data licenses automatically transfer to
the weights or to audio separated by a user. Historical source snapshots,
provenance, hashes and the complete identity result are recorded in
[evidence.json](evidence.json). The retained older statements and deletion history
are included for transparency rather than presented as automatic overrides of
the later historical MIT declaration.

## Release decision and limits of this update

The initial 2026-10-14 decision was to hold model-containing public packages.
After the historical official artifact was compared directly, the owner chose
to rely on its MIT declaration and requested removal of the model-specific hold.
`LICENSES/distribution-status.json` records this updated project decision as
`historical-mit-basis-adopted`. Keep this checkpoint pinned and retain the MIT
text, attribution, historical card and identity evidence with its distribution.

This update does not change the model or the application's separation quality.
It does not itself upload or publish a release. The older v1.0.0 ZIP remains a
draft because its legacy FFmpeg materials are a separate unresolved matter.
The current package must be delivered with the verified FFmpeg/LAME source
materials and other component notices described in `docs/license-compliance.md`.
No inquiry or other external message has been sent to the rights holder.
