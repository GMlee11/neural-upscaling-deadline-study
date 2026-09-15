"""Read-only source/draw accounting from the two archived successor sessions.

Never extracts or executes archive contents and never contacts hardware.
"""
import hashlib
import json
from pathlib import Path
import statistics
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def verify(root=ROOT):
    reports = {}
    for board in ('rk3566', 'rk3576'):
        folder = root/'results'/board/'paper1_composition_audit_v1'
        with tarfile.open(folder/'capture-evidence-v1.tar.gz','r:gz') as archive:
            members = archive.getmembers()
            assert len({m.name for m in members}) == len(members), 'duplicate archive member'
            assert all(m.isfile() for m in members), 'only regular evidence files allowed'
            data = {m.name:archive.extractfile(m).read() for m in members}
        manifest = json.loads(data['capture-evidence-v1.sha256.json'])
        assert set(data) == set(manifest) | {'capture-evidence-v1.sha256.json'}
        for name,digest in manifest.items():
            assert hashlib.sha256(data[name]).hexdigest() == digest,name
        prefix = 'capture/capture-v1/'
        terminal = json.loads(data[prefix+'terminal.json'])
        summary = json.loads((folder/'summary.json').read_text())
        assert terminal['status'] == summary['status'] == 'COMPLETE'
        assert len(terminal['rows']) == len(summary['rows']) == 12
        for cell,reported in zip(terminal['rows'],summary['rows']):
            assert cell['status'] == 'COMPLETE' and cell['source_frames'] == 300
            assert all(reported[k] == cell[k] for k in ('index','width','control','logging'))
            path = prefix+f'{cell["index"]:02d}_{cell["width"]}_{cell["control"]}_{cell["logging"]}/'
            frames = [json.loads(s) for s in data[path+'godot_frames.jsonl'].splitlines()]
            events = [json.loads(s) for s in data[path+'composition.jsonl'].splitlines()]
            assert [r['frame_id'] for r in frames] == list(range(300))
            assert events[0]['source_count'] == 300 and not events[0]['errors']
            assert events[0]['logging_enabled'] == cell['logging']
            assert reported['strict_response_eligible'] == sum(r['strict_same_frame_neural'] for r in frames)
            if not cell['logging']:
                assert len(events) == 1
                continue
            sources = [r for r in events if r['event'] == 'source']
            terminals = [r for r in events if r['event'] == 'terminal']
            draws = [r for r in events if r['event'] == 'draw']
            assert [r['source_id'] for r in sources] == list(range(300))
            assert [r['source_id'] for r in terminals] == list(range(300))
            assert [r['draw_id'] for r in draws] == list(range(events[0]['draw_count']))
            clocks = {r['source_id']:r['capture_usec'] for r in sources}
            for r in draws:
                if r['selected_path'] == 'blank':
                    assert r['base_source_id'] == r['neural_source_id'] == -1
                    continue
                assert r['source_capture_usec'] == clocks[r['base_source_id']]
                assert abs(r['age_at_post_ms']-(r['post_draw_usec']-r['source_capture_usec'])/1000) < .001
                assert r['source_capture_usec'] <= r['pre_draw_usec'] <= r['post_draw_usec']
                assert r['within_one_frame_at_post'] == (r['selected_path']=='neural' and r['age_at_post_ms'] <= 1000/30)
            neural = [r for r in draws if r['selected_path'] == 'neural']
            accepted = {r['source_id'] for r in terminals if r['runtime_accepted']}
            selected = {r['neural_source_id'] for r in neural}
            timely = {r['neural_source_id'] for r in neural if r['within_one_frame_at_post']}
            assert selected <= accepted
            assert all(r['base_source_id'] == r['neural_source_id'] for r in neural)
            counts = dict(runtime_accepted_sources=len(accepted),neural_selected_sources=len(selected),
                          timely_neural_selected_sources=len(timely),accepted_not_selected=len(accepted-selected),
                          neural_draws=len(neural),classical_draws=sum(r['selected_path']=='classical' for r in draws),
                          blank_draws=sum(r['selected_path']=='blank' for r in draws))
            assert all(reported[k] == v for k,v in counts.items()),counts
            median = statistics.median(r['age_at_post_ms'] for r in neural) if neural else None
            assert median == reported['neural_post_age_median_ms']
        assert summary['source_frames'] == 3600
        reports[board] = dict(source_frames=3600,cells=12,verified_files=len(manifest))
    print('PAPER1_COMPOSITION_AUDITS_PASS '+json.dumps(reports,sort_keys=True))
    return reports


if __name__ == '__main__':
    verify()
