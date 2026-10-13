# Demucs model provenance and release hold

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
The hash starts with the checksum prefix in the upstream filename. No replacement
model was downloaded or installed during this review.

## Conflicting licensing evidence

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
- On 2026-08-31, the author [removed the MIT metadata line](https://huggingface.co/adefossez/HTDemucs/commit/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003).
  The current card contains no model license. The related
  [clarification discussion](https://huggingface.co/adefossez/HTDemucs/discussions/1)
  has no author clarification as of this review.

The old MIT metadata is material evidence of permission and must not be ignored.
Its later removal does **not** establish that a previously valid grant was
retroactively revoked. Conversely, the scope and authority of that metadata,
and its application to this legacy `.th` distribution, have not been resolved.
The official conversion tool indicates the same model state is converted to
safetensors, but tensor-by-tensor identity with the Hub artifact has not been
independently tested here; such a test would not settle permission on its own.

No conclusion is made that training-data licenses automatically transfer to
the weights or to audio separated by a user. No unrestricted redistribution
clearance is claimed from this record. Small evidence extracts and upstream
response hashes are recorded in [evidence.json](evidence.json).

## Approved release decision

On 2026-10-14, the project owner chose to **retain the existing Demucs model and
accepted separation quality, and hold public executable distribution until
model permissions are resolved**. The application's own code may be licensed
under MIT separately; that choice does not remove this hold.

Do not publish the existing model-containing executable package, or describe it
as cleared for general or commercial distribution, on the strength of the
source-code license or this record. No model replacement, automatic download
workaround, or model-rights approval is authorized by this document.

## Draft questions for the rights holder (not sent)

1. May `htdemucs` signature `955717e8`, including the legacy
   `955717e8-8726e21a.th` checkpoint identified above, be used and redistributed
   unchanged inside a general-purpose offline music-editing application, both
   free and commercial? Please identify the applicable license and conditions.
2. Was the `license: mit` declaration published on 2026-07-11 for
   `adefossez/HTDemucs` an intentional grant covering those weights, their legacy
   `.th` form, and format conversions? What was the scope of that declaration
   and the reason it was removed on 2026-08-31?
3. Who can provide written permission for this distribution, and what
   attribution, redistribution, end-user-use, or training-data-related
   conditions must the application satisfy?
