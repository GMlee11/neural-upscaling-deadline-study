"""Read-only verification of compact RK3566 totals and qualification identities.

This verifies reductions from the packaged per-cell summaries, not the omitted
raw frame stream. Full raw replay uses the separately hash-identified archive.
"""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "results/rk3566/paper1_replication_v1"


def main():
    report = json.loads((EVIDENCE / "summary.json").read_text())
    terminal = json.loads((EVIDENCE / "terminal.json").read_text())
    freeze = json.loads((EVIDENCE / "freeze.json").read_text())
    qual_bytes = (EVIDENCE / "qualification.json").read_bytes()
    qual = json.loads(qual_bytes)
    assert hashlib.sha256(qual_bytes).hexdigest() == freeze["files"]["engineering/direct-qualification-v6-check.json"]
    assert qual["all_pass"] and len(qual["cases"]) == 16 and all(r["pass"] for r in qual["cases"])
    assert freeze["independent_review_approved"] and freeze["numerical_qualification_pass"]
    assert len(report["runs"]) == 50
    assert len({(r["scene"], r["width"], r["control"]) for r in report["runs"]}) == 50
    complete = [r for r in report["runs"] if r["status"] == "COMPLETE"]
    assert len(complete) == report["completed_cells"] == terminal["completed_cells"]
    if report["status"] == "COMPLETE":
        assert len(complete) == 50
    for row in complete:
        assert row["frame_count"] == 300
        assert 0 <= row["strict_eligible_count"] <= row["runtime_accepted_count"] <= row["npu_completed_frames"] <= 300
        assert abs(row["strict_same_frame_neural_fraction"] - row["strict_eligible_count"]/300) < 1e-12
        assert row["maximum_temperature_c"] < 80
    for aggregate in report["aggregates"]:
        cells = [r for r in complete if r["width"] == aggregate["width"] and r["control"] == aggregate["control"]]
        assert len(cells) == aggregate["completed_scenes"]
        if not cells:
            continue
        for field in ("strict_eligible_count", "runtime_accepted_count", "npu_completed_frames"):
            assert sum(r[field] for r in cells) == aggregate[field]
        assert aggregate["frames"] == 300 * len(cells)
        assert abs(statistics.fmean(r["fallback_cadence_fps"] for r in cells) - aggregate["mean_fallback_cadence_fps"]) < 1e-10
    print(f"PAPER1_RK3566_COMPACT_EVIDENCE_PASS cells={len(complete)}/50 status={report['status']}")


if __name__ == "__main__":
    main()
