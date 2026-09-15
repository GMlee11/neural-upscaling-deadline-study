"""Read-only, post-capture descriptive timing audit; no new experiment or tuning.

Receipt age plus upload duration is an eligibility score, NOT a selection clock.
All medians use one observation per source, never draw-weighted repetitions.
"""
import hashlib
import json
from pathlib import Path
import statistics
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def first_selection_ages(events, path):
    first = {}
    for row in events:
        if row['event'] == 'draw' and row['selected_path'] == path:
            first.setdefault(row['base_source_id'], row['age_at_post_ms'])
    return list(first.values())


def describe(root=ROOT):
    report = {'classification': 'post-capture descriptive analysis, not preregistered contrasts',
              'paired_comparison': 'one logging-on/off cell each; both retain ownership and scheduling changes',
              'cells': [], 'example': None}
    for board in ('rk3566', 'rk3576'):
        file = root/'results'/board/'paper1_composition_audit_v1/capture-evidence-v1.tar.gz'
        with tarfile.open(file) as archive:
            data = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}
        manifest = json.loads(data['capture-evidence-v1.sha256.json'])
        assert set(data) == set(manifest) | {'capture-evidence-v1.sha256.json'}
        for name, digest in manifest.items():
            assert hashlib.sha256(data[name]).hexdigest() == digest, name
        prefix = 'capture/capture-v1/'
        for cell in json.loads(data[prefix+'terminal.json'])['rows']:
            path = prefix+f'{cell["index"]:02d}_{cell["width"]}_{cell["control"]}_{cell["logging"]}/'
            frames = [json.loads(s) for s in data[path+'godot_frames.jsonl'].splitlines()]
            events = [json.loads(s) for s in data[path+'composition.jsonl'].splitlines()]
            assert len(frames) == 300
            clocks = [f['frame_capture_elapsed_ms'] for f in frames]
            ages = first_selection_ages(events, 'classical') if cell['logging'] else []
            report['cells'].append(dict(board=board, width=cell['width'], control=cell['control'],
                logging=cell['logging'], sources=len(frames),
                source_rate_per_s=299000/(clocks[-1]-clocks[0]),
                response_eligible=sum(f['strict_same_frame_neural'] for f in frames),
                receipt_age_median_ms=statistics.median(f['neural_response_age_ms'] for f in frames),
                first_classical_selected_sources=len(ages) if cell['logging'] else None,
                first_classical_post_age_median_ms=statistics.median(ages) if ages else None))
            if board == 'rk3576' and cell['width'] == 320 and cell['control'] == 'always' and cell['logging']:
                frame = next(f for f in frames if f['strict_same_frame_neural'])
                sid = frame['frame_id']
                capture = next(e['capture_usec'] for e in events if e['event']=='source' and e['source_id']==sid)
                related = [e for e in events if e.get('source_id')==sid or e.get('neural_source_id')==sid]
                draw = next(e for e in related if e['event']=='draw')
                report['example'] = dict(source_id=sid, selection_timestamp_logged=False,
                    receipt_age_ms=frame['neural_response_age_ms'], upload_duration_ms=frame['godot_upload_ms'],
                    eligibility_score_ms=frame['neural_response_age_ms']+frame['godot_upload_ms'],
                    first_neural_pre_age_ms=draw['age_at_pre_ms'], first_neural_post_age_ms=draw['age_at_post_ms'],
                    receipt_to_first_pre_ms=draw['age_at_pre_ms']-frame['neural_response_age_ms'],
                    first_pre_to_post_ms=(draw['post_draw_usec']-draw['pre_draw_usec'])/1000,
                    events=[dict(event=e['event'], age_ms=(e['recorded_usec']-capture)/1000)
                            for e in related if 'recorded_usec' in e])
    return report


if __name__ == '__main__':
    print(json.dumps(describe(), indent=2, sort_keys=True))
