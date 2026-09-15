"""Offline reproduction of the independently reviewed composition successors."""
import importlib.util
import json
from pathlib import Path
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('composition_artifact',ROOT/'artifact/paper1_hotmobile2027/verify_composition_audits.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_both_archives_reproduce_source_not_draw_counts():
    result = module.verify()
    assert set(result) == {'rk3566','rk3576'}
    assert all(r['source_frames'] == 3600 and r['verified_files'] == 80 for r in result.values())


def test_false_timely_composition_claim_is_rejected(tmp_path):
    for board in ('rk3566','rk3576'):
        relative = Path('results')/board/'paper1_composition_audit_v1'
        (tmp_path/relative).mkdir(parents=True)
        for name in ('capture-evidence-v1.tar.gz','summary.json'):
            shutil.copyfile(ROOT/relative/name,tmp_path/relative/name)
    path = tmp_path/'results/rk3576/paper1_composition_audit_v1/summary.json'
    summary = json.loads(path.read_text())
    row = next(r for r in summary['rows'] if r['width']==320 and r['control']=='always' and r['logging'])
    row['timely_neural_selected_sources'] = row['strict_response_eligible']
    path.write_text(json.dumps(summary))
    with pytest.raises(AssertionError):
        module.verify(tmp_path)


def test_timeline_separates_eligibility_score_from_observed_draw_clock():
    timing_spec = importlib.util.spec_from_file_location('timing', ROOT/'artifact/paper1_hotmobile2027/explain_composition_timing.py')
    timing = importlib.util.module_from_spec(timing_spec)
    timing_spec.loader.exec_module(timing)
    report = timing.describe()
    example = report['example']
    assert example['source_id'] == 31
    assert example['selection_timestamp_logged'] is False
    assert example['receipt_age_ms'] == pytest.approx(32.987)
    assert example['eligibility_score_ms'] == pytest.approx(33.038)
    assert example['receipt_to_first_pre_ms'] == pytest.approx(83.811)
    assert example['first_pre_to_post_ms'] == pytest.approx(9.283)
    assert len(report['cells']) == 24
    bicubic = [r for r in report['cells'] if r['logging'] and r['control']=='bicubic']
    assert all(r['first_classical_selected_sources']==299 for r in bicubic)
    assert [r['first_classical_post_age_median_ms'] for r in bicubic] == pytest.approx([14.234,17.721,7.095,7.939])
    assert all(r['first_classical_selected_sources'] is None for r in report['cells'] if not r['logging'])
