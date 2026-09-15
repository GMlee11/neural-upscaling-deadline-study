"""Summarize physical direct-texture renderer-metadata admission runs."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.telemetry import percentile  # noqa: E402
from src.utils.research_db import publish_record_set  # noqa: E402


RUNS = (
    ("mode_180p_to_360p", 30),
    ("mode_180p_to_360p", 60),
    ("mode_360p_to_720p", 30),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one nonempty deterministic frame trace."""

    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"invalid or empty Phase-12 trace: {path}")
    return rows


def summarize(
    rows: Sequence[Mapping[str, Any]],
    *,
    variant: str,
    mode_id: str,
    target_fps: int,
) -> dict[str, object]:
    """Summarize display, admission, NPU, deadline, and selector behavior."""

    ordered = sorted(rows, key=lambda row: int(row["frame_id"]))
    if [int(row["frame_id"]) for row in ordered] != list(range(len(ordered))):
        raise ValueError("Phase-12 frame IDs are not contiguous")
    if len(ordered) < 2:
        raise ValueError("Phase-12 physical run requires multiple frames")
    period_ms = 1000.0 / target_fps
    presentation = [
        float(row["fallback_presentation_elapsed_ms"]) for row in ordered
    ]
    duration_ms = presentation[-1] - presentation[0] + period_ms
    display_fps = len(ordered) * 1000.0 / duration_ms
    methods = Counter(str(row["selected_method_id"]) for row in ordered)
    neural_completed = [
        row for row in ordered if bool(row["service_had_neural_image"])
    ]
    accepted = [row for row in ordered if bool(row["has_neural_image"])]
    selector = [float(row["selector_ms"]) for row in ordered]
    metadata_features = [
        float(row.get("metadata_features_ms", 0.0)) for row in ordered
    ]
    metadata_model = [
        float(row.get("metadata_model_ms", 0.0)) for row in ordered
    ]
    frame_age = [float(row["frame_age_ms"]) for row in ordered]
    deadline_ms = float(ordered[0]["client_deadline_ms"])
    route_status = Counter(str(row["route_status"]) for row in ordered)

    # Direct-texture traces expose device-stage timings only for completed NPU
    # frames. Older controls omit these fields, so absence remains explicit
    # rather than being converted into a misleading zero.
    def optional_timing(field: str) -> tuple[float | None, float | None]:
        """Return mean/P95 for a device timing when the trace provides it."""

        values = [
            float(row[field])
            for row in neural_completed
            if field in row and row[field] is not None
        ]
        if not values:
            return None, None
        return statistics.fmean(values), percentile(values, 95.0)

    npu_mean, npu_p95 = optional_timing("backend_npu_inference_ms")
    native_mean, native_p95 = optional_timing("backend_native_total_ms")
    compose_mean, compose_p95 = optional_timing("backend_gpu_compose_ms")
    return {
        "row_type": "phase12_physical_run",
        "variant": variant,
        "mode_id": mode_id,
        "target_fps": target_fps,
        "frame_count": len(ordered),
        "display_fps": display_fps,
        "display_target_met": display_fps >= target_fps * 0.95,
        "selected_method_counts": dict(sorted(methods.items())),
        "route_status_counts": dict(sorted(route_status.items())),
        "npu_completed_frames": len(neural_completed),
        "npu_invocations_per_frame": len(neural_completed) / len(ordered),
        "accepted_neural_fraction": len(accepted) / len(ordered),
        "deadline_miss_count": len(neural_completed) - len(accepted),
        "deadline_ms": deadline_ms,
        "mean_selector_ms": statistics.fmean(selector),
        "p95_selector_ms": percentile(selector, 95.0),
        "p99_selector_ms": percentile(selector, 99.0),
        "mean_metadata_features_ms": statistics.fmean(metadata_features),
        "mean_metadata_model_ms": statistics.fmean(metadata_model),
        "mean_frame_age_ms": statistics.fmean(frame_age),
        "p95_frame_age_ms": percentile(frame_age, 95.0),
        "p99_frame_age_ms": percentile(frame_age, 99.0),
        "mean_backend_npu_inference_ms": npu_mean,
        "p95_backend_npu_inference_ms": npu_p95,
        "mean_backend_native_total_ms": native_mean,
        "p95_backend_native_total_ms": native_p95,
        "mean_backend_gpu_compose_ms": compose_mean,
        "p95_backend_gpu_compose_ms": compose_p95,
    }


def build_report(result_root: Path) -> dict[str, object]:
    """Build paired always-full and metadata-policy physical comparisons."""

    runs: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    for mode_id, target_fps in RUNS:
        pair: dict[str, dict[str, object]] = {}
        for variant in ("always_full", "metadata_policy"):
            path = (
                result_root
                / variant
                / mode_id
                / f"{target_fps}fps"
                / "buffers3"
                / "godot_frames.jsonl"
            )
            row = summarize(
                read_jsonl(path),
                variant=variant,
                mode_id=mode_id,
                target_fps=target_fps,
            )
            runs.append(row)
            pair[variant] = row
        control = pair["always_full"]
        policy = pair["metadata_policy"]
        comparisons.append(
            {
                "row_type": "phase12_physical_comparison",
                "mode_id": mode_id,
                "target_fps": target_fps,
                "npu_invocation_reduction_percent": (
                    100.0
                    * (
                        float(control["npu_invocations_per_frame"])
                        - float(policy["npu_invocations_per_frame"])
                    )
                    / max(
                        float(control["npu_invocations_per_frame"]),
                        1e-12,
                    )
                ),
                "display_fps_change_percent": (
                    100.0
                    * (
                        float(policy["display_fps"])
                        - float(control["display_fps"])
                    )
                    / max(float(control["display_fps"]), 1e-12)
                ),
                "mean_frame_age_change_percent": (
                    100.0
                    * (
                        float(policy["mean_frame_age_ms"])
                        - float(control["mean_frame_age_ms"])
                    )
                    / max(float(control["mean_frame_age_ms"]), 1e-12)
                ),
                "selector_mean_ms": policy["mean_selector_ms"],
                "selector_p95_ms": policy["p95_selector_ms"],
                "policy_display_target_met": policy["display_target_met"],
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "renderer_metadata_admission_phase12_physical",
        "status": "measured_complete",
        "runs": runs,
        "comparisons": comparisons,
        "external_power_status": "pending_external_meter",
        "energy_claim_supported": False,
    }


def write_markdown(report: Mapping[str, object], path: Path) -> None:
    """Write a compact paired physical report."""

    lines = [
        "# Phase 12 Physical Renderer-Metadata Admission",
        "",
        "| Mode | Target | NPU reduction | Display change | Frame-age change | Selector mean/P95 | Target |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["comparisons"]:
        lines.append(
            f"| {row['mode_id']} | {row['target_fps']} FPS | "
            f"{float(row['npu_invocation_reduction_percent']):.1f}% | "
            f"{float(row['display_fps_change_percent']):+.1f}% | "
            f"{float(row['mean_frame_age_change_percent']):+.1f}% | "
            f"{float(row['selector_mean_ms']):.3f}/"
            f"{float(row['selector_p95_ms']):.3f} ms | "
            f"{'PASS' if row['policy_display_target_met'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "Power and joules/frame remain pending an external wall meter.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build the physical Phase-12 report command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-root",
        type=Path,
        default=Path("results/rk3576/phase12_metadata"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("results/tables/renderer_metadata_phase12_physical.json"),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path("results/tables/renderer_metadata_phase12_physical.md"),
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/research.sqlite3"),
    )
    parser.add_argument(
        "--record-set",
        default="hardware.rk3576.renderer_metadata_phase12",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate and publish the physical Phase-12 report."""

    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.result_root.resolve())
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_markdown(report, args.output_markdown)
        publish_record_set(
            args.database_path,
            args.record_set,
            [*report["runs"], *report["comparisons"]],
            overwrite=args.overwrite,
            source_path=args.output_json.as_posix(),
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Phase-12 physical report: {args.output_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
