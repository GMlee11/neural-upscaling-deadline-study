"""Verify all three resolutions without conflating their session identities."""
from artifact.paper1_hotmobile2027.verify_180p_runtime import verify
from src.report.paper1_corrected_runtime_v1 import ROOT, generate, load_180p_summary


def test_both_180p_captures_replay():
    result = verify()
    for board, count in (('rk3576',245), ('rk3566',243)):
        assert result[board] == dict(status='PASS', cells=40, source_frames=12000,
            verified_capture_files=321, local_frozen_inputs_verified=count)


def test_three_resolution_table_preserves_counts():
    text = generate()
    assert '30.17 & 3,000 & 2,791 & 3,000 & 1,032' in text
    assert '25.99 & 3,000 & 0 & 3,000 & 0' in text
    assert '24.41 & 3,000 & 224 & 2,984 & 12' in text
    assert '30.14 & 87 & 0 & 54 & 0' in text
    assert text.count('180p &') == 2
    assert text.count('360p &') == 2
    assert text.count('720p &') == 2
    assert 'separate sessions and configurations' in text
    assert text == (ROOT/'docs/paper/generated/paper1_corrected_runtime_v1.tex').read_text()


def test_all_sources_and_repetitions_retained():
    for board in ('rk3576','rk3566'):
        summary = load_180p_summary(ROOT, board)
        assert len(summary['cells']) == 40
        assert all(r['source_frames']==300 for r in summary['cells'])
        rows = [r for r in summary['aggregates'] if r['control']=='always' and r['repetition']]
        assert [r['timely_post'] for r in rows] == ([536,496] if board=='rk3576' else [0,0])
