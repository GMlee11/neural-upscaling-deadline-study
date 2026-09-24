"""Portable, read-only replay of both 180p captures using hash-bound reducers.

Only distributed support modules execute, never code loaded from the archive.
Raw archives and all frozen experiment identities remain unchanged.
"""
import hashlib
import importlib
import json
from pathlib import Path
import sys

if __package__:
    from .verify_corrected_runtime import SavedPath, read_archive
else:
    from verify_corrected_runtime import SavedPath, read_archive

ROOT = Path(__file__).resolve().parents[2]


def verify(root=ROOT, boards=('rk3576', 'rk3566')):
    results = {}
    module_names = ('report', 'validate', 'design', 'neural_refresh_policy')
    for board in boards:
        support = root/'artifact/paper1_hotmobile2027/runtime_180p'/board
        files = read_archive(root/f'results/{board}/paper1_180p_output_v1/capture-evidence-v1.tar.gz')
        expected = json.loads((root/f'results/analysis/paper1_180p_output_v1_{board}.json').read_text())
        freeze = json.loads(files['freeze.json'])
        assert freeze['board'] == board and freeze['protocol'] == 'paper1_180p_output_v1'
        assert hashlib.sha256(files['freeze.json']).hexdigest() == expected['freeze_sha256']
        model_paths = [p for p in freeze['files'] if p.endswith('/paper1-180p-output-v1/model.rknn')]
        assert len(model_paths) == 1
        prefix = model_paths[0][:-len('model.rknn')]
        checked = 0
        for name, digest in freeze['files'].items():
            if name.startswith(prefix):
                assert hashlib.sha256(files[name[len(prefix):]]).hexdigest() == digest, name
                checked += 1
        for name in (*[n+'.py' for n in module_names], 'policy.json'):
            digest = hashlib.sha256((support/name).read_bytes()).hexdigest()
            assert digest == freeze['files'][prefix+name]
        saved = {name: sys.modules.pop(name, None) for name in module_names}
        sys.path.insert(0, str(support))
        try:
            design = importlib.import_module('design')
            reducer = importlib.import_module('report')
            assert freeze['schedule'] == design.schedule()
            state = json.loads(files['capture-v1/terminal.json'])
            assert state['status'] == 'COMPLETE' and not state.get('changed_files') and not state.get('error')
            assert len(state['cells']) == len(freeze['commands']) == 40
            for row, command in zip(state['cells'], freeze['commands']):
                assert json.loads(files['capture-v1/'+row['directory']+'/command.json']) == command
                assert '--maximum-neural-age-frames=3' in command
                assert '--mode=mode_90p_to_180p' in command
                assert '--spatial-input-fixture=true' not in command
            actual = reducer.report(SavedPath(files, 'capture-v1'))
            assert actual == expected, board+' saved summary differs from frozen reduction'
            assert sum(r['source_frames'] for r in actual['cells']) == 12000
            results[board] = dict(status='PASS', cells=40, source_frames=12000,
                verified_capture_files=actual['verified_files'], local_frozen_inputs_verified=checked)
        finally:
            sys.path.remove(str(support))
            for name in module_names:
                sys.modules.pop(name, None)
                if saved[name] is not None:
                    sys.modules[name] = saved[name]
    return results


if __name__ == '__main__':
    print('PAPER1_180P_RUNTIME_PASS '+json.dumps(verify(), sort_keys=True))
