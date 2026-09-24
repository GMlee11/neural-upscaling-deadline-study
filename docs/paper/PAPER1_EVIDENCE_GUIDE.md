# Paper 1 evidence guide

Current scope: corrected source-linked runtime reassessment on RK3576 and
RK3566 across 180p, 360p and 720p outputs: 120 cells and 36,000 sources per board.
The current manuscript and
release manifests are authoritative. This guide reconciles earlier planning
documents without rewriting their frozen contents.

The final prose pass consolidates repeated scope caveats without changing the
evidence. Internal protocol review refers to separate AI-assisted project
sessions, not external human peer review. Dated internal preregistration records
describe the pre-inspection specification; public registration is not claimed.
The shorter Table 2 caption refers to Section 4.1 for its unchanged post hoc
selection rule, eligibility-score distinction and interpretation limits.

## Primary and historical records

- Primary runtime results: `results/{rk3576,rk3566}/paper1_corrected_runtime_v1/`
  (360p/720p) and `results/{rk3576,rk3566}/paper1_180p_output_v1/` (180p).
  Four controls, five scenes, three resolutions and two repetitions per board.
  Both sets use the corrected source-linked presenter. Their original freeze
  identities and sessions remain distinct; Table 1 reports each resolution,
  not a pooled performance estimate across configurations.
  Runtime selection is not physical scanout; the 100-ms acceptance horizon is
  distinct from the strict 33.33-ms first-post-draw freshness objective.
- Offline confirmation: `results/tables/paper1_hotmobile2027_reprojection.json`
  and `results/analysis/paper1_hotmobile2027_reprojection.jsonl`. Per scene,
  resolution, method and delay: 29 PSNR samples and nine SSIM/LPIPS samples.
  Images were produced using the dynamic ONNX source graph from QAT-trained
  weights, not measured target-specific INT8 RKNN outputs. This is independent
  offline quality evidence, not quality joined to runtime-displayed frames.
- Historical planning: `docs/paper1_hotmobile2027_experiment_contract.md`,
  `docs/paper1_renderer_deadline_refresh_v1.md`, and
  `docs/paper1_temporal_reprojection_v2_contract.md` describe earlier campaign
  identities and must not be read as the corrected-runtime protocol. Their old
  control lists, display terminology and zero-result statements are not current
  primary claims. Frozen files are retained unchanged for provenance.
- Earlier runtime, composition-audit and repair records are separate history.
  Their outcomes are never pooled with or relabeled as corrected measurements.
  The current 180p RK3576 always-neural result includes 1,032 timely sources,
  and the 360p result includes 12; an
  unqualified historical statement of zero timely delivery does not describe it.

## Commit and hash interpretation

`artifact/paper1_hotmobile2027/historical_provenance.json` is an older inventory
snapshot. Its `release_source_commit` binds historical excluded-file provenance,
not the current manuscript or complete current package. Its old exclusion of the
frame-level offline observation JSONL describes that older snapshot; the current
package now includes an exact hash-matching copy for metric audit. All other
historically excluded files remain outside this minimal package.

Use `expected_outputs.json` for
claims-bearing hashes, and `release_manifest.json` plus `FILES.txt` for the
complete current package. Internal review prompts, reviewer-response memoranda
and the old displayed-result audit are retained in the development repository,
not included in the current reviewer release. They are not publication evidence
or an actual venue decision.

## Reproduction and availability

Paper exhibit map: the package-root `README.md` identifies the inputs and checks
for Tables 1-3. Run its `reproduce.ps1` command to regenerate
and byte-compare the exhibits in temporary space and replay both board archives.
Table 1's source rate is the equal-cell arithmetic mean of per-cell rates, not
an average of intervals. Table 3's observation check validates stored metric
means, not fresh inference or image-metric computation. Table 2 is regenerated
from saved event records. No board is needed for these checks.

The corrected-table generator also derives Table 2 directly from the saved
RK3576 composition and selection-event logs. Its post hoc illustration rule is
the first receipt-side eligible 360p always-neural source in cell-execution/source-ID
order in each repetition, without filtering on post-draw latency. This selects
cell 01/source 9 and cell 46/source 192. Times are relative to source capture;
receipt uses worker_received_usec, assignment uses the stamp just after the
assignment, and post-draw uses the first source-matched neural draw. The eligibility
score adds assignment duration to receipt age; it is not the assignment timestamp.
Both examples are late at post-draw, but are not population estimates or a causal
decomposition. Regression tests check those values and byte-identical generation.
The reported fallback/draw rates are unchanged equal-cell summary fields; draws
may repeat content and do not count unique neural sources or physical scanout.

Receipt-side eligibility is a score (receipt age plus assignment operation
duration), not elapsed age at assignment. Intervening waiting is excluded.
Table 2 now prints both score calculations separately from event timestamps.
The raw fields and reduction remain unchanged; `eligible` in saved summaries
retains this original receipt-side definition. Timely delivery continues to use
the first source-linked post-draw age, including all elapsed time since capture.

Deployment configuration is inside each corrected-runtime capture archive:
`freeze.json` contains dated platform/environment records, model/runtime hash
bindings and all 80 commands; `capture-v1/<cell>/command.json` records each
executed command and `system.jsonl` records per-cell system observations. Both
boards contain 80 command files and 80 system logs. The included engineering
archives preserve qualification evidence. These are execution records and
bindings, not a claim that every external dependency or model binary is bundled.

The non-mutating replay checks archived runtime events and reductions. The
offline-observation test checks sampling counts and stored summary means; it
does not rerun neural inference or recalculate image metrics from raw images.
The raw confirmatory image corpus is not bundled here. The 180p capture archives
retain their small compiled model as part of the immutable frozen-input snapshot;
that is not a turnkey board installer or permission to redistribute dependencies.

## Three-resolution runtime evidence

The 180p captures contain 40 cells / 12,000 sources per board; the 360p/720p
captures contain 80 cells / 24,000 sources per board. Across all resolutions,
72,000 sources support Table 1. Each row still has exactly 3,000 sources.
All neural outputs are scaled into the unchanged 1280x720 root window.
At 180p, RK3576 always-neural has 2,791 receipt-side eligible responses,
3,000 eventual neural selections and 1,032 timely first post-draw selections.
RK3566 has 3,000 eventual selections and zero eligible/timely selections.

The 180p archives include `protocol.md`, `freeze.json`, the exact 40 commands,
qualification records, compiler metadata, numerical fixtures and raw captures.
`verify_180p_runtime.py` checks local freeze bindings, all 321 capture-file
identities per board and byte-bound support modules, then reproduces the entire
summary in memory. It neither executes archived code nor contacts a board.
External board-file identities are attestations, not live rereads by this replay.

The 180p and 360p/720p sessions differ in compiled shape and input-view adapter;
RK3576 also uses a separate Xorg display with its idle greeter stopped at 180p.
The R8 adapter preserves all 43,200 input bytes while aligning the row layout.
Weights, ordered calibration inputs, acceptance rules and inherited scheduler
parameters were not retuned. Shader caches were not cold-cache controlled.
Standalone compiler stdout logs were not retained; compiler metadata and the
original engineering transcript remain the provenance, not reconstructed logs.
Cross-resolution results are descriptive, not an isolated causal resolution test.
The offline quality evaluation covers 360p and 720p only.

This is a local package, not proof of public or reviewer access. The author must
establish access via the designated repository or venue-supported supplement
and update the manuscript availability statement only after verifying access.
Licensing and third-party notices must be resolved before public distribution.
No upload, submission, acceptance, DOI or venue rights are implied.

Author release checklist: choose an appropriate license and retain third-party
notices; upload only this allowlisted package; preserve the freeze records and
exact evidence bytes; identify a stable release/tag or commit; check the README
and reproduction command from a separate checkout; confirm reviewer access while
signed out (or through the venue's supported access mechanism); then replace the
manuscript's pending-access paragraph with the verified release location. A dated
freeze record is provenance, not proof of prior public registration.
