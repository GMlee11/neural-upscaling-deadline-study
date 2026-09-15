# Paper 1 HotMobile 2027 Evidence

## Physical RK3576 Runtime

| Mode | Control | Fallback/s | Calls/frame | Same-frame neural | P95 age | Policy ms |
|---|---|---:|---:|---:|---:|---:|
| 180p--360p | always_neural | 29.993 | 1.000 | 0.343 | 92.28 ms | 0.000 ms |
| 180p--360p | fixed_period_2 | 29.997 | 0.500 | 0.109 | 87.38 ms | 0.000 ms |
| 180p--360p | gpu_bicubic | 30.013 | 0.000 | 0.000 | 84.42 ms | 0.000 ms |
| 180p--360p | gpu_lanczos | 30.013 | 0.000 | 0.000 | 83.90 ms | 0.000 ms |
| 180p--360p | renderer_deadline_refresh_v1 | 30.007 | 0.610 | 0.174 | 90.23 ms | 0.607 ms |
| 360p--720p | always_neural | 18.620 | 1.000 | 0.000 | 207.38 ms | 0.000 ms |
| 360p--720p | fixed_period_2 | 25.853 | 0.500 | 0.000 | 171.13 ms | 0.000 ms |
| 360p--720p | gpu_bicubic | 30.002 | 0.000 | 0.000 | 85.19 ms | 0.000 ms |
| 360p--720p | gpu_lanczos | 30.004 | 0.000 | 0.000 | 85.05 ms | 0.000 ms |
| 360p--720p | renderer_deadline_refresh_v1 | 30.009 | 0.141 | 0.000 | 127.30 ms | 0.711 ms |

## Complete Primary-Workload Scene Rows

| Scene | Fallback/s | Calls/frame | Same-frame neural | P95 age | Policy ms |
|---|---:|---:|---:|---:|---:|
| barrier_yard | 30.015 | 0.160 | 0.000 | 130.78 ms | 0.653 ms |
| corridor_neon | 30.013 | 0.220 | 0.000 | 123.41 ms | 0.647 ms |
| forest_outpost | 30.005 | 0.080 | 0.000 | 126.31 ms | 0.734 ms |
| hud_particles | 30.012 | 0.080 | 0.000 | 128.57 ms | 0.835 ms |
| reflective_plaza | 29.998 | 0.167 | 0.000 | 127.43 ms | 0.687 ms |

These are all five frozen 360p-to-720p/30-FPS scheduler rows; no scene or threshold was selected after inspection.

## Primary 720p Runtime and Strict Accounting

- Authoritative runtime decision: `reject_refresh_policy_runtime_gate`.
- Authoritative quality decision: `reject_refresh_quality_gate`.
- Historical `display_fps` is computed from immediate fallback-presentation timestamps; it is not a count of every renderer commit.
- The trace partially instantiates the proposed full event contract: it records immediate fallback, terminal routing, acceptance/discard, and age/deadline fields, but not every later composition or physical panel scanout.
- The runtime accepts a source-matched neural result within three frames (100 ms), whereas the strict paper rule credits only results eligible within one frame (33.33 ms).

| Outcome or event | Count | Percent of 1,500 frame records |
|---|---:|---:|
| Submitted and completed | 212 | 14.1% |
| Runtime-accepted neural (within 100 ms) | 172 | 11.5% |
| Completed but discarded late | 40 | 2.7% |
| Refresh bypass, no submission | 1288 | 85.9% |
| Terminal classical route | 1328 | 88.5% |
| Strict one-frame neural eligible | 0 | 0.0% |

Runtime-accepted, late-discarded, and bypassed are mutually exclusive terminal route outcomes. Submission/completion, terminal-classical, and strict-eligibility rows are derived views and must not be summed. The runtime first issues classical fallback for every source record. Runtime acceptance is not a complete later-composition event, so the aggregate supports neither a neural-composition count nor an all-classical composition history.
- The frozen nested `primary_720p_gate.quality_gate_status` value is stale; this reducer reports `strict_quality_gate.decision` and does not rewrite the source result.

## Fresh Confirmatory Quality (Two-Frame Delay)

| Mode | Method | PSNR | SSIM | LPIPS | Valid history |
|---|---|---:|---:|---:|---:|
| 180p--360p | bicubic | 29.457 | 0.95830 | 0.08299 | 0.000 |
| 180p--360p | fresh_neural | 29.318 | 0.95544 | 0.05233 | 1.000 |
| 180p--360p | lanczos | 29.246 | 0.95350 | 0.09716 | 0.000 |
| 180p--360p | motion_depth_disocclusion | 29.414 | 0.95686 | 0.08152 | 0.482 |
| 180p--360p | stale_unwarped | 28.884 | 0.92972 | 0.10431 | 1.000 |
| 360p--720p | bicubic | 32.612 | 0.97728 | 0.05553 | 0.000 |
| 360p--720p | fresh_neural | 32.421 | 0.97559 | 0.03619 | 1.000 |
| 360p--720p | lanczos | 32.406 | 0.97426 | 0.06382 | 0.000 |
| 360p--720p | motion_depth_disocclusion | 32.572 | 0.97636 | 0.05560 | 0.488 |
| 360p--720p | stale_unwarped | 32.025 | 0.95880 | 0.09179 | 1.000 |

The physical scheduler restores the immediate-fallback cadence by declining most NPU work. It accepts 172 neural outcomes under the looser three-frame runtime gate, but none qualifies for strict one-frame 720p credit. Late residual reprojection is preserved as a negative result because its small apparent gains mostly converge back to the classical fallback.

No physical power or energy claim is made.
