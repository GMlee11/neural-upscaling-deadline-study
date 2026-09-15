"""Regression tests for the focused Paper 1 reviewer package."""

from __future__ import annotations

import json
from pathlib import Path

from artifact.paper1_hotmobile2027.build_hash_manifest import (
    EXPECTED_PATHS,
    build_manifest,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]


def test_claims_manifest_covers_both_evidence_sets() -> None:
    """Require physical timing, fresh quality and replay code in the freeze."""

    expected = set(EXPECTED_PATHS)
    assert "configs/paper1_hotmobile2027_replay.yaml" in expected
    assert "results/tables/rk3576_paper1_v1_final_decision.json" in expected
    assert "results/tables/rk3576_refresh_scheduler_paper1_v1.json" in expected
    assert "results/tables/rk3576_refresh_quality_paper1_v1.json" in expected
    assert "results/manifests/rk3576_paper1_v1_evidence_manifest.json" in expected
    assert "results/models/rk3576_neural_refresh_paper1_v1.json" in expected
    assert "docs/paper1_renderer_deadline_refresh_v1.md" in expected
    assert "src/report/paper1_hotmobile2027_workshop.py" in expected
    assert "results/tables/paper1_hotmobile2027_reprojection.json" in expected
    assert "results/analysis/paper1_hotmobile2027_temporal_manifest.jsonl" in expected
    assert "artifact/paper1_hotmobile2027/historical_provenance.json" in expected
    assert "results/tables/paper1_hotmobile2027_workshop.json" in expected
    assert (
        "results/rk3576/phase13_npu_width_integrated/student_npu_w24_int8/"
        "always_full/mode_180p_to_360p/30fps/buffers3/godot_frames.jsonl"
        in expected
    )
    assert (
        "results/rk3576/phase13_npu_width_integrated/student_npu_w24_int8/"
        "always_full/mode_360p_to_720p/30fps/buffers3/godot_frames.jsonl"
        in expected
    )
    assert "docs/paper/paper1_hotmobile2027.tex" not in expected
    assert "output/pdf/paper1_hotmobile2027.pdf" not in expected


def test_claims_manifest_hashes_every_declared_file() -> None:
    """Build a complete SHA-256 manifest without accepting missing outputs."""

    payload = build_manifest()
    rows = payload["files"]
    assert isinstance(rows, list)
    assert len(rows) == len(EXPECTED_PATHS)
    assert all(len(str(row["sha256"])) == 64 for row in rows)
    assert all((ROOT / str(row["path"])).is_file() for row in rows)


def test_compact_v1_provenance_chain_matches_frozen_decision() -> None:
    """Trace the 31,500-frame decision through compact canonical summaries."""

    decision = json.loads(
        (ROOT / "results/tables/rk3576_paper1_v1_final_decision.json").read_text(
            encoding="utf-8"
        )
    )
    evidence_manifest = json.loads(
        (
            ROOT / "results/manifests/rk3576_paper1_v1_evidence_manifest.json"
        ).read_text(encoding="utf-8")
    )
    support = {str(row["path"]): row for row in evidence_manifest["support_files"]}
    packaged = (
        "configs/rk3576_refresh_scheduler_paper1_v1.yaml",
        "configs/rk3576_refresh_quality_paper1_v1.yaml",
        "results/models/rk3576_neural_refresh_paper1_v1.json",
        "results/tables/rk3576_refresh_scheduler_paper1_v1.json",
        "results/tables/rk3576_refresh_quality_paper1_v1.json",
        "results/tables/rk3576_paper1_v1_final_decision.json",
    )
    for relative in packaged:
        assert sha256_file(ROOT / relative) == support[relative]["sha256"]

    assert decision["physical_scope"] == {
        "power_measured": False,
        "quality_frames": 1500,
        "runtime_frames": 31500,
        "runtime_rows": 105,
        "scene_count": 5,
    }
    assert decision["source_reports"]["runtime_sha256"] == sha256_file(
        ROOT / "results/tables/rk3576_refresh_scheduler_paper1_v1.json"
    )
    assert decision["source_reports"]["quality_sha256"] == sha256_file(
        ROOT / "results/tables/rk3576_refresh_quality_paper1_v1.json"
    )


def test_displayed_result_reporting_uses_authoritative_final_gate() -> None:
    """Document the legacy nested status while reporting the final decision."""

    decision = json.loads(
        (ROOT / "results/tables/rk3576_paper1_v1_final_decision.json").read_text(
            encoding="utf-8"
        )
    )
    workshop = json.loads(
        (ROOT / "results/tables/paper1_hotmobile2027_workshop.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        decision["primary_720p_gate"]["quality_gate_status"]
        == "pending_fresh_trace_quality_evaluation"
    )
    gate = workshop["displayed_result_gate"]
    assert gate["authoritative_quality_path"] == "strict_quality_gate"
    assert gate["strict_quality_decision"] == "reject_refresh_quality_gate"
    assert gate["strict_720p_same_frame_neural_fraction"] == 0.0
    assert gate["runtime_accepted_neural_count"] == 172
    assert gate["strict_same_frame_eligible_count"] == 0
    assert (
        gate["provenance_interpretation"]
        == "runtime_acceptance_and_strict_eligibility_do_not_establish_"
        "complete_composition_history"
    )
    instrumentation = workshop["historical_instrumentation"]
    assert instrumentation["contract_instantiation"] == "partial"
    assert instrumentation["observed_events"] == [
        "immediate_fallback_presentation",
        "terminal_runtime_route",
        "runtime_acceptance_or_discard",
        "frame_age_and_deadline_fields",
    ]
    assert instrumentation["unobserved_events"] == [
        "complete_later_renderer_composition_log",
        "physical_panel_scanout",
    ]
    accounting = workshop["primary_runtime_accounting"]
    assert accounting["denominator_frame_records"] == 1500
    assert accounting["submitted_count"] == 212
    assert accounting["completed_count"] == 212
    assert accounting["runtime_accepted_neural_count"] == 172
    assert accounting["late_discarded_neural_count"] == 40
    assert accounting["bypassed_count"] == 1288
    assert accounting["terminal_classical_route_count"] == 1328
    assert accounting["strict_same_frame_eligible_count"] == 0
    assert workshop["power_claim_supported"] is False


def test_generated_primary_figure_preserves_zero_timely_720p_boundary() -> None:
    """Keep the publication figure tied to recorded aggregate fields only."""

    rendered = (
        ROOT / "docs/paper/generated/paper1_hotmobile2027.tex"
    ).read_text(encoding="utf-8")
    assert "label{fig:displayed-provenance}" in rendered
    assert (
        "360p--720p & Deadline & 30.01 & 0.141 & 127.3 ms & 0.0\\% & "
        "0\\% strict; runtime route separate" in rendered
    )
    assert "Runtime-accepted neural & 172 & 11.5\\%" in rendered
    assert "immediate-fallback timestamps" in rendered
    assert "runtime acceptance is recorded, later composition and scanout are not" in rendered


def test_artifact_requirements_cover_focused_import_graph() -> None:
    """Keep the reviewer dependency set minimal and experiment-free."""

    requirements = set(
        (
            ROOT / "artifact/paper1_hotmobile2027/requirements.txt"
        ).read_text(encoding="utf-8").splitlines()
    )
    assert requirements == {"pytest==9.1.1", "PyYAML==6.0.3"}


def test_excluded_claim_adjacent_files_are_hash_pinned() -> None:
    """Keep excluded raw, board, model, and experiment files auditable."""

    provenance = json.loads(
        (
            ROOT / "artifact/paper1_hotmobile2027/historical_provenance.json"
        ).read_text(encoding="utf-8")
    )
    rows = provenance["excluded_files"]
    assert len(rows) == 26
    assert all(len(str(row["sha256"])) == 64 for row in rows)
    included = "results/analysis/paper1_hotmobile2027_reprojection.jsonl"
    assert sum(row['path'] == included for row in rows) == 1
    for row in rows:
        path = ROOT / str(row['path'])
        if row['path'] == included:
            assert sha256_file(path) == row['sha256']
        else:
            assert not path.exists()


def test_artifact_inventory_excludes_submission_material():
    paths = (ROOT / "FILES.txt").read_text(encoding="utf-8").splitlines()
    assert not any(path.endswith((".pdf", ".bib")) or path.startswith("paper/") for path in paths)
    assert "docs/paper/paper1_hotmobile2027.tex" not in paths
    assert "SUBMISSION_CHECKLIST.md" not in paths
