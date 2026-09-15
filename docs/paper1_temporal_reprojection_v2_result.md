# Paper 1 V2 Temporal-Reprojection Result

Status: **rejected; physical implementation not authorized**

## What Was Tested

Six new 300-frame temporal sequences were captured at 30 FPS with synchronized
640x360 input, 1280x720 reference, motion, current depth, expected historical
depth, and frozen neural output. Four sequences were designated development and
two were sealed before evaluation.

The offline reference simulated neural residuals arriving one to five frames
late. It performed backward motion reprojection, depth consistency checks,
disocclusion rejection, HUD exclusion, age decay, and classical fallback. The
authorization sample used 30 deterministic frames per scene and delay. The two
sealed sequences were not read by the quality evaluator.

## Development Result

| Delay | Reprojected PSNR | Reprojected LPIPS | Valid history | Useful scenes | Gate |
|---:|---:|---:|---:|---:|---|
| 2 frames | 31.927 dB | 0.05773 | 49.4% | 1/4 | Fail |
| 3 frames | 31.980 dB | 0.05725 | 42.2% | 3/4 | Fail |
| 4 frames | 32.002 dB | 0.05713 | 36.4% | 4/4 | Pass numerically |
| 5 frames | 32.008 dB | 0.05717 | 31.6% | 4/4 | Pass numerically |

The classical controls were 32.014 dB / 0.05726 LPIPS for bicubic and 31.831 dB
/ 0.06635 LPIPS for Lanczos. Fresh neural output was 31.650 dB / 0.03400 LPIPS.
The frozen model therefore remained perceptually stronger but less accurate by
PSNR than bicubic on these new scenes.

## Interpretation

At two frames late, reprojection was perceptually worse than bicubic in three of
four scenes. At three frames, it missed the preregistered 80% scene requirement.
The four- and five-frame rows drifted back toward bicubic because only 36.4% and
31.6% of neural history remained valid and the age decay weakened what survived.
Their LPIPS gains over bicubic were only 0.00013 and 0.00009, respectively.
That is fallback behavior, not a meaningful salvage of late neural quality.

Adding an unwarped stale residual was much worse, reaching 0.096-0.119 LPIPS at
two-to-five frames. The HR-visible MSE oracle selected bicubic on aggregate,
which confirms that late residual reuse did not improve pixel fidelity.

## Decision

The preregistered decision is `reject_temporal_reprojection_v2`.

- Do not implement this mechanism in the Mali shader or RK3576 runtime.
- Do not evaluate the sealed `v2_particle_gate` or `v2_occlusion_lab` sequences.
- Do not retune depth thresholds, age decay, or sampling on these traces.
- Preserve V1 and V2 as separate adverse results.
- Keep Paper 2 as the positive FPGA architecture paper and Paper 3 as the
  cross-platform co-design boundary paper.

The branch can be revisited only as a genuinely new V3 hypothesis using new
development traces and a mechanism materially different from pixel-space late
residual reprojection.
