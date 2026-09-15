# Neural Upscaling Deadline Study — Reviewer Artifact

This repository contains **supporting data and reproduction tools only** for
*When Neural Upscaling Arrives Too Late: Lessons from a Low-Cost CPU/GPU/NPU SoC*.
The paper PDF, manuscript source, bibliography and submission paperwork are
intentionally not included. This repository is not a preprint.

## What is included

- Frozen RK3576 and RK3566 corrected-runtime summaries and capture archives:
  80 cells and 24,000 source records per board.
- Separate historical runtime, composition-audit and repair evidence.
- Offline quality observations, summary statistics and protocol records.
- Analysis and verification code, pinned dependencies and regression tests.
- Exact file inventory and SHA-256 manifests.

No inference hardware is needed to replay the saved evidence. This is not a
complete hardware-deployment package: model binaries, OS images and the raw
image corpus are not included. The offline checks verify recorded metric
observations and reductions, not fresh image-quality computation.

## Reproduce the reported exhibits

Use Python 3.12 in an environment **outside this repository**. From the
repository root with that environment activated:

```powershell
python -m pip install -r artifact/paper1_hotmobile2027/requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File artifact/paper1_hotmobile2027/reproduce.ps1 -Python python
```

The PowerShell wrapper works in temporary space, checks regenerated outputs
against their frozen references, runs evidence tests and validates manifests.
It does not contact a board or change the saved data.

| Exhibit in the separately submitted paper | Evidence and checks |
| --- | --- |
| Table 1: runtime comparison | `results/{rk3576,rk3566}/paper1_corrected_runtime_v1/`; replay both raw capture archives and compare full summaries. Source rate is the equal-cell arithmetic mean of per-cell capture rates, not panel FPS. |
| Table 2: offline quality | `results/analysis/paper1_hotmobile2027_reprojection.jsonl` and `results/tables/paper1_hotmobile2027_reprojection.json`; check all 144 sampling groups and stored means. |
| Figure 1: source-linked timelines | Saved RK3576 composition/selection events; `timing_examples()` in `src/report/paper1_corrected_runtime_v1.py` applies the documented selection rule and reconstructs timestamps. |

Generated table/figure fragments in `docs/paper/generated/` are machine-produced
reference outputs used for byte-for-byte reproduction checks—not the paper's
manuscript. No LaTeX installation is required for the replay.

## Organization and interpretation

| Directory/file | Contents |
| --- | --- |
| `results/` | Frozen captures, observations, summaries and provenance. |
| `artifact/paper1_hotmobile2027/` | Replay entry point, pinned dependencies, frozen reducer support and integrity checks. |
| `src/` | Reporting and analysis code. |
| `configs/`, `demo/` | Included configuration and renderer-source snapshot. |
| `docs/` | Evidence guide, dated protocols and result notes. |
| `tests/` | Data/reduction/reproduction regression tests; manuscript-format tests are not part of this artifact. |
| `FILES.txt` | Exact distributed-file inventory. |

Read [the evidence guide](docs/paper/PAPER1_EVIDENCE_GUIDE.md) before using
historical records. Corrected-runtime measurements are primary; older results
are preserved separately and never pooled. Root-output post-draw is not GPU
completion or panel scanout. Receipt-side eligibility excludes intervening
waiting and is not elapsed age at assignment.

Each corrected-runtime capture archive contains `freeze.json`, model/runtime
hash bindings and the 80 execution commands. Per-cell `command.json` and
`system.jsonl` retain execution and system records. Engineering archives retain
qualification evidence. These do not imply all deployment dependencies are
redistributed.

## Integrity and availability

`expected_outputs.json` binds evidence and replay files.
`release_manifest.json` covers every `FILES.txt` entry except itself.
`.gitattributes` preserves exact bytes. Only root `.git` metadata is excluded
from the inventory; caches, virtual environments and unrelated files are not
silently ignored.

Intended repository: https://github.com/GMlee11/neural-upscaling-deadline-study.
Preparing this folder does not publish it. After upload, verify access while
signed out and preserve a review snapshot with a commit or tag. The submission
PDF is maintained separately; its artifact link should identify that snapshot.
No manuscript or PDF needs to be uploaded here.

No project-wide open-source license has been selected. Public access is not a
blanket reuse license; dependencies retain their own terms and are installed
separately. Preserve required third-party notices. No venue acceptance, artifact
certification or public registration is implied.
