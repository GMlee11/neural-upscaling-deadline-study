# Paper 1 V2: Deadline-Safe Late-Residual Reprojection

Status: **rejected and frozen at the development oracle; V1 remains frozen**

The preregistered development gate rejected V2 on 2026-08-03. The sealed
sequences remain unevaluated, and no Mali/RK3576 implementation is authorized.
See `results/tables/paper1_temporal_reprojection_oracle_v2.md` and
`docs/paper1_temporal_reprojection_v2_result.md`.

## Research Question

Can an embedded renderer salvage neural upscaling corrections that arrive after
their source frame's display deadline by reprojecting only the learned residual
with motion, depth, and disocclusion metadata?

The target is the physical RK3576 render-to-present pipeline, not offline neural
throughput. A classical GPU upscale must always be available immediately.

## Frozen V1 Boundary

Paper 1 V1 remains an immutable adverse baseline. At 360p-to-720p and 30 FPS,
its scheduler maintained display throughput and avoided 85.9% of NPU calls, but
delivered no neural frame within 33.33 ms. Its traces, thresholds, measurements,
and hashes may be used for comparison but not for V2 tuning.

V2 uses new experiment IDs and new temporal traces. It changes the mechanism:
late residuals are reprojected rather than discarded.

## Algorithm Contract

For source frame `s` and current frame `t`:

```text
source_residual = neural_s - classical_s
warped_residual = warp(source_residual, current_to_source_motion)
valid = in_bounds AND depth_consistent AND NOT disoccluded AND NOT HUD
display_t = clamp(classical_t + age_decay * valid * warped_residual)
```

Depth consistency compares the source depth sampled at the motion-projected
coordinate with the depth expected for the current surface in source-frame
space. Invalid pixels fall back to the current classical image. HUD is composed
after upscaling and never receives stale history.

The offline oracle may inspect HR only to answer whether useful headroom exists.
The deployable policy and shader may use renderer and causal runtime state only.

## Novelty Boundary

Temporal super-resolution, motion-vector warping, G-buffer guidance, occlusion
handling, and asynchronous neural execution are established ideas. V2 does not
claim any of them individually.

The candidate systems contribution is narrower:

> deadline-safe salvage of otherwise-late neural residuals from a commodity NPU
> in a low-cost interactive CPU/GPU/NPU graphics pipeline, with explicit
> classical fallback, age-bounded commit, and displayed-result evaluation.

FAST transfers prior super-resolved pixels using compressed-video motion;
modern neural-rendering SR systems use temporal color and G-buffer history;
mobile frame-generation work also uses depth and motion for backward warping.
These systems narrow the novelty claim and must be compared directly. The paper
is viable only if the measured late-result behavior and deadline-safe mechanism
produce a distinct, useful systems result.

## Preregistered Gates

The offline oracle authorizes physical implementation only if reprojected
residuals:

- improve displayed LPIPS over bicubic and Lanczos;
- remain within 0.20 dB PSNR of fresh neural output;
- remain useful at the RK3576's typical two-to-five-frame delays;
- work across at least 80% of development scenes; and
- avoid visible disocclusion, motion-boundary, and HUD failures.

The authorization oracle uses every tenth captured current frame: 30 frames per
scene at each delay, or 120 development observations per delay. This fixed
sampling decision was made from evaluator runtime profiling before quality
results were inspected. Any authorized physical V2 evaluation must use all 300
frames per scene.

The final physical V2 result must:

- sustain 30 FPS for the complete 360p-to-720p render-to-present path;
- beat fixed-period refresh and the frozen V1 discard-late scheduler;
- reuse a meaningful fraction of otherwise-late neural results;
- add no more than 2 ms GPU overhead;
- generalize across untouched sealed scenes; and
- report p95/p99 frame time, frame age, usable-result rate, quality, temporal
  error, deadline misses, neural calls, and visible failure cases.

Failure freezes V2 as a negative result. It does not authorize threshold or
decay retuning on the same sealed sequences.

## Focused Prior Work

- FAST, CVPR Workshops 2017: selective video SR plus motion-vector transfer and
  adaptive handling of occlusion.
- Neural Supersampling for Real-Time Rendering, 2020: temporal reconstruction
  with dense motion and depth.
- FuseSR, SIGGRAPH Asia 2023: temporal SR with LR/HR G-buffer guidance.
- Radiance-demodulated neural SR, CVPR 2024: real-time rendering SR using depth
  and motion while addressing occlusion.
- Decoupled G-buffer-guided video SR, CVPR 2025: temporal refinement using
  rendering buffers.
- Mob-FGSR: mobile backward warping with color, depth, and motion metadata.

The literature review must be refreshed before submission. URLs and full
bibliographic records belong in the eventual V2 manuscript and artifact.
