# Paper 1 RK3566 replication — complete physical outcome

2026-09-11. `paper1_rk3566_replication_v1`: **COMPLETE**, 50/50 intended cells,
15,000 measured frames, one physical session. No failed cells, retries, omitted
scenes, policy tuning, or changes to earlier Paper 1/2/3 results.

## What was run

Orange Pi 3B V2.1 / RK3566; real Mali-G52 Panfrost GLES 3.1 rendering;
Godot 4.6.3; kernel 6.1.115-vendor-rk35xx; Mesa 25.0.7; RKNN Runtime/Toolkit2
2.3.2; one default NPU context, three buffer slots. Both full-frame models were
compiled from the unchanged original ONNX and original calibration lists.

Five original scenes × two resolutions × five controls, 300 measured frames
and 20 renderer warmups per cell, fixed 30-FPS target. The order rotated
controls and alternated resolution order. Governors were unchanged. Each cell
started at <=55C; maximum recorded temperature across the session was 61.666C,
below the 80C stop threshold. No diagnostic image readback or quality measurement
was performed in the timed runs.

Pre-capture qualification: 16/16 synthetic numerical cases passed; residuals
were byte-exact against an ordinary RKNN API reference, composition error <=1
RGB byte, and 24 repeated input/residual/composition comparisons were identical.
Forced bicubic and Lanczos actual shader identities and final-frame failure
propagation were tested. The independent review approved the fixed protocol.

## All scene-equal aggregate results

Each row covers all five scenes and 1,500 measured source-frame records.
Cadence is initial fallback presentation, **not panel FPS or complete later
composition history**. Strict eligibility is source response age plus upload
<=33.33ms; runtime acceptance uses <=100ms.

| Output | Control | Fallback/s | NPU completions | Runtime accepted | Strict eligible |
|---|---|---:|---:|---:|---:|
| 360p | Bicubic | 29.993 | 0 | 0 | 0 |
| 360p | Verified Lanczos | 24.712 | 0 | 0 | 0 |
| 360p | Always neural | 25.809 | 1,500 | 1,500 | 0 |
| 360p | Fixed period 2 | 29.965 | 750 | 750 | 0 |
| 360p | Frozen scheduler | 29.403 | 506 | 506 | 0 |
| 720p | Bicubic | 29.982 | 0 | 0 | 0 |
| 720p | Verified Lanczos | 22.503 | 0 | 0 | 0 |
| 720p | Always neural | 9.814 | 1,500 | 0 | 0 |
| 720p | Fixed period 2 | 15.240 | 750 | 0 | 0 |
| 720p | Frozen scheduler | 29.997 | 5 | 0 | 0 |

At 720p the scheduler makes one completed startup request per scene and avoids
submission on 1,495/1,500 source frames (99.667% fewer requests than always-neural). All five completions
are late even under the 100ms gate. Its restored cadence is therefore not a
neural-delivery or quality success. At 360p every always-neural completion is
runtime-accepted, while none meets the strict one-frame rule. This separately
replicates the distinction among fallback cadence, runtime acceptance and strict
source-matched eligibility. Zero strict eligibility holds in every measured
cell, not merely an aggregate selected after inspection.

This is not a matched chip-speed comparison: hardware, drivers, target-specific
compiled artifacts and NPU concurrency differ from RK3576. It does not establish
multi-session repeatability, universal NPU behavior, displayed image quality,
scanout, or energy efficiency. The original 31,500-frame RK3576 campaign and
1,800-frame confirmatory capture remain separate evidence sets. Offline image
quality was not replicated on RK3566.

## Durable evidence and reproduction

Main-repository compact evidence is in `results/rk3566/paper1_replication_v1/`:
`summary.json` contains all 50 per-cell rows and ten aggregate rows;
`terminal.json`, `freeze.json`, `qualification.json`, and `raw_manifest.json`
bind completion, deployment, qualification and raw-file identities.

- Capture source checkpoint: `b4f0479311864785d39549cc3da015a9945e264a`.
- Pre-run freeze SHA-256: `a6f362dad9a74285a43ae2e447936d99e3d12e525e75388e0fc36fc1b88de378`.
- Raw archive: `paper1-rk3566-capture-v1.tar.gz`, 3,006,943 bytes,
  SHA-256 `51b0403e6f6cd962bc5a9a81ffe4e1ca718dbef3f140bf81c0aaa0351c9910eb`.
- All 254 retrieved files match the board-generated per-file manifest.
- All critical deployed source/model/runtime identities matched the freeze after
  capture. Windows/Linux line-ending differences were checked explicitly before
  capture; the manifest pins the exact deployed bytes, not normalized hashes.

`scripts/rk3566/report_paper1_capture_v1.py` recomputes the summary from the full
raw archive, verifies all contiguous frame IDs, source scenes, strict flags,
readback settings and recorded hashes. The compact reviewer package runs
`artifact/paper1_hotmobile2027/verify_rk3566_summary.py` without board access;
it validates per-cell totals and qualification bindings but does not pretend to
replay omitted raw frames. The author retains the raw archive; no public
download, submission, or acceptance is claimed.

The historical Lanczos-requested runtime-label correction is documented
separately in `paper1_historical_lanczos_disclosure_20260911.md`. It does not
invalidate the independent offline Lanczos quality baseline.

Independent outcome review (turn 01a09235-f8b7-7072-aa99-aa7e2286c851) approved
the evidence with one accounting-wording correction: five submitted/completed
requests across 1,500 source frames, not five completions out of 1,500 submitted
requests. That correction is applied. The reviewer checked compact evidence and
hash bindings; the orchestrator, separately, replayed the full raw frame archive.
