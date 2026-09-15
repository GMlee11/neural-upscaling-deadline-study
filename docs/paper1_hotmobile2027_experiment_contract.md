# Paper 1 HotMobile 2027 Experiment Contract

## Research Question

When a compact neural upscaler produces a useful image too late for a mobile
graphics deadline, which system measurements and architectural capabilities are
needed to make that work visible rather than merely complete?

## Venue And Format

The target is ACM HotMobile 2027. The official call requests systems-oriented
papers that expose new directions, constructive critiques, unexpected early
results, or new evaluation methods. Submissions are non-anonymous and limited
to six US-letter pages including references. The hard deadline is October 9,
2026 at 11:59 PM AoE.

This is intentionally a short boundary paper, not a claim that the RK3576
already performs real-time neural 360p-to-720p reconstruction. The physical V1
result is the central observation: reducing NPU submissions restored display
throughput, but no neural result arrived in the same frame. The rejected V2
reprojection oracle is included because it tests the obvious way to salvage
late output and shows where ghosting and disocclusion make reuse unsafe.

## Frozen Confirmatory Suite

Three new deterministic 300-frame scenes are frozen before evaluation:

| Scene | Stressor |
|---|---|
| `p1c_market_pan` | Signs, poles, irregular stalls, lateral motion |
| `p1c_foliage_bridge` | Foliage silhouettes, rails, repeated disocclusion |
| `p1c_industrial_turn` | Reflective panels, pipes, close occluders |

Each scene is rendered at 320x180 to 640x360 and 640x360 to 1280x720, at a
30-FPS target for 300 measured frames after 20 warmups. Native HR, LR, motion,
depth, expected depth, camera state, and timestamps are synchronized.

## Immutable Controls

The campaign compares bicubic, Lanczos, always-neural, fixed-period neural
refresh, the frozen V1 deadline scheduler, and frozen V2 late-residual
reprojection. No threshold, model weight, scene, camera path, age limit, or
refresh period may be changed after confirmatory outputs are inspected.

## Required Measurements

The paper reports simulation, rendering, transfer/readback, request packing,
NPU preparation, NPU inference, reconstruction, output materialization, upload,
queueing, and presentation separately. It also reports display FPS, neural
service FPS, average/p95/p99 frame age, deadline misses, fallback rate, dropped
frames, PSNR, SSIM, LPIPS, and temporal behavior.

Power and energy are out of scope because no calibrated external meter is
available. The manuscript must not infer energy savings from NPU-call counts.

## Interpretation Rule

A late neural frame is not counted as real-time quality. The primary result is
the frame actually displayed at its deadline. Offline neural quality is shown
only to establish that useful work existed and was lost to service latency.

The campaign remains publishable if it confirms a boundary rather than a speed
win, provided the evidence is reproducible and the architectural requirements
follow directly from measured bottlenecks.
