# Paper 1: frozen prompt-selection comparison

2026-09-14. COMPLETE; independent outcome review PASS. No further capture is
needed for this comparison. Historical experiments remain unchanged.

## Design and evidence

The RK3576 corridor-scene comparison uses unchanged width-24 INT8 computation,
depth three, three slots, source matching, 100-ms runtime acceptance, and a
33.33-ms retrospective freshness deadline. Ordered and process-frame prompt
presentation share instrumentation. Two repetitions reverse mode order across
both resolutions and bicubic/always-neural controls: 16 cells of 300 source
frames, 4,800 total, one physical session. Every cell completed; no retries,
replacement samples, or frozen-file drift were recorded.

The prompt policy chooses the oldest ready source without neural-source
regression and retires native storage only after validated draw and detachment.
Expired and superseded sources remain in all-source denominators. Engineering
qualification precedes freeze: source-coded root pixels, unchanged-native
numerical comparisons (18 cases), ownership, expiry and failure-path checks.
Failed engineering iterations are preserved, not counted as scientific samples.

Capture archive SHA-256:
`7b86447b0ea48953131861d28228ff181df8fa74b0b64a8b26367c45e27da854`.
Archived freeze SHA-256:
`c4d733744e3ce10305d16155bc00cb3bbff41871c558b1857d6cd55f416598c8`.
Engineering V2 archive SHA-256:
`31da57c2604b5335ddb0d929edcceea362bdff3af670ce80740c97323cb1fd9a`.
The capture archive contains its frozen protocol, qualification identity,
independent design approval and all 114 hash-manifested capture files.

## Outcome

Each row below has 300 source frames. Output resolution is not window size.
Median age is measured at first neural post-draw, among selected sources.

| Output | Repeat | Policy | Response eligible | Selected | Timely post-draw | Median age (ms) |
|---|---:|---|---:|---:|---:|---:|
| 360p | 1 | Ordered | 84 | 300 | 0 | 98.0125 |
| 360p | 1 | Prompt | 184 | 300 | 6 | 48.0295 |
| 360p | 2 | Ordered | 108 | 300 | 0 | 110.7315 |
| 360p | 2 | Prompt | 139 | 300 | 5 | 50.6555 |
| 720p | 1 | Ordered | 0 | 299 | 0 | 183.193 |
| 720p | 1 | Prompt | 0 | 247 | 0 | 110.960 |
| 720p | 2 | Ordered | 0 | 95 | 0 | 203.670 |
| 720p | 2 | Prompt | 0 | 81 | 0 | 115.459 |

At 360p both policies eventually select all 600 sources. Timely post-draw
selection rises from 0/600 to 11/600 (1.83%). Prompt's 68/600 timely pre-draw
observations and 323/600 eligible responses are different boundaries, not
substitutes for the primary 11 timely post-draw observations. Ordered response
eligibility is 192/600. Bicubic capture-start rates remain 30.14-30.15/s.

At 720p both policies have zero eligible and timely-selected sources. Prompt
retains 264 late discards and eight superseded sources; ordered retains 206
late discards. Selected counts vary substantially between repetitions. The
720p conditional medians compare different selected subsets and cannot support
a paired same-source speedup or an all-source latency improvement.

## Interpretation and reproduction

The complete presentation policy reduces lower-mode selection age, but does
not produce reliable one-frame neural delivery. Changed load, overlap, capture
pacing and disposition behavior prevent attribution to one isolated wait.
This is not an intrinsic NPU limit, cross-session generality, GPU-completion or
panel-scanout measurement, or pixelwise validation of every captured image.
No prompt-plus-deadline-scheduler result is claimed. The separate corrected
720p observation does not retroactively repair historical logs.

Run `python -B artifact/paper1_hotmobile2027/verify_prompt_selection.py` to
verify all 114 capture hashes and reproduce raw-timestamp eligibility and
selection counts against `summary.json`, without extraction, archived-code
execution, inference or board access. Independent review additionally checked
the exact archive set, frozen dependency closure, command order, medians,
terminal routes, ownership, entry/stop conditions and all 16 validators.
