"""Assemble the frozen physical and confirmatory evidence for Paper 1."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from src.report.metadata_admission_phase12_report import read_jsonl
from src.report.paper1_hotmobile2027_report import summarize_hotmobile_trace
from src.utils.research_db import sha256_file


DEFAULT_CONFIG = Path("configs/paper1_hotmobile2027_confirmatory.yaml")
PAPER_PROFILES = (
    "gpu_bicubic",
    "gpu_lanczos",
    "always_neural",
    "fixed_period_2",
    "renderer_deadline_refresh_v1",
)
PRIMARY_SCENES = (
    "barrier_yard",
    "corridor_neon",
    "forest_outpost",
    "hud_particles",
    "reflective_plaza",
)
PROFILE_LABELS = {
    "gpu_bicubic": "Bicubic",
    "gpu_lanczos": "Lanczos req.*",
    "always_neural": "Always neural",
    "fixed_period_2": "Fixed/2",
    "renderer_deadline_refresh_v1": "Deadline",
}
SCENE_LABELS = {
    "barrier_yard": "Barrier",
    "corridor_neon": "Corridor",
    "forest_outpost": "Forest",
    "hud_particles": "HUD",
    "reflective_plaza": "Plaza",
}


# Pull one representative row for each classical/fresh/late method at the
# shortest simulated delay. The paper reports scene-equal statistics and keeps
# the full delay sweep in the artifact rather than crowding the six-page text.
def select_quality_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select the age-two quality rows used in the compact paper table."""

    methods = {
        "bicubic",
        "lanczos",
        "fresh_neural",
        "stale_unwarped",
        "motion_depth_disocclusion",
    }
    rows = [
        dict(row)
        for row in report["summary"]
        if int(row["age_frames"]) == 2 and str(row["method"]) in methods
    ]
    expected = 2 * len(methods)
    if len(rows) != expected:
        raise ValueError(f"expected {expected} age-two quality rows, found {len(rows)}")
    return sorted(rows, key=lambda row: (str(row["mode_id"]), str(row["method"])))


# The V1 decision contains many diagnostic controls. The workshop comparison
# is deliberately restricted to the five preregistered controls at 30 FPS and
# the two requested resolution modes.
def select_runtime_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select the matched 30-FPS runtime controls from the frozen decision."""

    rows = [
        dict(row)
        for row in report["runtime_summary"]
        if int(row["target_fps"]) == 30
        and str(row["profile_id"]) in PAPER_PROFILES
        and str(row["mode_id"])
        in {"mode_180p_to_360p", "mode_360p_to_720p"}
    ]
    expected = 2 * len(PAPER_PROFILES)
    if len(rows) != expected:
        raise ValueError(f"expected {expected} physical runtime rows, found {len(rows)}")
    return sorted(rows, key=lambda row: (str(row["mode_id"]), str(row["profile_id"])))


def select_scene_runtime_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return all five frozen scene rows for the primary 720p deadline policy."""

    rows = [
        dict(row)
        for row in report["runs"]
        if str(row["mode_id"]) == "mode_360p_to_720p"
        and int(row["target_fps"]) == 30
        and str(row["profile_id"]) == "renderer_deadline_refresh_v1"
    ]
    scene_ids = tuple(sorted(str(row["scene_variant"]) for row in rows))
    if scene_ids != PRIMARY_SCENES:
        raise ValueError(
            "expected the complete five-scene primary scheduler set; "
            f"found {scene_ids}"
        )
    if any(float(row["strict_same_frame_neural_fraction"]) != 0.0 for row in rows):
        raise ValueError("expected zero same-frame 720p neural acceptance in every scene")
    return sorted(rows, key=lambda row: str(row["scene_variant"]))


def build_primary_runtime_accounting(
    report: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Reduce the frozen primary run into explicit runtime and strict outcomes."""

    rows = select_scene_runtime_rows(report)
    workload = next(
        (
            row
            for row in policy["supported_workloads"]
            if str(row["mode_id"]) == "mode_360p_to_720p"
            and int(row["target_fps"]) == 30
        ),
        None,
    )
    if workload is None or int(workload["maximum_refresh_age_frames"]) != 3:
        raise ValueError("expected the frozen three-frame 720p runtime gate")

    frame_count = sum(int(row["frame_count"]) for row in rows)
    action_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    for row in rows:
        row_actions = {
            str(key): int(value) for key, value in row["refresh_action_counts"].items()
        }
        row_routes = {
            str(key): int(value) for key, value in row["route_status_counts"].items()
        }
        if set(row_actions) != {"bypass", "submit"}:
            raise ValueError("unexpected primary scheduler action category")
        if set(row_routes) != {
            "accepted_neural",
            "client_late_neural_discarded",
            "refresh_policy_bypass",
        }:
            raise ValueError("unexpected primary scheduler route category")
        if int(row["frame_count"]) != sum(row_routes.values()):
            raise ValueError("primary scheduler scene routes do not close")
        if int(row["npu_completed_frames"]) != int(row_actions["submit"]):
            raise ValueError("primary scheduler scene submissions do not close")
        if int(row["deadline_miss_count"]) != int(
            row_routes["client_late_neural_discarded"]
        ):
            raise ValueError("primary scheduler scene deadline misses do not close")
        accepted_count = (
            float(row["accepted_neural_fraction"]) * int(row["frame_count"])
        )
        if abs(accepted_count - int(row_routes["accepted_neural"])) > 1e-9:
            raise ValueError("primary scheduler accepted fraction does not close")
        action_counts.update(row_actions)
        route_counts.update(row_routes)
        if float(row["deadline_ms"]) != 100.0:
            raise ValueError("expected the frozen 100-ms runtime acceptance gate")

    submitted = int(action_counts["submit"])
    completed = sum(int(row["npu_completed_frames"]) for row in rows)
    runtime_accepted = int(route_counts["accepted_neural"])
    late_discarded = int(route_counts["client_late_neural_discarded"])
    bypassed = int(route_counts["refresh_policy_bypass"])
    strict_eligible = sum(
        round(float(row["strict_same_frame_neural_fraction"]) * int(row["frame_count"]))
        for row in rows
    )
    if submitted != completed or submitted != runtime_accepted + late_discarded:
        raise ValueError("primary scheduler completion accounting does not close")
    if frame_count != runtime_accepted + late_discarded + bypassed:
        raise ValueError("primary scheduler route accounting does not close")
    if frame_count != 1_500 or strict_eligible != 0:
        raise ValueError("unexpected primary scheduler denominator or strict count")

    terminal_classical = late_discarded + bypassed
    return {
        "denominator_frame_records": frame_count,
        "runtime_gate_frames": 3,
        "runtime_gate_ms": 100.0,
        "strict_gate_frames": 1,
        "strict_gate_ms": 1000.0 / 30.0,
        "submitted_count": submitted,
        "completed_count": completed,
        "runtime_accepted_neural_count": runtime_accepted,
        "late_discarded_neural_count": late_discarded,
        "bypassed_count": bypassed,
        "terminal_classical_route_count": terminal_classical,
        "strict_same_frame_eligible_count": strict_eligible,
        "initial_fallback_count": frame_count,
        "categories_are_not_all_mutually_exclusive": True,
        "distinct_renderer_commit_count_available": False,
        "panel_scanout_observed": False,
    }


def collect_v1_provenance(
    paper: Mapping[str, Any], physical: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Hash compact V1 sources and verify the frozen decision's source chain."""

    sources = paper["canonical_v1_sources"]
    manifest_path = Path(sources["evidence_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    support = {str(row["path"]): row for row in manifest["support_files"]}
    roles = (
        "scheduler_config",
        "quality_config",
        "policy",
        "evidence_manifest",
        "scheduler_report",
        "quality_report",
        "result_note",
    )
    rows: list[dict[str, Any]] = []
    for role in roles:
        path = Path(sources[role])
        digest = sha256_file(path)
        relative = path.as_posix()
        if relative in support and digest != str(support[relative]["sha256"]):
            raise ValueError(f"V1 evidence-manifest hash mismatch: {relative}")
        rows.append(
            {
                "role": role,
                "path": relative,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
            }
        )

    scheduler_digest = sha256_file(Path(sources["scheduler_report"]))
    quality_digest = sha256_file(Path(sources["quality_report"]))
    if scheduler_digest != str(physical["source_reports"]["runtime_sha256"]):
        raise ValueError("final decision does not match packaged V1 scheduler report")
    if quality_digest != str(physical["source_reports"]["quality_sha256"]):
        raise ValueError("final decision does not match packaged V1 quality report")
    return rows


def displayed_result_gate(
    physical: Mapping[str, Any], accounting: Mapping[str, Any]
) -> dict[str, Any]:
    """Expose the authoritative final gate without rewriting frozen evidence."""

    scope = physical["physical_scope"]
    primary = physical["primary_720p_gate"]
    strict_quality = physical["strict_quality_gate"]
    if int(scope["runtime_frames"]) != 31_500:
        raise ValueError("expected the frozen 31,500-frame physical scope")
    if float(primary["strict_same_frame_neural_fraction"]) != 0.0:
        raise ValueError("expected zero same-frame 720p neural acceptance")
    return {
        "authoritative_quality_path": "strict_quality_gate",
        "runtime_decision": primary["decision"],
        "runtime_gate_pass": bool(primary["runtime_gate_pass"]),
        "strict_quality_decision": strict_quality["decision"],
        "strict_quality_gate_pass": bool(strict_quality["overall_passed"]),
        "strict_720p_same_frame_neural_fraction": float(
            primary["strict_same_frame_neural_fraction"]
        ),
        "runtime_accepted_neural_count": int(
            accounting["runtime_accepted_neural_count"]
        ),
        "strict_same_frame_eligible_count": int(
            accounting["strict_same_frame_eligible_count"]
        ),
        "provenance_interpretation": (
            "runtime_acceptance_and_strict_eligibility_do_not_establish_"
            "complete_composition_history"
        ),
        "legacy_nested_quality_gate_status": primary["quality_gate_status"],
        "legacy_nested_status_is_stale": True,
    }


def build_report(config: Mapping[str, Any]) -> dict[str, Any]:
    """Join frozen physical timing with independent confirmatory quality."""

    paper = config["workshop_paper"]
    physical_path = Path(paper["physical_decision_json"])
    reprojection_path = Path(paper["reprojection_json"])
    physical = json.loads(physical_path.read_text(encoding="utf-8"))
    reprojection = json.loads(reprojection_path.read_text(encoding="utf-8"))
    scheduler_path = Path(paper["canonical_v1_sources"]["scheduler_report"])
    scheduler = json.loads(scheduler_path.read_text(encoding="utf-8"))
    policy_path = Path(paper["canonical_v1_sources"]["policy"])
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    provenance_rows = collect_v1_provenance(paper, physical)
    accounting = build_primary_runtime_accounting(scheduler, policy)
    gate = displayed_result_gate(physical, accounting)

    latency_rows: list[dict[str, Any]] = []
    evidence_hashes = [
        {"path": physical_path.as_posix(), "sha256": sha256_file(physical_path)},
        {"path": reprojection_path.as_posix(), "sha256": sha256_file(reprojection_path)},
    ]
    evidence_hashes.extend(provenance_rows)
    for trace in paper["representative_latency_traces"]:
        trace_path = Path(trace["path"])
        rows = read_jsonl(trace_path)
        latency_rows.append(
            summarize_hotmobile_trace(
                rows,
                profile_id=str(trace["profile_id"]),
                scene_variant="representative_physical_trace",
                mode_id=str(trace["mode_id"]),
                target_fps=30,
            )
        )
        evidence_hashes.append(
            {"path": trace_path.as_posix(), "sha256": sha256_file(trace_path)}
        )

    return {
        "schema_version": 2,
        "experiment_id": "paper1_hotmobile2027_workshop_v1",
        "classification": "mobile_systems_boundary_and_evaluation_paper",
        "physical_runtime_scope": "five scenes, 31,500 frames, RK3576",
        "physical_scope": physical["physical_scope"],
        "confirmatory_quality_scope": "three unseen scenes, two modes, 1,800 captured frames",
        "runtime_rows": select_runtime_rows(physical),
        "scene_runtime_rows": select_scene_runtime_rows(scheduler),
        "primary_runtime_accounting": accounting,
        "latency_breakdown_rows": latency_rows,
        "quality_rows": select_quality_rows(reprojection),
        "physical_decision": physical["decision"],
        "late_reprojection_decision": "reject_as_positive_mechanism",
        "power_claim_supported": False,
        "displayed_result_gate": gate,
        "historical_instrumentation": {
            "contract_instantiation": "partial",
            "observed_events": [
                "immediate_fallback_presentation",
                "terminal_runtime_route",
                "runtime_acceptance_or_discard",
                "frame_age_and_deadline_fields",
            ],
            "unobserved_events": [
                "complete_later_renderer_composition_log",
                "physical_panel_scanout",
            ],
        },
        "provenance_records": provenance_rows,
        "reporting_warnings": [
            {
                "field": "primary_720p_gate.quality_gate_status",
                "frozen_value": gate["legacy_nested_quality_gate_status"],
                "authoritative_path": "strict_quality_gate.decision",
                "authoritative_value": gate["strict_quality_decision"],
                "action": "preserve frozen source; report through authoritative final gate",
            }
        ],
        "evidence_hashes": evidence_hashes,
    }


def _short_mode(mode_id: str) -> str:
    """Return a compact human-readable resolution label."""

    return "180p--360p" if mode_id == "mode_180p_to_360p" else "360p--720p"


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a reviewer-readable evidence summary."""

    lines = [
        "# Paper 1 HotMobile 2027 Evidence",
        "",
        "## Physical RK3576 Runtime",
        "",
        "| Mode | Control | Fallback/s | Calls/frame | Same-frame neural | P95 age | Policy ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["runtime_rows"]:
        lines.append(
            f"| {_short_mode(str(row['mode_id']))} | {row['profile_id']} | "
            f"{float(row['display_fps']):.3f} | {float(row['npu_invocations_per_frame']):.3f} | "
            f"{float(row['strict_same_frame_neural_fraction']):.3f} | "
            f"{float(row['p95_frame_age_ms']):.2f} ms | "
            f"{float(row['mean_refresh_selector_ms']):.3f} ms |"
        )
    lines.extend(
        [
            "",
            "## Complete Primary-Workload Scene Rows",
            "",
            "| Scene | Fallback/s | Calls/frame | Same-frame neural | P95 age | Policy ms |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["scene_runtime_rows"]:
        lines.append(
            f"| {row['scene_variant']} | {float(row['display_fps']):.3f} | "
            f"{float(row['npu_invocations_per_frame']):.3f} | "
            f"{float(row['strict_same_frame_neural_fraction']):.3f} | "
            f"{float(row['p95_frame_age_ms']):.2f} ms | "
            f"{float(row['mean_refresh_selector_ms']):.3f} ms |"
        )
    lines.extend(
        [
            "",
            "These are all five frozen 360p-to-720p/30-FPS scheduler rows; no scene or threshold was selected after inspection.",
            "",
            "## Primary 720p Runtime and Strict Accounting",
            "",
            f"- Authoritative runtime decision: `{report['displayed_result_gate']['runtime_decision']}`.",
            f"- Authoritative quality decision: `{report['displayed_result_gate']['strict_quality_decision']}`.",
            "- Historical `display_fps` is computed from immediate fallback-presentation timestamps; it is not a count of every renderer commit.",
            "- The trace partially instantiates the proposed full event contract: it records immediate fallback, terminal routing, acceptance/discard, and age/deadline fields, but not every later composition or physical panel scanout.",
            "- The runtime accepts a source-matched neural result within three frames (100 ms), whereas the strict paper rule credits only results eligible within one frame (33.33 ms).",
            "",
            "| Outcome or event | Count | Percent of 1,500 frame records |",
            "|---|---:|---:|",
            f"| Submitted and completed | {report['primary_runtime_accounting']['submitted_count']} | {100.0 * report['primary_runtime_accounting']['submitted_count'] / 1500.0:.1f}% |",
            f"| Runtime-accepted neural (within 100 ms) | {report['primary_runtime_accounting']['runtime_accepted_neural_count']} | {100.0 * report['primary_runtime_accounting']['runtime_accepted_neural_count'] / 1500.0:.1f}% |",
            f"| Completed but discarded late | {report['primary_runtime_accounting']['late_discarded_neural_count']} | {100.0 * report['primary_runtime_accounting']['late_discarded_neural_count'] / 1500.0:.1f}% |",
            f"| Refresh bypass, no submission | {report['primary_runtime_accounting']['bypassed_count']} | {100.0 * report['primary_runtime_accounting']['bypassed_count'] / 1500.0:.1f}% |",
            f"| Terminal classical route | {report['primary_runtime_accounting']['terminal_classical_route_count']} | {100.0 * report['primary_runtime_accounting']['terminal_classical_route_count'] / 1500.0:.1f}% |",
            f"| Strict one-frame neural eligible | {report['primary_runtime_accounting']['strict_same_frame_eligible_count']} | 0.0% |",
            "",
            "Runtime-accepted, late-discarded, and bypassed are mutually exclusive terminal route outcomes. Submission/completion, terminal-classical, and strict-eligibility rows are derived views and must not be summed. The runtime first issues classical fallback for every source record. Runtime acceptance is not a complete later-composition event, so the aggregate supports neither a neural-composition count nor an all-classical composition history.",
            "- The frozen nested `primary_720p_gate.quality_gate_status` value is stale; this reducer reports `strict_quality_gate.decision` and does not rewrite the source result.",
            "",
            "## Fresh Confirmatory Quality (Two-Frame Delay)",
            "",
            "| Mode | Method | PSNR | SSIM | LPIPS | Valid history |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in report["quality_rows"]:
        lines.append(
            f"| {_short_mode(str(row['mode_id']))} | {row['method']} | "
            f"{float(row['scene_equal_psnr']):.3f} | {float(row['scene_equal_ssim']):.5f} | "
            f"{float(row['scene_equal_lpips']):.5f} | "
            f"{float(row['mean_valid_history_fraction']):.3f} |"
        )
    lines.extend(
        [
            "",
            "The physical scheduler restores the immediate-fallback cadence by declining most NPU work. It accepts 172 neural outcomes under the looser three-frame runtime gate, but none qualifies for strict one-frame 720p credit. Late residual reprojection is preserved as a negative result because its small apparent gains mostly converge back to the classical fallback.",
            "",
            "No physical power or energy claim is made.",
        ]
    )
    return "\n".join(lines) + "\n"


def _tex_escape(value: str) -> str:
    """Escape the small identifier vocabulary inserted into LaTeX tables."""

    return value.replace("_", r"\_").replace("%", r"\%")


def _deadline_provenance(row: Mapping[str, Any]) -> str:
    """Describe strict eligibility without inferring unencoded route outcomes."""

    profile = str(row["profile_id"])
    strict = float(row["strict_same_frame_neural_fraction"])
    if profile in {"gpu_bicubic", "gpu_lanczos"}:
        return "Classical control"
    if strict == 0.0:
        return "0\\% strict; runtime route separate"
    return f"{100.0 * strict:.1f}\\% strict one-frame eligible"


def render_displayed_provenance_figure(report: Mapping[str, Any]) -> list[str]:
    """Render an honest provenance figure from the frozen aggregate fields."""

    profile_order = {profile: index for index, profile in enumerate(PAPER_PROFILES)}
    runtime_rows = sorted(
        [row for row in report["runtime_rows"] if row["profile_id"] != "gpu_lanczos"],
        key=lambda row: (
            str(row["mode_id"]),
            profile_order[str(row["profile_id"])],
        ),
    )
    lines = [
        r"\begin{figure*}[t]",
        r"\centering",
        r"\fontsize{10}{11}\selectfont",
        r"\setlength{\tabcolsep}{2.5pt}",
        r"\begin{tabularx}{\textwidth}{@{}llrrr>{\raggedright\arraybackslash}p{0.22\textwidth}>{\raggedright\arraybackslash}X@{}}",
        r"\toprule",
        r"Mode & Control & Fallback/s & Calls/f & P95 age & Strict same-frame neural & Interpretation \\",
        r"\midrule",
    ]
    previous_mode = ""
    for row in runtime_rows:
        mode = str(row["mode_id"])
        if previous_mode and mode != previous_mode:
            lines.append(r"\addlinespace[2pt]")
        strict = float(row["strict_same_frame_neural_fraction"])
        bar_mm = 70.0 * strict
        if strict > 0.0:
            bar = rf"\rule{{{bar_mm:.1f}mm}}{{1.05ex}}\ {100.0 * strict:.1f}\%"
        else:
            bar = r"0.0\%"
        lines.append(
            f"{_short_mode(mode)} & {PROFILE_LABELS[str(row['profile_id'])]} & "
            f"{float(row['display_fps']):.2f} & "
            f"{float(row['npu_invocations_per_frame']):.3f} & "
            f"{float(row['p95_frame_age_ms']):.1f} ms & {bar} & "
            f"{_deadline_provenance(row)} \\\\"
        )
        previous_mode = mode
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabularx}",
            r"\caption{Strict one-frame eligibility across matched 30-FPS controls. Bars encode only \texttt{strict\_same\_frame\_neural\_fraction}. Historical FPS comes from immediate-fallback timestamps; runtime acceptance is recorded, later composition and scanout are not. Table~\ref{tab:runtime-accounting} reports terminal routes. The unverified Lanczos-requested runtime configuration is omitted here and retained in the artifact.}",
            r"\Description{A two-resolution table figure compares immediate-fallback cadence, NPU calls per frame, p95 recorded frame age, and strict one-frame neural eligibility. Zero strict eligibility is kept separate from the runtime's looser three-frame acceptance.}",
            r"\label{fig:displayed-provenance}",
            r"\end{figure*}",
            "",
        ]
    )
    return lines


def render_generated_tex(report: Mapping[str, Any]) -> str:
    """Render compact tables that the HotMobile manuscript imports."""

    lines = [
        "% Generated by src/report/paper1_hotmobile2027_workshop.py.",
        "% Do not edit this file manually; regenerate it from frozen evidence.",
    ]
    lines.extend(render_displayed_provenance_figure(report))
    lines.extend(
        [
        r"\begin{table*}[t]",
        r"\caption{Primary 360p-to-720p accounting over all 1,500 records (five frozen scenes). Accepted, discarded, and bypassed are mutually exclusive routes; other rows overlap or are derived. A classical fallback is issued first; accepted routing does not enumerate later composition or scanout.}",
        r"\label{tab:runtime-accounting}",
        r"\centering",
        r"\fontsize{10}{11}\selectfont",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabularx}{\textwidth}{@{}lrr>{\raggedright\arraybackslash}X@{}}",
        r"\toprule",
        r"Outcome or event & Count & \% of records & Semantics \\",
        r"\midrule",
        ]
    )
    accounting = report["primary_runtime_accounting"]
    denominator = float(accounting["denominator_frame_records"])
    accounting_rows = (
        ("Submitted and completed", accounting["submitted_count"], "NPU work issued; all submissions completed"),
        ("Runtime-accepted neural", accounting["runtime_accepted_neural_count"], "Accepted by 100-ms gate; later composition not enumerated"),
        ("Completed, discarded late", accounting["late_discarded_neural_count"], "Completion missed the 100-ms client gate"),
        ("Refresh bypass", accounting["bypassed_count"], "Policy issued no NPU request"),
        ("Terminal classical route", accounting["terminal_classical_route_count"], "Bypass plus late-discard route records"),
        ("Strict one-frame eligible", accounting["strict_same_frame_eligible_count"], "Retrospective 33.33-ms source-matched credit"),
    )
    for label, count, semantics in accounting_rows:
        lines.append(
            f"{label} & {int(count):,} & {100.0 * int(count) / denominator:.1f}\\% & "
            f"{semantics} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabularx}", r"\end{table*}", ""])

    lines.extend(
        [
            r"\begin{table*}[t]",
            r"\caption{Scene-equal quality on three untouched confirmatory scenes. Late warp is motion-, depth-, and disocclusion-checked at a two-frame delay. Valid denotes the fraction admitting a neural correction; zero for classical baselines does not mean invalid output.}",
            r"\label{tab:confirmatory-quality}",
            r"\centering",
            r"\fontsize{10}{11}\selectfont",
            r"\setlength{\tabcolsep}{6.0pt}",
            r"\begin{tabular}{llrrrr}",
            r"\toprule",
            r"Mode & Method & PSNR & SSIM & LPIPS & Valid \\",
            r"\midrule",
        ]
    )
    method_labels = {
        "bicubic": "Bicubic",
        "lanczos": "Lanczos",
        "fresh_neural": "Fresh N",
        "stale_unwarped": "Stale",
        "motion_depth_disocclusion": "Late warp",
    }
    for row in report["quality_rows"]:
        lines.append(
            f"{'180/360' if str(row['mode_id']) == 'mode_180p_to_360p' else '360/720'} & "
            f"{method_labels[str(row['method'])]} & "
            f"{float(row['scene_equal_psnr']):.3f} & "
            f"{float(row['scene_equal_ssim']):.4f} & "
            f"{float(row['scene_equal_lpips']):.4f} & "
            f"{float(row['mean_valid_history_fraction']):.3f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])

    lines.extend(
        [
            r"\begin{table}[t]",
            r"\caption{Representative direct-texture always-neural latency decomposition (all values in ms). Components overlap and must not be summed as a serialized frame time. The archived application-step field is not panel scanout.}",
            r"\label{tab:latency-breakdown}",
            r"\centering",
            r"\fontsize{10}{11}\selectfont",
            r"\setlength{\tabcolsep}{3.0pt}",
            r"\begin{tabular}{lrrrrr}",
            r"\toprule",
            r"Mode & Render & Input & NPU & Recon. & App step \\",
            r"\midrule",
        ]
    )
    for row in report["latency_breakdown_rows"]:
        components = row["latency_components"]
        lines.append(
            f"{_short_mode(str(row['mode_id']))} & "
            f"{components['render']['mean_ms']:.2f} & "
            f"{components['input_transfer']['mean_ms']:.2f} & "
            f"{components['npu']['mean_ms']:.2f} & "
            f"{components['reconstruction']['mean_ms']:.2f} & "
            f"{components['presentation']['mean_ms']:.2f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def run(config_path: Path, *, overwrite: bool) -> dict[str, Any]:
    """Generate JSON, Markdown, and LaTeX from frozen workshop evidence."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    report = build_report(config)
    paper = config["workshop_paper"]
    outputs = {
        Path(paper["report_json"]): json.dumps(report, indent=2, sort_keys=True) + "\n",
        Path(paper["report_markdown"]): render_markdown(report),
        Path(paper["generated_tex"]): render_generated_tex(report),
    }
    if not overwrite and any(path.exists() for path in outputs):
        raise FileExistsError("Paper 1 workshop output exists; pass --overwrite")
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the workshop report command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Write workshop evidence and print a machine-readable completion line."""

    args = parse_args(argv)
    try:
        report = run(args.config, overwrite=args.overwrite)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 1
    print(
        "PAPER1_HOTMOBILE_WORKSHOP_PASS "
        f"runtime_rows={len(report['runtime_rows'])} "
        f"quality_rows={len(report['quality_rows'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
