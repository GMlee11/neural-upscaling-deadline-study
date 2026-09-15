# Paper 1 corrected-runtime V1: RK3566 outcome

2026-09-15. COMPLETE; local replay PASS; independent outcome review PASS.
The Orange Pi 3B finished its single frozen 80-cell campaign with 24,000 sources,
no replacement cells, reported capture failure or frozen-input drift. The same
five existing scenes, two resolutions, four controls and two repetitions were
prescribed as on RK3576, with separately qualified target-specific native software.
This is a controlled reassessment of previously examined workloads, not untouched
confirmation or a hardware-matched comparison of chip speed.

## Evidence and verification

- Capture: `results/rk3566/paper1_corrected_runtime_v1/capture-evidence-v1.tar.gz`.
  9,500,941 bytes; SHA-256
  `585a9d1c689038f9c781ba6fb4bed2bb3c47791d6f7289a875de67b4f0189ee5`.
- Summary: `results/rk3566/paper1_corrected_runtime_v1/summary-v1.json`.
  SHA-256 `1aa4450c0b96d52e61648f9afc2a34483ec5429988110a8d07ce397f9147ca1e`.
- Freeze: `97661ab591324a3d6a276835bee985ad594725482ecd5bb1c836d8f65fd5b547`.
- All 641 capture manifest entries verify; the archive has 647 regular files.
  All 80 commands and scene/source identities match the freeze. Full local
  replay equals the entire board summary, not just selected headline fields.
- Independent raw timestamp arithmetic, control checks, source counts, rates,
  qualification/approval identities and repetition accounting pass. See
  `docs/reviews/paper1_corrected_runtime_v1_rk3566_outcome_review.md`.
- 3,811 temperature observations span 40.000--57.222 C; no 80 C stop violation.
  First samples are at most 55.000 C. This does not identify causes of latency.
- The capture process exited and the board archive was synced before SCP.
  Remote/local archive and summary hashes match. No further board run is needed.

## Primary results

Every row contains **3,000 source frames**, including bypassed and late sources.
Eligible means receipt age plus assignment time <=33.33 ms. Selected means a
source-linked neural root-output draw was observed. Timely means the first
post-draw occurred within 33.33 ms. Runtime acceptance separately allows receipt
through 100 ms. None of these events measures physical panel scanout.

| Output | Control | Submitted | Eligible | Selected | Timely | Mean source captures/s |
|---|---|---:|---:|---:|---:|---:|
| 360p | Bicubic | 0 | 0 | 0 | 0 | 28.99 |
| 360p | Always neural | 3,000 | 0 | 2,975 | 0 | 21.68 |
| 360p | Fixed/2 | 1,500 | 0 | 1,500 | 0 | 24.26 |
| 360p | Frozen scheduler | 1,403 | 0 | 1,402 | 0 | 23.51 |
| 720p | Bicubic | 0 | 0 | 0 | 0 | 24.59 |
| 720p | Always neural | 3,000 | 0 | 0 | 0 | 8.24 |
| 720p | Fixed/2 | 1,500 | 0 | 0 | 0 | 12.67 |
| 720p | Frozen scheduler | 10 | 0 | 0 | 0 | 24.47 |

Rates are equal-cell means of 299 intervals divided by first-to-last capture
time, not panel FPS. Bicubic intentionally has no neural work; its neural zeros
are not classical-delivery failures. Every submitted request completes.

At 360p, always-neural discards 25 late responses; fixed/2 deliberately bypasses
1,500 sources; the scheduler bypasses 1,597 and discards one late. At 720p, every
submitted request is late even under the runtime acceptance rule. The scheduler
bypasses 2,990 sources (99.667%), preserving approximately classical cadence, not
30 Hz or timely neural enhancement.

Both repetitions have zero strict eligible, timely pre-draw and timely post-draw
sources in every cell. At 360p, always selects 1,490 then 1,485; fixed/2 selects
750 each; the scheduler submits 696 then 707 and selects 696 then 706. At 720p,
the scheduler submits five requests per repetition, all late. One session with
two repetitions does not establish cross-session robustness.

## What the replication adds

RK3576 occasionally delivers timely 360p neural results (12/3,000 always-neural
sources); RK3566 does not. Both have zero timely neural selections at 720p.
On each board, eventual acceptance and preserved classical-like source cadence
are different from one-frame neural delivery. Different runtime stacks, model
compilation, concurrency and rendering prevent attributing absolute differences
solely to the chip. The result does not establish a universal NPU limitation.

New corrected matrices replace historical runtime rows as primary evidence.
Old traces remain labeled and unpooled; offline quality/reprojection remains
unchanged. Reproduce both new captures without hardware using
`python -B artifact/paper1_hotmobile2027/verify_corrected_runtime.py`.
