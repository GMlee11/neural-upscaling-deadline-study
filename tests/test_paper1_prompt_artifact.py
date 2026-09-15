"""Reproduce the corrected-presenter result without board access."""

import json
from pathlib import Path

from artifact.paper1_hotmobile2027.verify_prompt_selection import verify


def test_frozen_prompt_capture_counts():
    result = verify()
    assert result['status'] == 'PASS'
    assert result['source_frames'] == 4800
    assert result['verified_capture_files'] == 114
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / 'results/rk3576/paper1_prompt_selection_v1/summary.json').read_text())
    rows = summary['cells']
    low = [r for r in rows if r['width'] == 320 and r['control'] == 'always']
    assert len(low) == 4
    assert sum(r['timely_selected_post'] for r in low if r['mode'] == 'prompt') == 11
    assert sum(r['timely_selected_post'] for r in low if r['mode'] == 'ordered') == 0
    assert all(r['eventually_selected'] == 300 for r in low)
    assert all(r['timely_selected_post'] == 0 for r in rows if r['width'] == 640)
