"""Deterministic frame telemetry, aggregation, hashing, and SQLite publishing."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.utils.research_db import publish_record_set


STAGE_FIELDS = (
    "godot_simulation_ms",
    "godot_gpu_render_wait_ms",
    "godot_lr_readback_ms",
    "godot_reference_readback_ms",
    "godot_request_pack_ms",
    "godot_render_capture_ms",
    "request_transfer_ms",
    "scheduler_sequence_wait_ms",
    "backend_queue_wait_ms",
    "backend_queue_service_ms",
    "decode_ms",
    "backend_prepare_ms",
    "backend_inference_ms",
    "backend_reconstruction_ms",
    "backend_materialize_ms",
    "quality_ms",
    "encode_ms",
    "godot_upload_ms",
    "godot_composition_ms",
    "godot_presentation_ms",
    "frame_age_ms",
    "end_to_end_ms",
)


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile for nonempty finite samples."""

    if not values:
        raise ValueError("cannot calculate a percentile without samples")
    if not 0.0 <= percentile_value <= 100.0:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(float(value) for value in values)
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("percentile samples must be finite")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def append_jsonl(path: Path, record: Mapping[str, object]) -> None:
    """Append one sorted strict-JSON row, creating its parent when needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output_file:
        output_file.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read nonblank JSON-object rows while rejecting malformed telemetry."""

    if not path.is_file():
        raise FileNotFoundError(f"telemetry file does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"telemetry line {line_number} is not an object")
        rows.append(value)
    return rows


def sha256_bytes(payload: bytes) -> str:
    """Hash one exact transport payload for replay comparisons."""

    return hashlib.sha256(payload).hexdigest()


def output_hash_chain(rows: Sequence[Mapping[str, Any]]) -> str:
    """Hash ordered frame IDs and output hashes into one replay identity."""

    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda value: int(value["frame_id"])):
        digest.update(str(int(row["frame_id"])).encode("ascii"))
        digest.update(b":")
        digest.update(str(row["output_sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def merge_frame_telemetry(
    runtime_rows: Sequence[Mapping[str, Any]],
    godot_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join runtime and Godot rows one-to-one by deterministic frame ID."""

    runtime = {int(row["frame_id"]): dict(row) for row in runtime_rows}
    godot = {int(row["frame_id"]): dict(row) for row in godot_rows}
    if set(runtime) != set(godot):
        missing_runtime = sorted(set(godot) - set(runtime))
        missing_godot = sorted(set(runtime) - set(godot))
        raise ValueError(
            f"runtime/Godot frame IDs differ; runtime missing={missing_runtime}, "
            f"Godot missing={missing_godot}"
        )
    merged: list[dict[str, Any]] = []
    for frame_id in sorted(runtime):
        row = {**runtime[frame_id], **godot[frame_id]}
        # Schema V3 measures actual frame age from camera-state capture through
        # presentation. Preserve the historical sum for old evidence rows.
        if row.get("frame_age_ms") is not None:
            row["end_to_end_ms"] = float(row["frame_age_ms"])
        else:
            row["end_to_end_ms"] = float(row["request_transfer_ms"]) + float(
                row.get("godot_render_capture_ms", 0.0)
            ) + float(row.get("godot_composition_ms", 0.0)) + float(
                row.get("godot_presentation_ms", 0.0)
            )
        merged.append(row)
    return merged


def summarize_frames(
    rows: Sequence[Mapping[str, Any]],
    *,
    deadline_ms: float,
    target_fps: float,
) -> dict[str, Any]:
    """Aggregate stage latency, quality, drops, routing, and deterministic hashes."""

    if not rows:
        raise ValueError("at least one frame row is required")
    if deadline_ms <= 0.0 or target_fps <= 0.0:
        raise ValueError("deadline and target FPS must be positive")
    ordered = sorted(rows, key=lambda row: int(row["frame_id"]))
    if [int(row["frame_id"]) for row in ordered] != list(range(len(ordered))):
        raise ValueError("frame IDs must be contiguous and zero based")
    summary: dict[str, Any] = {
        "frame_count": len(ordered),
        "target_fps": target_fps,
        "target_duration_seconds": len(ordered) / target_fps,
        "deadline_ms": deadline_ms,
        "dropped_frame_count": sum(
            float(row["end_to_end_ms"]) > deadline_ms for row in ordered
        ),
        "deadline_miss_percent": 100.0
        * sum(float(row["end_to_end_ms"]) > deadline_ms for row in ordered)
        / len(ordered),
        "output_hash_chain": output_hash_chain(ordered),
        "first_output_sha256": str(ordered[0]["output_sha256"]),
        "last_output_sha256": str(ordered[-1]["output_sha256"]),
    }
    end_to_end = [float(row["end_to_end_ms"]) for row in ordered]
    summary["average_end_to_end_ms"] = math.fsum(end_to_end) / len(end_to_end)
    summary["median_end_to_end_ms"] = statistics.median(end_to_end)
    summary["p95_end_to_end_ms"] = percentile(end_to_end, 95.0)
    summary["p99_end_to_end_ms"] = percentile(end_to_end, 99.0)
    summary["observed_processing_fps"] = 1000.0 / summary["average_end_to_end_ms"]

    stage_summary: dict[str, dict[str, float]] = {}
    for field in STAGE_FIELDS:
        values = [float(row[field]) for row in ordered if row.get(field) is not None]
        if values:
            stage_summary[field] = {
                "average_ms": math.fsum(values) / len(values),
                "median_ms": statistics.median(values),
                "p95_ms": percentile(values, 95.0),
                "p99_ms": percentile(values, 99.0),
            }
    summary["stages"] = stage_summary

    psnr = [float(row["psnr_db"]) for row in ordered if row.get("psnr_db") is not None]
    ssim = [float(row["ssim"]) for row in ordered if row.get("ssim") is not None]
    summary["quality"] = {
        "psnr_frame_count": len(psnr),
        "average_psnr_db": math.fsum(psnr) / len(psnr) if psnr else None,
        "ssim_frame_count": len(ssim),
        "average_ssim": math.fsum(ssim) / len(ssim) if ssim else None,
    }
    temperatures = [
        float(row["host_temperature_peak_c"])
        for row in ordered
        if row.get("host_temperature_peak_c") is not None
    ]
    power_samples = [
        value
        for row in ordered
        for value in (
            row.get("external_power_start_w"),
            row.get("external_power_end_w"),
        )
        if value is not None
    ]
    power_sources = sorted(
        {
            str(value)
            for row in ordered
            for value in (
                row.get("external_power_start_source"),
                row.get("external_power_end_source"),
            )
            if value
        }
    )
    summary["physical_telemetry"] = {
        "temperature_sample_count": len(temperatures),
        "peak_temperature_c": max(temperatures) if temperatures else None,
        "external_power_sample_count": len(power_samples),
        "average_external_power_w": (
            math.fsum(float(value) for value in power_samples) / len(power_samples)
            if power_samples
            else None
        ),
        "external_power_sources": power_sources,
        "energy_joules_per_frame": None,
        "measurement_status": (
            "measured" if temperatures or power_samples else "unavailable"
        ),
    }
    backend_counts: Counter[str] = Counter()
    for row in ordered:
        counts = row.get("executed_method_counts")
        if isinstance(counts, Mapping):
            backend_counts.update({str(key): int(value) for key, value in counts.items()})
        else:
            backend_counts[str(row.get("backend_id", "unknown"))] += 1
    summary["executed_method_counts"] = dict(sorted(backend_counts.items()))
    summary["total_switch_count"] = sum(int(row.get("switch_count", 0)) for row in ordered)
    summary["total_forced_count"] = sum(int(row.get("forced_count", 0)) for row in ordered)
    summary["total_halo_input_pixels"] = sum(
        int(row.get("halo_input_pixels", 0)) for row in ordered
    )
    summary["average_actual_neural_gmac"] = math.fsum(
        float(row.get("actual_neural_gmac", 0.0)) for row in ordered
    ) / len(ordered)
    return summary


def _sqlite_safe(value: Any) -> Any:
    """Convert nested telemetry values to deterministic JSON strings."""

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def publish_runtime_results(
    database_path: Path,
    frame_rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    record_set_prefix: str,
    source_stem: str,
    overwrite: bool,
) -> None:
    """Publish one runtime experiment without replacing a different backend run."""

    if not record_set_prefix.strip():
        raise ValueError("record_set_prefix must not be empty")
    if not source_stem.strip():
        raise ValueError("source_stem must not be empty")

    publish_record_set(
        database_path,
        f"{record_set_prefix}.frames",
        ({key: _sqlite_safe(value) for key, value in row.items()} for row in frame_rows),
        overwrite=overwrite,
        source_path=f"results/runtime/{source_stem}/combined_frames.jsonl",
    )
    summary_row = {
        key: _sqlite_safe(value)
        for key, value in summary.items()
        if key not in {"stages", "quality", "physical_telemetry"}
    }
    for stage, values in summary.get("stages", {}).items():
        for metric, value in values.items():
            summary_row[f"{stage}_{metric}"] = value
    for metric, value in summary.get("quality", {}).items():
        summary_row[f"quality_{metric}"] = value
    for metric, value in summary.get("physical_telemetry", {}).items():
        summary_row[f"physical_{metric}"] = _sqlite_safe(value)
    publish_record_set(
        database_path,
        f"{record_set_prefix}.summary",
        [summary_row],
        overwrite=overwrite,
        source_path=f"results/tables/{source_stem}.json",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Replace one JSONL artifact atomically enough for local experiment use."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)
