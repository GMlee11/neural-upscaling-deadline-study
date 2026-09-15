"""Summarize the physical RK3576 HotMobile confirmatory matrix."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from src.report.metadata_admission_phase12_report import read_jsonl, summarize
from src.runtime.telemetry import percentile
from src.utils.research_db import sha256_file


DEFAULT_CONFIG = Path("configs/paper1_hotmobile2027_confirmatory.yaml")


# Each timing category is derived directly from telemetry rather than inferred
# from aggregate service time. Reconstruction combines the measured RGA resize,
# residual packing, and GPU composition stages used by the direct-texture path.
def _component_values(
    rows: Sequence[Mapping[str, Any]],
    component: str,
) -> list[float]:
    """Return one per-frame latency component in milliseconds."""

    if component == "simulation":
        return [float(row.get("godot_simulation_ms", 0.0)) for row in rows]
    if component == "render":
        return [float(row.get("godot_gpu_render_wait_ms", 0.0)) for row in rows]
    if component == "input_transfer":
        return [
            float(row.get("backend_gpu_capture_ms", 0.0))
            + float(row.get("backend_rga_input_convert_ms", 0.0))
            for row in rows
        ]
    if component == "npu":
        return [float(row.get("backend_npu_inference_ms", 0.0)) for row in rows]
    if component == "reconstruction":
        return [
            float(row.get("backend_rga_resize_ms", 0.0))
            + float(row.get("backend_residual_pack_ms", 0.0))
            + float(row.get("backend_gpu_compose_ms", 0.0))
            for row in rows
        ]
    if component == "upload":
        return [float(row.get("godot_upload_ms", 0.0)) for row in rows]
    if component == "queue":
        return [float(row.get("npu_queue_wait_ms", 0.0)) for row in rows]
    if component == "presentation":
        return [float(row.get("godot_presentation_ms", 0.0)) for row in rows]
    raise ValueError(f"unknown latency component: {component}")


def summarize_hotmobile_trace(
    rows: Sequence[Mapping[str, Any]],
    *,
    profile_id: str,
    scene_variant: str,
    mode_id: str,
    target_fps: int,
) -> dict[str, Any]:
    """Add detailed latency, freshness, and drop metrics to common telemetry."""

    ordered = sorted(rows, key=lambda row: int(row["frame_id"]))
    result = summarize(
        ordered,
        variant=profile_id,
        mode_id=mode_id,
        target_fps=target_fps,
    )
    period_ms = 1000.0 / target_fps
    presentation = [float(row["fallback_presentation_elapsed_ms"]) for row in ordered]
    intervals = [later - earlier for earlier, later in zip(presentation, presentation[1:])]
    display_misses = sum(value > period_ms * 1.05 for value in intervals)
    service_had_neural = [
        bool(row.get("service_had_neural_image", False)) for row in ordered
    ]
    accepted = [bool(row.get("has_neural_image", False)) for row in ordered]
    components: dict[str, dict[str, float]] = {}
    for component in (
        "simulation",
        "render",
        "input_transfer",
        "npu",
        "reconstruction",
        "upload",
        "queue",
        "presentation",
    ):
        values = _component_values(ordered, component)
        components[component] = {
            "mean_ms": statistics.fmean(values),
            "p95_ms": percentile(values, 95.0),
            "p99_ms": percentile(values, 99.0),
        }
    duration_seconds = (
        presentation[-1] - presentation[0] + period_ms
    ) / 1000.0
    result.update(
        {
            "row_type": "paper1_hotmobile2027_physical_run",
            "profile_id": profile_id,
            "scene_variant": scene_variant,
            "neural_service_fps": sum(service_had_neural) / duration_seconds,
            "same_frame_neural_fraction": sum(
                bool(row.get("strict_same_frame_neural", False)) for row in ordered
            )
            / len(ordered),
            "fallback_rate": 1.0 - (sum(accepted) / len(accepted)),
            "npu_deadline_miss_rate": (
                (sum(service_had_neural) - sum(accepted)) / sum(service_had_neural)
                if any(service_had_neural)
                else 0.0
            ),
            "display_deadline_miss_rate": display_misses / max(1, len(intervals)),
            "dropped_frame_intervals": display_misses,
            "refresh_action_counts": dict(
                sorted(
                    Counter(
                        str(row.get("refresh_policy_action", "disabled"))
                        for row in ordered
                    ).items()
                )
            ),
            "latency_components": components,
        }
    )
    return result


def _scene_equal(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    """Average one scalar after each scene has already been reduced."""

    return statistics.fmean(float(row[field]) for row in rows)


def build_report(config: Mapping[str, Any]) -> dict[str, Any]:
    """Load the exact physical matrix and attach frozen offline V2 evidence."""

    physical = config["physical_rk3576"]
    trace = config["trace_contract"]
    root = Path(physical["result_root"])
    runs: list[dict[str, Any]] = []
    hashes: list[dict[str, str]] = []
    for profile in physical["profiles"]:
        for scene in trace["sequences"]:
            for mode in trace["modes"]:
                mode_id = str(mode["mode_id"])
                path = (
                    root
                    / str(profile)
                    / str(scene)
                    / mode_id
                    / "30fps"
                    / "buffers3"
                    / "godot_frames.jsonl"
                )
                rows = read_jsonl(path)
                if len(rows) != int(physical["frame_count"]):
                    raise ValueError(
                        f"{path} expected {physical['frame_count']} rows, found {len(rows)}"
                    )
                runs.append(
                    summarize_hotmobile_trace(
                        rows,
                        profile_id=str(profile),
                        scene_variant=str(scene),
                        mode_id=mode_id,
                        target_fps=int(physical["target_fps"]),
                    )
                )
                hashes.append({"path": path.as_posix(), "sha256": sha256_file(path)})

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in runs:
        grouped.setdefault((str(row["mode_id"]), str(row["profile_id"])), []).append(row)
    comparisons: list[dict[str, Any]] = []
    for (mode_id, profile), rows in sorted(grouped.items()):
        comparisons.append(
            {
                "mode_id": mode_id,
                "profile_id": profile,
                "display_fps": _scene_equal(rows, "display_fps"),
                "neural_service_fps": _scene_equal(rows, "neural_service_fps"),
                "npu_calls_per_frame": _scene_equal(rows, "npu_invocations_per_frame"),
                "same_frame_neural_fraction": _scene_equal(rows, "same_frame_neural_fraction"),
                "fallback_rate": _scene_equal(rows, "fallback_rate"),
                "p95_frame_age_ms": _scene_equal(rows, "p95_frame_age_ms"),
                "p99_frame_age_ms": _scene_equal(rows, "p99_frame_age_ms"),
                "display_deadline_miss_rate": _scene_equal(rows, "display_deadline_miss_rate"),
            }
        )
    reprojection_path = Path(config["late_reprojection"]["report_json"])
    reprojection = json.loads(reprojection_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "status": "physical_confirmatory_complete",
        "power_claim_supported": False,
        "runs": runs,
        "scene_equal_comparisons": comparisons,
        "late_reprojection_control": reprojection,
        "trace_hashes": hashes,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the compact table used directly by the workshop manuscript."""

    lines = [
        "# Paper 1 HotMobile 2027 Physical Confirmatory Results",
        "",
        "| Mode | Profile | Display FPS | Neural FPS | Calls/frame | Same-frame | Fallback | P95 age | P99 age | Display misses |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["scene_equal_comparisons"]:
        lines.append(
            f"| {row['mode_id']} | {row['profile_id']} | {row['display_fps']:.3f} | "
            f"{row['neural_service_fps']:.3f} | {row['npu_calls_per_frame']:.3f} | "
            f"{row['same_frame_neural_fraction']:.3f} | {row['fallback_rate']:.3f} | "
            f"{row['p95_frame_age_ms']:.2f} ms | {row['p99_frame_age_ms']:.2f} ms | "
            f"{100.0 * row['display_deadline_miss_rate']:.2f}% |"
        )
    lines.extend(
        [
            "",
            "Power and energy are intentionally not claimed because no calibrated external meter was available.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(config_path: Path, *, overwrite: bool) -> dict[str, Any]:
    """Build and write the physical confirmatory report."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    report = build_report(config)
    output = config["reporting"]
    json_path = Path(output["report_json"])
    markdown_path = Path(output["report_markdown"])
    if not overwrite and (json_path.exists() or markdown_path.exists()):
        raise FileExistsError("HotMobile report exists; pass --overwrite")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the frozen campaign configuration and overwrite guard."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the physical report and print its completion state."""

    args = parse_args(argv)
    try:
        report = run(args.config, overwrite=args.overwrite)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 1
    print(
        "PAPER1_HOTMOBILE_REPORT_COMPLETE "
        f"runs={len(report['runs'])} comparisons={len(report['scene_equal_comparisons'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
