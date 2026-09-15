"""Replay frozen corrected-system reductions in memory; no board or extraction.

Only the reviewed local support modules execute. Archived code never executes.
"""
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
SUPPORT=Path(__file__).with_name('corrected_runtime')


class SavedPath:
    def __init__(self, files, name):
        self.files=files
        self.path=PurePosixPath(name)

    def __truediv__(self, other):
        return SavedPath(self.files,self.path/other)

    @property
    def name(self):
        return self.path.name

    def read_bytes(self):
        return self.files[str(self.path)]

    def read_text(self, **_):
        return self.read_bytes().decode('utf-8')

    def is_file(self):
        return str(self.path) in self.files

    def relative_to(self, other):
        return self.path.relative_to(other.path)

    def rglob(self, pattern):
        assert pattern=='*'
        prefix=str(self.path)+'/'
        return (SavedPath(self.files,name) for name in sorted(self.files) if name.startswith(prefix))


def read_archive(path):
    files={}
    with tarfile.open(path) as archive:
        names=set()
        for member in archive.getmembers():
            name=PurePosixPath(member.name)
            assert not name.is_absolute() and '..' not in name.parts
            assert not member.issym() and not member.islnk()
            assert member.name not in names
            names.add(member.name)
            if member.isfile():
                files[member.name]=archive.extractfile(member).read()
            else:
                assert member.isdir()
    return files


def verify(boards=('rk3576','rk3566'), root=ROOT):
    module_names=('report','validate','design','neural_refresh_policy')
    saved={name:sys.modules.pop(name,None) for name in module_names}
    sys.path.insert(0,str(SUPPORT))
    results={}
    try:
        for board in boards:
            folder=root/'results'/board/'paper1_corrected_runtime_v1'
            expected=json.loads((folder/'summary-v1.json').read_text())
            files=read_archive(folder/'capture-evidence-v1.tar.gz')
            freeze=json.loads(files['freeze.json'])
            assert hashlib.sha256(files['freeze.json']).hexdigest()==expected['freeze_sha256']
            assert freeze['board']==board and freeze['protocol']=='paper1_corrected_runtime_v1'
            for filename in ('report.py','validate.py','design.py','neural_refresh_policy.py','policy.json'):
                bindings=[digest for name,digest in freeze['files'].items()
                          if name.endswith('/paper1-corrected-runtime-v1/'+filename)]
                assert bindings==[hashlib.sha256((SUPPORT/filename).read_bytes()).hexdigest()], filename
            reducer=importlib.import_module('report')
            state=json.loads(files['capture-v1/terminal.json'])
            assert state['status']=='COMPLETE' and not state.get('changed_files') and not state.get('error')
            assert len(state['cells'])==len(freeze['commands'])==80
            for row,command in zip(state['cells'],freeze['commands']):
                prefix='capture-v1/'+row['directory']+'/'
                assert json.loads(files[prefix+'command.json'])==command
                telemetry=[json.loads(line) for line in files[prefix+'godot_frames.jsonl'].splitlines()]
                assert len(telemetry)==300 and all(frame['scene_variant_id']==row['scene'] for frame in telemetry)
            actual=reducer.report(SavedPath(files,'capture-v1'))
            assert actual==expected, board+' frozen reduction differs from summary'
            results[board]=dict(status='PASS',cells=len(actual['cells']),
                source_frames=sum(row['source_frames'] for row in actual['cells']),
                verified_capture_files=actual['verified_files'])
    finally:
        sys.path.remove(str(SUPPORT))
        for name in module_names:
            sys.modules.pop(name,None)
            if saved[name] is not None:
                sys.modules[name]=saved[name]
    return results


if __name__=='__main__':
    print('PAPER1_CORRECTED_RUNTIME_PASS '+json.dumps(verify(),sort_keys=True))
