"""Deadline- and age-bounded neural refresh admission for RK3576.

The policy in this module does not predict image quality and does not replace
the frozen renderer selectors.  It answers a narrower systems question: given
an immediately available GPU classical frame, is there enough measured service
capacity to launch a neural refresh without building a stale queue?
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ARTIFACT_ID = "rk3576_neural_refresh_policy_paper1_v1"
POLICY_ID = "renderer_deadline_refresh_v1"


@dataclass(frozen=True)
class RefreshObservation:
    """Causal runtime state available immediately before NPU submission."""

    frame_id: int
    mode_id: str
    target_fps: int
    gpu_frame_ms: float
    pending_frames: int
    last_committed_neural_frame: int | None
    last_submitted_neural_frame: int | None
    measured_service_ewma_ms: float | None = None
    temperature_c: float | None = None
    renderer_metadata: Mapping[str, float] | None = None


def renderer_priority_score(
    policy: Mapping[str, Any],
    metadata: Mapping[str, float] | None,
) -> float:
    """Calculate a bounded priority from renderer-owned scene information.

    The score deliberately uses draw-list metadata rather than reading image
    pixels on the CPU. Missing metadata is treated as zero so an unavailable
    signal cannot accidentally force more NPU work.
    """

    if metadata is None:
        return 0.0
    weights = policy["renderer_priority_weights"]
    weighted_sum = 0.0
    weight_total = 0.0
    for field, weight_value in weights.items():
        weight = _finite_nonnegative(weight_value, f"weight[{field}]")
        value = min(1.0, _finite_nonnegative(metadata.get(field, 0.0), field))
        weighted_sum += weight * value
        weight_total += weight
    return weighted_sum / max(weight_total, 1e-12)


def _finite_nonnegative(value: object, name: str) -> float:
    """Return one finite nonnegative float with a precise artifact error."""

    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return converted


def load_refresh_policy(path: Path) -> dict[str, object]:
    """Load and fully validate the portable Godot/Python policy artifact."""

    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("refresh policy root must be a mapping")
    if policy.get("artifact") != ARTIFACT_ID:
        raise ValueError("refresh policy artifact is incompatible")
    if policy.get("policy_id") != POLICY_ID:
        raise ValueError("refresh policy identifier is unsupported")

    alpha = float(policy.get("service_ewma_alpha", 0.0))
    if not math.isfinite(alpha) or not 0.0 < alpha <= 1.0:
        raise ValueError("service_ewma_alpha must be in (0, 1]")
    _finite_nonnegative(
        policy.get("fixed_completion_overhead_ms", -1.0),
        "fixed_completion_overhead_ms",
    )
    _finite_nonnegative(policy.get("safety_margin_ms", -1.0), "safety_margin_ms")
    if int(policy.get("maximum_pending_frames", -1)) < 0:
        raise ValueError("maximum_pending_frames must be nonnegative")
    threshold = float(policy.get("renderer_priority_threshold", -1.0))
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("renderer_priority_threshold must be in [0, 1]")
    if int(policy.get("priority_refresh_period_frames", 0)) < 1:
        raise ValueError("priority_refresh_period_frames must be positive")
    weights = policy.get("renderer_priority_weights")
    if not isinstance(weights, Mapping) or not weights:
        raise ValueError("renderer_priority_weights must be a nonempty mapping")
    if sum(
        _finite_nonnegative(value, str(key)) for key, value in weights.items()
    ) <= 0.0:
        raise ValueError("renderer priority weights must contain a positive value")

    workloads = policy.get("supported_workloads")
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("refresh policy requires supported workloads")
    identities: set[tuple[str, int]] = set()
    for index, workload_value in enumerate(workloads):
        if not isinstance(workload_value, Mapping):
            raise ValueError(f"supported_workloads[{index}] must be a mapping")
        mode_id = str(workload_value.get("mode_id", ""))
        target_fps = int(workload_value.get("target_fps", 0))
        identity = (mode_id, target_fps)
        if not mode_id or target_fps <= 0 or identity in identities:
            raise ValueError("refresh workload identities must be unique and valid")
        identities.add(identity)
        for field in (
            "target_refresh_period_frames",
            "maximum_refresh_age_frames",
        ):
            if int(workload_value.get(field, 0)) < 1:
                raise ValueError(f"{field} must be positive")
        if int(workload_value["target_refresh_period_frames"]) > int(
            workload_value["maximum_refresh_age_frames"]
        ):
            raise ValueError("refresh period cannot exceed maximum refresh age")
        _finite_nonnegative(
            workload_value.get("initial_service_ms", -1.0),
            "initial_service_ms",
        )
    return policy


def update_service_ewma(
    previous_ms: float | None,
    observed_ms: float,
    *,
    alpha: float,
) -> float:
    """Update the causal service-time estimate after one completed request."""

    observed = _finite_nonnegative(observed_ms, "observed_ms")
    if not math.isfinite(alpha) or not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    if previous_ms is None:
        return observed
    previous = _finite_nonnegative(previous_ms, "previous_ms")
    return alpha * observed + (1.0 - alpha) * previous


def choose_refresh_action(
    policy: Mapping[str, Any],
    observation: RefreshObservation,
) -> dict[str, object]:
    """Choose neural submission or immediate classical presentation.

    The action is deliberately conservative.  It never queues behind an
    occupied NPU context, and it rejects work predicted to finish after the
    configured maximum refresh age.  Same-frame success remains a separately
    reported measurement; a larger refresh-age allowance must never be called
    same-frame real time.
    """

    if observation.frame_id < 0 or observation.target_fps <= 0:
        raise ValueError("frame_id must be nonnegative and target_fps positive")
    gpu_frame_ms = _finite_nonnegative(observation.gpu_frame_ms, "gpu_frame_ms")
    if observation.pending_frames < 0:
        raise ValueError("pending_frames must be nonnegative")
    if observation.temperature_c is not None:
        _finite_nonnegative(observation.temperature_c, "temperature_c")

    workload = next(
        (
            row
            for row in policy["supported_workloads"]
            if str(row["mode_id"]) == observation.mode_id
            and int(row["target_fps"]) == observation.target_fps
        ),
        None,
    )
    frame_deadline_ms = 1000.0 / observation.target_fps
    if workload is None:
        return {
            "action": "bypass",
            "reason": "unsupported_workload",
            "frame_deadline_ms": frame_deadline_ms,
            "predicted_completion_age_ms": None,
            "frames_since_neural_commit": None,
        }

    maximum_age_frames = int(workload["maximum_refresh_age_frames"])
    refresh_deadline_ms = maximum_age_frames * frame_deadline_ms
    last_commit = observation.last_committed_neural_frame
    frames_since_commit = (
        maximum_age_frames
        if last_commit is None
        else max(0, observation.frame_id - last_commit)
    )
    last_submit = observation.last_submitted_neural_frame
    frames_since_submit = (
        int(workload["target_refresh_period_frames"])
        if last_submit is None
        else max(0, observation.frame_id - last_submit)
    )
    service_ms = (
        _finite_nonnegative(
            observation.measured_service_ewma_ms,
            "measured_service_ewma_ms",
        )
        if observation.measured_service_ewma_ms is not None
        else float(workload["initial_service_ms"])
    )
    predicted_age_ms = (
        gpu_frame_ms
        + service_ms
        + float(policy["fixed_completion_overhead_ms"])
        + float(policy["safety_margin_ms"])
    )
    priority_score = renderer_priority_score(
        policy,
        observation.renderer_metadata,
    )
    renderer_priority = priority_score >= float(
        policy["renderer_priority_threshold"]
    )
    effective_refresh_period = (
        int(policy["priority_refresh_period_frames"])
        if renderer_priority
        else int(workload["target_refresh_period_frames"])
    )

    action = "submit"
    reason = "refresh_due_capacity_available"
    temperature_limit = policy.get("temperature_limit_c")
    if (
        temperature_limit is not None
        and observation.temperature_c is not None
        and observation.temperature_c >= float(temperature_limit)
    ):
        action = "bypass"
        reason = "temperature_limit"
    elif observation.pending_frames > int(policy["maximum_pending_frames"]):
        action = "bypass"
        reason = "latest_frame_only_context_busy"
    elif frames_since_submit < effective_refresh_period:
        action = "bypass"
        reason = "refresh_period_not_due"
    elif predicted_age_ms > refresh_deadline_ms:
        action = "bypass"
        reason = "predicted_refresh_would_be_stale"

    return {
        "action": action,
        "reason": reason,
        "frame_deadline_ms": frame_deadline_ms,
        "refresh_deadline_ms": refresh_deadline_ms,
        "maximum_refresh_age_frames": maximum_age_frames,
        "target_refresh_period_frames": int(
            workload["target_refresh_period_frames"]
        ),
        "effective_refresh_period_frames": effective_refresh_period,
        "renderer_priority_score": priority_score,
        "renderer_priority": renderer_priority,
        "frames_since_neural_commit": frames_since_commit,
        "frames_since_neural_submit": frames_since_submit,
        "predicted_service_ms": service_ms,
        "predicted_completion_age_ms": predicted_age_ms,
        "predicted_same_frame": predicted_age_ms <= frame_deadline_ms,
        "pending_frames": observation.pending_frames,
    }
