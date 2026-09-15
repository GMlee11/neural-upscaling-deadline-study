"""Tests for the Paper 1 workshop evidence reducer."""

from __future__ import annotations

import pytest

from src.report.paper1_hotmobile2027_workshop import (
    build_primary_runtime_accounting,
    render_generated_tex,
    select_quality_rows,
    select_runtime_rows,
    select_scene_runtime_rows,
)


# Build the minimum complete five-profile, two-resolution control matrix. The
# reducer must reject missing rows rather than silently producing a paper table
# with unmatched experiments.
def _runtime_report() -> dict[str, object]:
    """Return one complete synthetic physical decision report."""

    rows = []
    profiles = (
        "gpu_bicubic",
        "gpu_lanczos",
        "always_neural",
        "fixed_period_2",
        "renderer_deadline_refresh_v1",
    )
    for mode in ("mode_180p_to_360p", "mode_360p_to_720p"):
        for profile in profiles:
            strict = 0.0
            if mode == "mode_180p_to_360p" and profile not in {
                "gpu_bicubic",
                "gpu_lanczos",
            }:
                strict = 0.25
            rows.append(
                {
                    "mode_id": mode,
                    "target_fps": 30,
                    "profile_id": profile,
                    "display_fps": 30.0,
                    "npu_invocations_per_frame": 0.5,
                    "strict_same_frame_neural_fraction": strict,
                    "p95_frame_age_ms": 80.0,
                    "mean_refresh_selector_ms": 0.5,
                }
            )
    return {"runtime_summary": rows}


def _quality_report() -> dict[str, object]:
    """Return the required age-two confirmatory quality methods."""

    rows = []
    methods = (
        "bicubic",
        "lanczos",
        "fresh_neural",
        "stale_unwarped",
        "motion_depth_disocclusion",
    )
    for mode in ("mode_180p_to_360p", "mode_360p_to_720p"):
        for method in methods:
            rows.append(
                {
                    "mode_id": mode,
                    "method": method,
                    "age_frames": 2,
                    "scene_equal_psnr": 30.0,
                    "scene_equal_ssim": 0.95,
                    "scene_equal_lpips": 0.05,
                    "mean_valid_history_fraction": 0.5,
                }
            )
    return {"summary": rows}


def _scene_runtime_report() -> dict[str, object]:
    """Return the complete frozen-scene identity expected by the reducer."""

    scenes = (
        "barrier_yard",
        "corridor_neon",
        "forest_outpost",
        "hud_particles",
        "reflective_plaza",
    )
    return {
        "runs": [
            {
                "mode_id": "mode_360p_to_720p",
                "target_fps": 30,
                "profile_id": "renderer_deadline_refresh_v1",
                "scene_variant": scene,
                "frame_count": 300,
                "display_fps": 30.0,
                "npu_invocations_per_frame": 0.1,
                "strict_same_frame_neural_fraction": 0.0,
                "p95_frame_age_ms": 127.0,
                "mean_refresh_selector_ms": 0.7,
                "deadline_ms": 100.0,
                "npu_completed_frames": 30,
                "deadline_miss_count": 6,
                "accepted_neural_fraction": 0.08,
                "refresh_action_counts": {"submit": 30, "bypass": 270},
                "route_status_counts": {
                    "accepted_neural": 24,
                    "client_late_neural_discarded": 6,
                    "refresh_policy_bypass": 270,
                },
            }
            for scene in scenes
        ]
    }


def _runtime_policy() -> dict[str, object]:
    """Return the frozen primary workload age bound expected by accounting."""

    return {
        "supported_workloads": [
            {
                "mode_id": "mode_360p_to_720p",
                "target_fps": 30,
                "maximum_refresh_age_frames": 3,
            }
        ]
    }


def test_workshop_selectors_require_complete_matched_tables() -> None:
    """Accept complete controls and reject an incomplete physical matrix."""

    runtime = select_runtime_rows(_runtime_report())
    quality = select_quality_rows(_quality_report())
    scene_runtime = select_scene_runtime_rows(_scene_runtime_report())
    assert len(runtime) == 10
    assert len(quality) == 10
    assert len(scene_runtime) == 5

    incomplete = _runtime_report()
    incomplete["runtime_summary"].pop()  # type: ignore[index,union-attr]
    with pytest.raises(ValueError, match="expected 10"):
        select_runtime_rows(incomplete)

    incomplete_scenes = _scene_runtime_report()
    incomplete_scenes["runs"].pop()  # type: ignore[index,union-attr]
    with pytest.raises(ValueError, match="complete five-scene"):
        select_scene_runtime_rows(incomplete_scenes)


def test_primary_runtime_accounting_separates_runtime_and_strict_gates() -> None:
    """Do not turn zero strict credit into zero runtime neural acceptance."""

    accounting = build_primary_runtime_accounting(
        _scene_runtime_report(), _runtime_policy()
    )
    assert accounting["denominator_frame_records"] == 1500
    assert accounting["runtime_gate_ms"] == 100.0
    assert accounting["strict_gate_ms"] == pytest.approx(33.333333333333336)
    assert accounting["runtime_accepted_neural_count"] == 120
    assert accounting["late_discarded_neural_count"] == 30
    assert accounting["bypassed_count"] == 1350
    assert accounting["strict_same_frame_eligible_count"] == 0


def test_generated_tex_contains_all_publication_tables() -> None:
    """Keep manuscript table labels stable for the submission source."""

    report = {
        "runtime_rows": select_runtime_rows(_runtime_report()),
        "scene_runtime_rows": select_scene_runtime_rows(_scene_runtime_report()),
        "primary_runtime_accounting": build_primary_runtime_accounting(
            _scene_runtime_report(), _runtime_policy()
        ),
        "quality_rows": select_quality_rows(_quality_report()),
        "latency_breakdown_rows": [
            {
                "mode_id": "mode_180p_to_360p",
                "latency_components": {
                    name: {"mean_ms": 1.0}
                    for name in (
                        "render",
                        "input_transfer",
                        "npu",
                        "reconstruction",
                        "presentation",
                    )
                },
            }
        ],
    }
    rendered = render_generated_tex(report)
    assert "label{tab:runtime-accounting}" in rendered
    assert "label{tab:confirmatory-quality}" in rendered
    assert "label{tab:latency-breakdown}" in rendered
    assert "label{fig:displayed-provenance}" in rendered
    assert "all 1,500 records" in rendered
    assert "Runtime-accepted neural & 120 & 8.0\\%" in rendered
    assert "\\fontsize{10}{11}\\selectfont" in rendered
    assert "\\scriptsize" not in rendered
    # Keep numeric columns separated and prose cells free of stretched spaces.
    assert r"\setlength{\tabcolsep}{2.5pt}" in rendered
    assert r"\setlength{\tabcolsep}{3.0pt}" in rendered
    assert r">{\raggedright\arraybackslash}X" in rendered
    assert "accepted routing does not enumerate later composition or scanout" in rendered
    assert "runtime acceptance is recorded, later composition and scanout are not" in rendered
    assert "Lanczos req.*" not in rendered
    assert "unverified Lanczos-requested runtime configuration is omitted" in rendered
    assert " & Lanczos & " in rendered  # Verified offline quality stays.
    assert "0\\% strict; runtime route separate" in rendered
    assert "renderer\\_deadline" not in rendered
    assert "Deadline" in rendered
    assert "Fallback/s" in rendered
    assert "App step" in rendered
    assert "not panel scanout" in rendered
    assert "all values in ms" in rendered
    assert "zero for classical baselines does not mean invalid output" in rendered
