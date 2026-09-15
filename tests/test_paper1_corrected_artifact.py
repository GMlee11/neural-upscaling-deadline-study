"""Corrected primary tables and portable saved-evidence replay."""
from pathlib import Path
import hashlib
import json
import tarfile
from collections import defaultdict
import statistics
from src.report.paper1_corrected_runtime_v1 import ROOT,load_summary,table,quality_table
from artifact.paper1_hotmobile2027.verify_corrected_runtime import verify


def test_rk3576_portable_frozen_replay():
    result=verify(boards=('rk3576',))['rk3576']
    assert result==dict(status='PASS',cells=80,source_frames=24000,verified_capture_files=641)


def test_rk3566_portable_frozen_replay():
    result=verify(boards=('rk3566',))['rk3566']
    assert result==dict(status='PASS',cells=80,source_frames=24000,verified_capture_files=641)


def test_rk3566_primary_counts_remain_separate():
    summary=load_summary(ROOT/'results/rk3566/paper1_corrected_runtime_v1/summary-v1.json','rk3566')
    text=table([summary])
    assert '21.68 & 3,000 & 0 & 2,975 & 0' in text
    assert '24.47 & 10 & 0 & 0 & 0' in text


def test_primary_table_uses_corrected_all_source_counts():
    summary=load_summary(ROOT/'results/rk3576/paper1_corrected_runtime_v1/summary-v1.json','rk3576')
    text=table([summary])
    assert '24.41 & 3,000 & 224 & 2,984 & 12' in text
    assert '30.14 & 87 & 0 & 54 & 0' in text
    assert '3,000 source frames' in text and 'not panel FPS' in text
    assert 'equal-cell arithmetic mean of per-cell capture rates' in text
    assert 'mean of capture intervals' not in text
    assert '360p' in text and '720p' in text
    assert r'Sources/s & Submitted & \shortstack{Receipt-side\\eligible} & Selected & Timely' in text
    assert 'NPU calls' not in text


def test_offline_quality_table_is_unchanged():
    historical=(ROOT/'docs/paper/generated/paper1_hotmobile2027.tex').read_text()
    selected=quality_table(historical)
    assert selected.strip() in historical
    assert '0.0523' in selected and '0.0362' in selected
    assert 'Strict one-frame eligibility across matched' not in selected


def test_replay_support_is_exact_frozen_source():
    with tarfile.open(ROOT/'results/rk3576/paper1_corrected_runtime_v1/capture-evidence-v1.tar.gz') as archive:
        freeze=json.load(archive.extractfile('freeze.json'))
    for name in ('report.py','validate.py','design.py','neural_refresh_policy.py','policy.json'):
        digest=hashlib.sha256((ROOT/'artifact/paper1_hotmobile2027/corrected_runtime'/name).read_bytes()).hexdigest()
        matches=[value for key,value in freeze['files'].items() if key.endswith('/paper1-corrected-runtime-v1/'+name)]
        assert matches==[digest]


def test_offline_observations_match_sampling_and_stored_means():
    groups = defaultdict(list)
    path = ROOT/'results/analysis/paper1_hotmobile2027_reprojection.jsonl'
    for line in path.read_text().splitlines():
        row = json.loads(line)
        groups[row['sequence_id'], row['method'], row['age_frames']].append(row)
    summary = json.loads((ROOT/'results/tables/paper1_hotmobile2027_reprojection.json').read_text())
    assert len(groups) == len(summary['sequence_summary']) == 144
    for row in summary['sequence_summary']:
        samples = groups[row['sequence_id'], row['method'], row['age_frames']]
        for metric, stride, count in (('psnr', 10, 29), ('ssim', 30, 9), ('lpips', 30, 9)):
            measured = [sample for sample in samples if sample[metric] is not None]
            assert len(measured) == count
            assert sorted(sample['frame_id'] for sample in measured) == list(range(stride, 300, stride))
            assert abs(statistics.mean(sample[metric] for sample in measured)-row[metric]) < 1e-12


def test_timing_examples_and_generated_figure():
    from src.report.paper1_corrected_runtime_v1 import timing_examples, generate
    examples=timing_examples()
    assert [(e['repetition'],e['source_id']) for e in examples]==[(1,9),(2,192)]
    assert [(e['receipt_ms'],e['assignment_stamp_ms'],e['first_post_ms']) for e in examples]==[
        (33.082,40.203,51.823),(31.807,34.119,43.421)]
    assert all(e['eligibility_ms']<=1000/30<e['first_post_ms'] for e in examples)
    assert [(e['upload_ms'],e['eligibility_ms']) for e in examples]==[(0.045,33.127),(0.039,31.846)]
    assert all(e['eligibility_ms']<e['assignment_stamp_ms']<e['first_post_ms'] for e in examples)
    from src.report.paper1_corrected_runtime_v1 import timing_figure
    figure=timing_figure()
    assert '33.082 + 0.045 & = & 33.127' in figure
    assert '31.807 + 0.039 & = & 31.846' in figure
    assert generate()==(ROOT/'docs/paper/generated/paper1_corrected_runtime_v1.tex').read_text()
    summary=load_summary(ROOT/'results/rk3576/paper1_corrected_runtime_v1/summary-v1.json','rk3576')
    row=next(r for r in summary['aggregates'] if r['width']==640 and r['control']=='scheduler' and r['repetition'] is None)
    assert f"{row['equal_cell_mean_rates']['initial_fallback_rate']:.2f}"=='30.15'
    assert f"{row['equal_cell_mean_rates']['draw_rate']:.2f}"=='77.36'
