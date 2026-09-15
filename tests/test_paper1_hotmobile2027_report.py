"""Tests for the physical HotMobile telemetry reducer."""

from __future__ import annotations

import pytest

from src.report.paper1_hotmobile2027_report import summarize_hotmobile_trace


def _physical_row(frame_id: int) -> dict[str, object]:
    """Build one valid compact direct-texture telemetry row."""

    return {
        "frame_id": frame_id,
        "fallback_presentation_elapsed_ms": frame_id * 33.333,
        "selected_method_id": "stage_abc",
        "service_had_neural_image": True,
        "has_neural_image": frame_id == 0,
        "strict_same_frame_neural": frame_id == 0,
        "selector_ms": 0.1,
        "metadata_features_ms": 0.0,
        "metadata_model_ms": 0.0,
        "frame_age_ms": 20.0 + frame_id,
        "client_deadline_ms": 33.333,
        "route_status": "complete",
        "refresh_policy_action": "submit",
        "godot_simulation_ms": 0.2,
        "godot_gpu_render_wait_ms": 2.0,
        "backend_gpu_capture_ms": 0.5,
        "backend_rga_input_convert_ms": 0.3,
        "backend_npu_inference_ms": 10.0,
        "backend_rga_resize_ms": 1.0,
        "backend_residual_pack_ms": 0.4,
        "backend_gpu_compose_ms": 0.6,
        "godot_upload_ms": 0.0,
        "npu_queue_wait_ms": 0.7,
        "godot_presentation_ms": 0.1,
    }


def test_hotmobile_trace_exposes_complete_latency_and_freshness() -> None:
    """Reduce all required components without mistaking completion for display."""

    result = summarize_hotmobile_trace(
        [_physical_row(index) for index in range(3)],
        profile_id="always_neural",
        scene_variant="p1c_market_pan",
        mode_id="mode_180p_to_360p",
        target_fps=30,
    )
    assert result["same_frame_neural_fraction"] == pytest.approx(1.0 / 3.0)
    assert result["fallback_rate"] == pytest.approx(2.0 / 3.0)
    assert result["npu_deadline_miss_rate"] == pytest.approx(2.0 / 3.0)
    assert result["latency_components"]["reconstruction"]["mean_ms"] == pytest.approx(2.0)
    assert result["latency_components"]["input_transfer"]["mean_ms"] == pytest.approx(0.8)
