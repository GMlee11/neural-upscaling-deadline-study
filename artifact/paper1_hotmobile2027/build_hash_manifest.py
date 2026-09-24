"""Create the Paper 1 claims-bearing SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifact/paper1_hotmobile2027/expected_outputs.json"

# Bind the evidence, frozen replay support and generated exhibit fragments.
# The submission manuscript and PDF are intentionally outside this artifact.
EXPECTED_PATHS = (
    'artifact/paper1_hotmobile2027/verify_180p_runtime.py',
    'tests/test_paper1_three_resolution_artifact.py',
    'results/rk3576/paper1_180p_output_v1/capture-evidence-v1.tar.gz',
    'results/analysis/paper1_180p_output_v1_rk3576.json',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3576/report.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3576/validate.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3576/design.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3576/neural_refresh_policy.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3576/policy.json',
    'results/rk3566/paper1_180p_output_v1/capture-evidence-v1.tar.gz',
    'results/analysis/paper1_180p_output_v1_rk3566.json',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3566/report.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3566/validate.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3566/design.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3566/neural_refresh_policy.py',
    'artifact/paper1_hotmobile2027/runtime_180p/rk3566/policy.json',

    "results/analysis/paper1_hotmobile2027_reprojection.jsonl",
    "docs/paper/PAPER1_EVIDENCE_GUIDE.md",
    "results/rk3576/paper1_corrected_runtime_v1/engineering-evidence-v2.tar.gz",
    "results/rk3566/paper1_corrected_runtime_v1/engineering-evidence-v1.tar.gz",
    "results/rk3576/paper1_corrected_runtime_v1/capture-evidence-v1.tar.gz",
    "results/rk3576/paper1_corrected_runtime_v1/summary-v1.json",
    "results/rk3566/paper1_corrected_runtime_v1/capture-evidence-v1.tar.gz",
    "results/rk3566/paper1_corrected_runtime_v1/summary-v1.json",
    "artifact/paper1_hotmobile2027/verify_corrected_runtime.py",
    "artifact/paper1_hotmobile2027/corrected_runtime/report.py",
    "artifact/paper1_hotmobile2027/corrected_runtime/validate.py",
    "artifact/paper1_hotmobile2027/corrected_runtime/design.py",
    "artifact/paper1_hotmobile2027/corrected_runtime/neural_refresh_policy.py",
    "artifact/paper1_hotmobile2027/corrected_runtime/policy.json",
    "src/report/paper1_corrected_runtime_v1.py",
    "tests/test_paper1_corrected_artifact.py",
    "docs/paper/generated/paper1_corrected_runtime_v1.tex",
    "results/rk3576/paper1_prompt_selection_v1/capture-evidence-v1.tar.gz",
    "results/rk3576/paper1_prompt_selection_v1/engineering-checkpoint-v2.tar.gz",
    "results/rk3576/paper1_prompt_selection_v1/summary.json",
    "artifact/paper1_hotmobile2027/verify_prompt_selection.py",
    "tests/test_paper1_prompt_artifact.py",
    "docs/paper1_prompt_selection_v1_result.md",
    "results/rk3566/paper1_composition_audit_v1/capture-evidence-v1.tar.gz",
    "results/rk3566/paper1_composition_audit_v1/summary.json",
    "results/rk3576/paper1_composition_audit_v1/capture-evidence-v1.tar.gz",
    "results/rk3576/paper1_composition_audit_v1/summary.json",
    "artifact/paper1_hotmobile2027/verify_composition_audits.py",
    "artifact/paper1_hotmobile2027/explain_composition_timing.py",
    "tests/test_paper1_composition_artifact.py",
    "results/rk3566/paper1_replication_v1/summary.json",
    "results/rk3566/paper1_replication_v1/terminal.json",
    "results/rk3566/paper1_replication_v1/freeze.json",
    "results/rk3566/paper1_replication_v1/qualification.json",
    "results/rk3566/paper1_replication_v1/raw_manifest.json",
    "docs/paper1_rk3566_replication_result_v1.md",
    "docs/paper1_historical_lanczos_disclosure_20260911.md",
    "artifact/paper1_hotmobile2027/verify_rk3566_summary.py",
    "configs/paper1_hotmobile2027_replay.yaml",
    "configs/rk3576_refresh_scheduler_paper1_v1.yaml",
    "configs/rk3576_refresh_quality_paper1_v1.yaml",
    "docs/paper1_hotmobile2027_experiment_contract.md",
    "docs/paper1_renderer_deadline_refresh_v1.md",
    "docs/paper1_temporal_reprojection_v2_contract.md",
    "docs/paper1_temporal_reprojection_v2_result.md",
    "results/manifests/rk3576_paper1_v1_evidence_manifest.json",
    "results/models/rk3576_neural_refresh_paper1_v1.json",
    "results/models/student_npu_w24_int8/student_npu_w24_runtime_dynamic.manifest.json",
    "results/tables/rk3576_refresh_scheduler_paper1_v1.json",
    "results/tables/rk3576_refresh_quality_paper1_v1.json",
    "results/tables/rk3576_paper1_v1_final_decision.json",
    "results/tables/paper1_hotmobile2027_reprojection.json",
    "results/tables/paper1_hotmobile2027_workshop.json",
    "results/tables/paper1_hotmobile2027_workshop.md",
    "results/analysis/paper1_hotmobile2027_temporal_manifest.jsonl",
    "results/rk3576/phase13_npu_width_integrated/student_npu_w24_int8/always_full/mode_180p_to_360p/30fps/buffers3/godot_frames.jsonl",
    "results/rk3576/phase13_npu_width_integrated/student_npu_w24_int8/always_full/mode_360p_to_720p/30fps/buffers3/godot_frames.jsonl",
    "artifact/paper1_hotmobile2027/historical_provenance.json",
    "src/report/paper1_hotmobile2027_workshop.py",
    "docs/paper/generated/paper1_hotmobile2027.tex",
)


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest without loading a file at once."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest() -> dict[str, object]:
    """Describe every claims-bearing output and reject missing evidence."""

    rows = []
    for relative in EXPECTED_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        rows.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": 3,
        "artifact": "paper1_hotmobile2027_v1_claims",
        "distribution_scope": "evidence_and_reproduction_only_no_manuscript_or_pdf",
        "files": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the deterministic manifest-generation command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write the hash manifest after a successful report and paper build."""

    args = build_parser().parse_args(argv)
    payload = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PAPER1_HOTMOBILE_HASH_MANIFEST files={len(payload['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
