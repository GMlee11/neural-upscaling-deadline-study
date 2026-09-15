# Paper 1 Renderer/Deadline Refresh V1

Last updated: 2026-08-03

## Purpose

This experiment is the final bounded attempt to establish a positive Paper 1
systems mechanism without reopening any frozen quality-selector trace. It asks:

> Can renderer-owned scene metadata and causal runtime state reduce RK3576 NPU
> work while improving strict neural delivery or frame freshness relative to a
> simple fixed-period refresh schedule?

The policy is not allowed to inspect HR pixels, neural output error, filenames,
scene identity, or future timing. The existing Phase-6, semantic, Stage-A, and
topology selectors remain frozen adverse results.

## Mechanism

The renderer computes a bounded priority score from draw-list metadata already
owned by the engine: thin geometry, repeated patterns, foliage, HUD/text,
particles, fences, and reflective surfaces. High-priority frames become
eligible for a faster refresh cadence. A causal controller then admits an NPU
request only when:

- the configured refresh period is due;
- no older request occupies the bounded latest-frame context;
- recent service time predicts completion inside the refresh-age bound; and
- the measured temperature remains below the frozen safety threshold.

The immediately available GPU classical image remains the fallback. A result
inside the three-frame refresh-age bound is not called same-frame real time.
Strict same-frame success uses exactly `1000 / target_fps` milliseconds.

## Fresh Temporal Workloads

Five deterministic Godot variants are reserved for this attempt:

| Variant | Stress content |
|---|---|
| `corridor_neon` | repeated panels, emissive strips, and thin geometry |
| `forest_outpost` | foliage, trunks, fences, and rocks |
| `barrier_yard` | barriers, markings, poles, and crates |
| `reflective_plaza` | reflective materials, seams, and repeated structures |
| `hud_particles` | HUD/text-like detail, particles, and thin signs |

Each run uses a smooth deterministic camera path and 300 measured frames. These
are fresh scene variants for a physical systems decision, not a claim of
independent multi-engine generalization.

## Controls

All profiles use the same Godot scene, width-24 INT8 graph where applicable,
frame count, core profile, and direct DMA-BUF/RGA/GPU reconstruction path:

- GPU bicubic;
- GPU Lanczos;
- always neural;
- fixed refresh every two frames;
- fixed refresh every three frames;
- the frozen renderer-metadata selector adverse baseline; and
- `renderer_deadline_refresh_v1`.

The matrix covers 180p-to-360p at 30 and 60 FPS and 360p-to-720p at 30 FPS.

## Locked Decision Gates

The primary 360p-to-720p/30-FPS result must:

- reduce NPU invocations by at least 25 percent;
- regress display FPS by no more than 1 percent;
- improve strict same-frame neural delivery by at least 0.05 over the better
  fixed-period control;
- avoid any P95 frame-age regression;
- keep refresh-policy overhead below 1 ms; and
- preserve displayed PSNR within 0.10 dB of always neural while beating
  bicubic in every fresh scene.

Power remains pending an external meter and cannot affect the present runtime
decision. Failure of any runtime gate freezes this policy as another adverse
result; it does not authorize threshold retuning on these scenes.

## Reproduction

Prepare the board payload on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts\prepare_rk3576_payload.ps1 `
  -OutputDir .tmp\rk3576_paper1_refresh_v1
```

Run the strict physical matrix on the ROCK 4D:

```bash
bash scripts/rk3576/run_refresh_scheduler_paper1_v1.sh
```

Capture exact board-rendered LR/HR/neural frames separately at a relaxed
cadence:

```bash
bash scripts/rk3576/run_refresh_quality_paper1_v1.sh
```

This capture uses one in-flight frame so the camera cannot advance before the
render-thread DMA capture owns its texture. A four-frame neural-age allowance
prevents synchronous PNG readback from discarding valid model output. Direct
GLES diagnostic readback is bottom-up; the evaluator flips it to top-down and
requires every captured NPU input to match the independently read LR frame
within one 8-bit level. These validation settings are never used for latency,
freshness, or FPS; those decisions come only from the strict matrix.

Copy the capture directory back to the host, then combine the physical frames
with strict 30-FPS policy decisions and calculate LPIPS in the desktop PyTorch
environment:

```powershell
.\.venv\Scripts\python.exe -m src.eval.evaluate_refresh_policy_quality `
  --config configs\rk3576_refresh_quality_paper1_v1.yaml `
  --overwrite

.\.venv\Scripts\python.exe -m src.report.rk3576_paper1_v1_final_decision `
  --overwrite

.\.venv\Scripts\python.exe -m src.report.rk3576_paper1_v1_evidence_manifest `
  --overwrite
```

Canonical outputs are:

- `results/tables/rk3576_refresh_scheduler_paper1_v1.{json,md}`;
- `results/tables/rk3576_refresh_quality_paper1_v1.{json,md}`;
- `results/tables/rk3576_paper1_v1_final_decision.{json,md}`;
- `results/manifests/rk3576_paper1_v1_evidence_manifest.json`;
- `results/analysis/rk3576_refresh_quality_paper1_v1.jsonl`; and
- SQLite record sets ending in `paper1_v1`.

## Current Status

The physical decision is complete: `reject_paper1_renderer_deadline_claim`.
The strict matrix contains 105 rows and 31,500 frames. At the primary
360p-to-720p/30-FPS workload, the proposed policy reaches 30.009 display FPS,
uses 0.141 NPU calls/frame, improves P95 frame age by 5.63% over the best
fixed-period control, and costs 0.711 ms, but delivers zero neural frames
inside 33.33 ms. At 180p-to-360p/30 it provides a limited positive result:
30.007 display FPS and 17.4% strict neural delivery versus 10.9% for fixed
period two, while using 0.610 NPU calls/frame. It does not meet the 60-FPS
deadline.

The corrected five-scene quality capture contains 1,500 aligned frames and
7,500 hashed PNG files across LR, HR, output, validation-input, and residual
channels. Always-neural reaches 31.971 dB / 0.97612 SSIM / 0.03454 LPIPS;
bicubic reaches 31.959 dB / 0.97775 / 0.05451. Because no 720p neural result is
timely, the proposed strict output equals bicubic and fails the requirement to
beat it in every scene. Power remains unmeasured. This result is frozen and the
policy must not be retuned on these physical traces.
