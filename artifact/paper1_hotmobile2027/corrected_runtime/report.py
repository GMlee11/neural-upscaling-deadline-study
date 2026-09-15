"""Frozen equal-cell reduction; no discarded sources or selected-only headline."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
from design import schedule, cell_name
from validate import validate, rows


def distribution(values):
    values = sorted(values)
    if not values:
        return None
    return dict(n=len(values), min=values[0], median=statistics.median(values),
                mean=statistics.mean(values), max=values[-1])


def rate(timestamps):
    return (len(timestamps) - 1) * 1e6 / (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else None


def cell_report(cell, record, frames):
    validate(cell, frames, 'prompt', record['control'])
    audit = rows(cell / 'composition.jsonl')
    telemetry = rows(cell / 'godot_frames.jsonl')
    sources = [r for r in audit if r['event'] == 'source']
    terminal = [r for r in audit if r['event'] == 'terminal']
    draws = [r for r in audit if r['event'] == 'draw']
    captured = [r for r in audit if r['event'] == 'captured']
    selected = {}
    source_times = {r['source_id']: r['capture_usec'] for r in sources}
    for draw in draws:
        if draw['selected_path'] == 'neural':
            source = draw['neural_source_id']
            selected.setdefault(source, dict(draw,
                age_at_pre_ms=(draw['pre_draw_usec']-source_times[source])/1000,
                age_at_post_ms=(draw['post_draw_usec']-source_times[source])/1000))
    return dict(record, source_frames=frames, submitted=len(captured),
        completed=len([r for r in audit if r['event'] == 'release']),
        eligible=sum(r['response_eligible'] for r in terminal), selected=len(selected),
        timely_pre=sum(r['age_at_pre_ms'] <= 1000/30 for r in selected.values()),
        timely_post=sum(r['age_at_post_ms'] <= 1000/30 for r in selected.values()),
        routes=dict(Counter(r['route'] for r in terminal)),
        selection_age_pre_ms=distribution([r['age_at_pre_ms'] for r in selected.values()]),
        selection_age_post_ms=distribution([r['age_at_post_ms'] for r in selected.values()]),
        source_capture_rate=rate([r['capture_usec'] for r in sources]),
        source_terminal_rate=rate([r['recorded_usec'] for r in terminal]),
        complete_run_throughput=frames * 1e6 / (terminal[-1]['recorded_usec'] - sources[0]['capture_usec']),
        draw_rate=rate([r['post_draw_usec'] for r in draws]),
        initial_fallback_rate=rate([r['fallback_presentation_elapsed_ms'] * 1000 for r in telemetry]),
        classical_draws=sum(r['selected_path'] == 'classical' for r in draws),
        service_ms=distribution([r['npu_service_ms'] for r in telemetry if r['service_had_neural_image']]),
        per_source_timings={key: distribution([r[key] for r in telemetry]) for key in
            ('frame_age_ms', 'godot_upload_ms', 'neural_response_age_ms')})


def reduce_cells(cells):
    summaries = []
    for width in (320, 640):
        for control in ('bicubic', 'always', 'fixed2', 'scheduler'):
            for repetition in (None, 1, 2):
                group = [r for r in cells if r['width'] == width and r['control'] == control
                         and (repetition is None or r['repetition'] == repetition)]
                if not group:
                    continue
                counts = {key: sum(r[key] for r in group) for key in
                          ('source_frames', 'submitted', 'completed', 'eligible', 'selected', 'timely_pre', 'timely_post')}
                summaries.append(dict(width=width, control=control, repetition=repetition,
                    cells=len(group), **counts,
                    eligible_fraction=counts['eligible']/counts['source_frames'],
                    timely_fraction=counts['timely_post']/counts['source_frames'],
                    equal_cell_mean_rates={key: statistics.mean(r[key] for r in group if r[key] is not None)
                        for key in ('source_capture_rate', 'source_terminal_rate', 'complete_run_throughput', 'draw_rate', 'initial_fallback_rate')},
                    routes=dict(sum((Counter(r['routes']) for r in group), Counter()))))
    return summaries


def report(directory):
    state = json.loads((directory / 'terminal.json').read_text())
    manifest = json.loads((directory / 'sha256.json').read_text())
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name != 'sha256.json'}
    assert actual == set(manifest)
    for name, digest in manifest.items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, name
    frames = state['frames_per_cell']
    completed = [r for r in state['cells'] if r['status'] == 'COMPLETE']
    if state['status'] == 'COMPLETE' and not state['engineering']:
        assert frames == 300 and len(completed) == 80
        for i, (record, expected) in enumerate(zip(completed, schedule())):
            assert all(record[key] == value for key,value in expected.items())
            assert record['directory'] == cell_name(i, expected)
    cells = [cell_report(directory / r['directory'], r, frames) for r in completed]
    return dict(protocol=state['protocol'], board=state['board'], status=state['status'],
                engineering=state['engineering'], freeze_sha256=state.get('freeze_sha256'),
                verified_files=len(manifest), cells=cells, aggregates=reduce_cells(cells),
                incomplete_cells=[r for r in state['cells'] if r['status'] != 'COMPLETE'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('directory', type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    result = report(args.directory)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print('REPORT', result['status'], len(result['cells']), result['verified_files'])
