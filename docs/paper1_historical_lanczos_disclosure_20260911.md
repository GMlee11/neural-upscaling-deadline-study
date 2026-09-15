# Historical Paper 1 runtime control-label correction

Read-only audit by the Paper 1 task, turn 01a09224-f852-73f3-b07d-0bdb4b7ceb77,
2026-09-11, found archived renderer source at c924449 defaults to bicubic for
immediate fallback. Its later branch selecting the recorded classical method
is unreachable under heterogeneous_progressive. The original runner requests
Lanczos using that backend. The evidence manifest pins aggregates/policy and
evaluation code but not the deployed main.gd/runner bytes.

Therefore historical gpu_lanczos timing rows cannot be advertised as verified
GPU Lanczos execution. Nor should they be definitively relabeled as measured
bicubic without the exact deployment binding. Publication labels now say
"Lanczos req.*" and explicitly exclude a distinct-kernel runtime comparison.
All frozen profile identifiers, numbers, traces and model results remain intact.

The offline evaluator uses Image.Resampling.LANCZOS explicitly, so its independent
Lanczos quality results remain valid within their existing scope. Scheduler
fallback cadence, NPU work reduction, runtime-accepted counts and strict
one-frame eligibility do not depend on treating the nominal classical controls
as different kernels. No rerun of the historical campaign is authorized or needed.

The new RK3566 replication selects the forced shader explicitly; a synthetic
test checks the two actual material/shader identities before measurement.
The fix is gated to rk3566_single_default, preserving historical RK3576 code.
