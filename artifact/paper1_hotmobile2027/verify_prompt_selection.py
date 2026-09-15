"""Read-only verification of the controlled prompt-selection evidence and counts.

No board, inference runtime, archive extraction, or execution of archived code.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'results/rk3576/paper1_prompt_selection_v1'

def verify():
    expected=json.loads((EVIDENCE/'summary.json').read_text())
    with tarfile.open(EVIDENCE/'capture-evidence-v1.tar.gz') as archive:
        files={}
        for member in archive.getmembers():
            assert not member.issym() and not member.islnk()
            assert not PurePosixPath(member.name).is_absolute() and '..' not in PurePosixPath(member.name).parts
            if member.isfile():
                assert member.name not in files
                files[member.name]=archive.extractfile(member).read()
    manifest=json.loads(files['capture-v1/sha256.json'])
    for name,digest in manifest.items():
        assert hashlib.sha256(files['capture-v1/'+name]).hexdigest()==digest,name
    assert hashlib.sha256(files['freeze.json']).hexdigest()==expected['freeze_sha256']
    state=json.loads(files['capture-v1/terminal.json'])
    assert state['status']==expected['status']=='COMPLETE'
    assert len(state['cells'])==len(expected['cells'])==16
    counts=[]
    for cell,reference in zip(state['cells'],expected['cells']):
        assert cell['status']=='COMPLETE'
        prefix=f'capture-v1/{cell["index"]:02d}_{cell["width"]}_{cell["control"]}_{cell["mode"]}/'
        records=lambda filename:[json.loads(x) for x in files[prefix+filename].splitlines()]
        audit=records('composition.jsonl');frames=records('godot_frames.jsonl');events=records('selection_events.jsonl')
        assert [f['frame_id'] for f in frames]==list(range(300))
        sources={x['source_id']:x['capture_usec'] for x in audit if x['event']=='source'}
        callbacks={x['source_id']:x for x in events if x['event']=='callback_ready'}
        terminals=[x for x in audit if x['event']=='terminal']
        assert len(sources)==len(terminals)==300 and not audit[0]['errors']
        eligible=0
        for f,t in zip(frames,terminals):
            s=f['frame_id'];assert s==t['source_id']
            score=(callbacks[s]['worker_received_usec']-sources[s])/1000+f['godot_upload_ms'] if s in callbacks else float('inf')
            strict=score<=1000/30
            assert strict==f['strict_same_frame_neural']==t['response_eligible']
            eligible+=strict
        selected={}
        for d in audit:
            if d['event']=='draw' and d['selected_path']=='neural':
                source=d['neural_source_id']
                assert source==d['base_source_id'] and source in callbacks
                selected.setdefault(source,d)
        pre=sum((d['pre_draw_usec']-sources[s])/1000<=1000/30 for s,d in selected.items())
        post=sum((d['post_draw_usec']-sources[s])/1000<=1000/30 for s,d in selected.items())
        count=dict(index=cell['index'],response_eligible=eligible,eventually_selected=len(selected),timely_selected_pre=pre,timely_selected_post=post,source_frames=300)
        assert all(reference[k]==v for k,v in count.items()),count
        counts.append(count)
    return dict(status='PASS',source_frames=4800,verified_capture_files=len(manifest),cells=counts)

if __name__=='__main__':print(json.dumps(verify(),indent=2))
