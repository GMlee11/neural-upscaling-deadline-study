# RK3576 Paper-1 V1 Final Decision

Decision: **reject_paper1_renderer_deadline_claim**.

| Mode | Target | Profile | Display FPS | NPU calls/frame | Strict neural | P95 age | Policy ms |
|---|---:|---|---:|---:|---:|---:|---:|
| mode_180p_to_360p | 30 | always_neural | 29.993 | 1.000 | 0.343 | 92.282 ms | 0.0000 ms |
| mode_180p_to_360p | 30 | fixed_period_2 | 29.997 | 0.500 | 0.109 | 87.376 ms | 0.0000 ms |
| mode_180p_to_360p | 30 | fixed_period_3 | 29.998 | 0.333 | 0.108 | 92.018 ms | 0.0000 ms |
| mode_180p_to_360p | 30 | renderer_deadline_refresh_v1 | 30.007 | 0.610 | 0.174 | 90.232 ms | 0.6068 ms |
| mode_180p_to_360p | 60 | always_neural | 44.823 | 1.000 | 0.000 | 94.075 ms | 0.0000 ms |
| mode_180p_to_360p | 60 | fixed_period_2 | 53.847 | 0.500 | 0.000 | 80.792 ms | 0.0000 ms |
| mode_180p_to_360p | 60 | fixed_period_3 | 54.281 | 0.333 | 0.000 | 70.799 ms | 0.0000 ms |
| mode_180p_to_360p | 60 | renderer_deadline_refresh_v1 | 54.357 | 0.337 | 0.000 | 72.312 ms | 0.5276 ms |
| mode_360p_to_720p | 30 | always_neural | 18.620 | 1.000 | 0.000 | 207.376 ms | 0.0000 ms |
| mode_360p_to_720p | 30 | fixed_period_2 | 25.853 | 0.500 | 0.000 | 171.132 ms | 0.0000 ms |
| mode_360p_to_720p | 30 | fixed_period_3 | 27.001 | 0.333 | 0.000 | 134.892 ms | 0.0000 ms |
| mode_360p_to_720p | 30 | renderer_deadline_refresh_v1 | 30.009 | 0.141 | 0.000 | 127.298 ms | 0.7112 ms |

## Interpretation

- At 360p-to-720p/30, the policy held +61.2% more display throughput than always-neural and avoided 85.9% of NPU submissions.
- It delivered 0.0% neural frames inside the 33.33 ms deadline, so strict displayed quality remained the bicubic fallback.
- The physical always-neural output is valid and aligned: 31.971 dB versus bicubic 31.959 dB, with LPIPS reduced by 36.6%.
- The strict policy scores 31.959 dB / 0.97775 / 0.05451 because no timely neural frame replaced bicubic at 720p.
- This freezes a useful physical boundary result, not a positive renderer/deadline scheduling claim.
- Energy remains unmeasured and no energy-efficiency claim is made.

Failure reasons: `primary_720p_runtime_gate_failed`, `no_720p_neural_frame_met_33_33ms_deadline`, `strict_displayed_quality_gate_failed`, `strict_policy_did_not_beat_bicubic_every_scene`.
