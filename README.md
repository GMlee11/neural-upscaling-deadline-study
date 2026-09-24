# Neural Upscaling Deadline Study - Reviewer Artifact

Supporting data and reproduction tools for **When Neural Upscaling Arrives Too
Late: Lessons from a Low-Cost CPU/GPU/NPU SoC**, Grant Lee, University of Central
Florida. 

This artifact contains no paper PDF, manuscript source, bibliography or
submission paperwork. It is not a preprint. Generated exhibit fragments are
included solely for reproducibility.

## Study and evidence

The paper evaluates 180p, 360p and 720p neural outputs on RK3576 and RK3566:
five scenes, four controls, two repetitions, and 300 sources per cell. This is
120 cells / 36,000 sources per board, 72,000 total. Every runtime table row uses
all 3,000 sources, including bypasses and late outputs.

The root window remains 1280x720; lower-resolution neural images are scaled
into it. Receipt-side eligibility is receipt age plus assignment duration and
excludes intervening waiting. Timely selection requires first source-matched
neural post-draw within 33.33 ms. Neither cadence nor root post-draw is panel FPS
or physical scanout.

At 180p, RK3576 always-neural records 2,791 eligible responses and 3,000 eventual
selections but only 1,032 timely selections (34.4%). The corresponding 360p
counts are 224, 2,984 and 12. No 720p neural selection is timely. RK3566 records
zero timely selections at all three resolutions. The result is not a claim of
reliable 30-Hz neural delivery or an isolated resolution/chip-speed effect.

The 180p sessions and 360p/720p sessions retain separate frozen experiment
identities. Compiled shapes, input-view adapters and RK3576 display setup differ;
shader caches were not cold-cache controlled. These are documented conditions,
not hidden replacement measurements. Old diagnostic/repair results remain
historical and are not pooled into the 72,000-source runtime study.

## Reproduce Tables 1-3

Use Python 3.12 in an environment **outside this repository**:

```powershell
python -m pip install -r artifact/paper1_hotmobile2027/requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File artifact/paper1_hotmobile2027/reproduce.ps1 -Python python
```

The wrapper generates exhibits in temporary space, compares their bytes,
runs focused tests, replays raw runtime events and verifies file manifests.
It does not contact a board, run neural inference or alter saved measurements.

| Paper exhibit | Evidence and reproduction |
| --- | --- |
| Table 1: three-resolution runtime matrix | `results/{rk3576,rk3566}/paper1_corrected_runtime_v1/` for 360p/720p and `paper1_180p_output_v1/` for 180p. `verify_corrected_runtime.py` and `verify_180p_runtime.py` reproduce complete summaries. `src.report.paper1_corrected_runtime_v1` combines their separately identified rows without pooling sessions. |
| Table 2: illustrative source-linked timestamps | Saved RK3576 360p composition/selection events. `timing_examples()` selects the first eligible source in execution/source order per repetition, not by latency. |
| Table 3: offline quality at 360p/720p | `results/analysis/paper1_hotmobile2027_reprojection.jsonl` and `results/tables/paper1_hotmobile2027_reprojection.json`. Tests check 144 sampling groups and stored means; this does not recompute metrics from images. No 180p quality result is claimed. |

Individual portable raw-replay checks, also included in the wrapper:

```text
python -B artifact/paper1_hotmobile2027/verify_corrected_runtime.py
python -B artifact/paper1_hotmobile2027/verify_180p_runtime.py
```

The verifiers execute only the distributed, hash-bound support modules, never
code loaded from capture archives. All 641 capture-file identities per
360p/720p board campaign and 321 per 180p campaign are checked. External board
identities remain recorded attestations, not live rereads by offline replay.

## Organization

| Location | Purpose |
| --- | --- |
| `results/` | Raw captures, qualification snapshots, summaries and quality observations. |
| `artifact/paper1_hotmobile2027/` | Replay entry point, frozen reducers, dependencies and integrity checks. |
| `src/` | Report generation and analysis support. |
| `docs/` | Evidence guide, dated protocol and outcome records, generated exhibits. |
| `configs/`, `demo/` | Included configuration and renderer-source snapshot. |
| `tests/` | Evidence, reduction and integrity checks. |
| `FILES.txt` | Exact distributed-file inventory; root Git metadata is excluded. |

Read [the evidence guide](docs/paper/PAPER1_EVIDENCE_GUIDE.md) for scope and
historical boundaries. Each capture archive contains frozen execution commands,
per-cell system observations and provenance. The 180p archives also contain
their dated protocol, numerical qualification, small compiled model and
hash-bound runtime snapshot. This is not a complete fresh-board installer:
external toolchains, OS images and the raw offline image corpus are not included.
Standalone compiler stdout logs were not retained; retained compiler metadata
does not substitute for those missing logs.

## Integrity, availability and reuse

`expected_outputs.json` binds evidence and replay files; `release_manifest.json`
covers every `FILES.txt` entry except itself. `.gitattributes` preserves bytes.
Old capture archives and their identities are unchanged.

Repository: https://github.com/GMlee11/neural-upscaling-deadline-study.
This September 24 three-resolution revision is prepared locally for the author
to commit and push. The earlier public snapshot `6dff168` does not contain its
180p data. After upload, preserve the review commit/tag and verify access while
signed out before uploading the matching replacement PDF to HotCRP. No assistant
commit, push or submission was performed by this preparation.
