"""Complete event/ownership joins for normal prompt-selection cells; read only."""
import json
from pathlib import Path
from neural_refresh_policy import RefreshObservation, choose_refresh_action, load_refresh_policy

def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()]

def unique(events,kind,key='source_id'):
    selected=[x for x in events if x['event']==kind]
    result={x[key]:x for x in selected}
    assert len(result)==len(selected),(kind,'duplicates')
    return result

def validate(out,frames,mode,control):
    ev=rows(out/'selection_events.jsonl')
    audit=rows(out/'composition.jsonl')
    telemetry=rows(out/'godot_frames.jsonl')
    assert ev[-1]['event']=='finalize' and ev[-1]['drained'] and not ev[-1]['reason'] and not ev[-1]['unresolved']
    assert all(a['recorded_usec']<=b['recorded_usec'] for a,b in zip(ev,ev[1:]))
    enter=unique(ev,'recorder_enter'); leave=unique(ev,'recorder_exit')
    terminal=unique(audit,'terminal'); capture=unique(audit,'captured')
    callbacks=unique(ev,'callback_ready'); release=unique(audit,'release')
    assert set(enter)==set(leave)==set(terminal)==set(range(frames))
    assert set(capture)==set(callbacks)==set(release)
    assert control in ('always', 'bicubic', 'fixed2', 'scheduler')
    if control == 'always':
        assert set(capture) == set(range(frames))
    elif control == 'bicubic':
        assert not capture
    elif control == 'fixed2':
        assert set(capture) == set(range(0, frames, 2))
    else:
        bypass = {r['frame_id'] for r in telemetry if r['route_status'] == 'refresh_policy_bypass'}
        assert set(capture).isdisjoint(bypass)
        assert set(capture) | bypass == set(range(frames))
    if control == 'fixed2':
        assert all(r['route_status'] == 'fixed_period_fallback' for r in telemetry if r['frame_id'] % 2)
    if control == 'bicubic':
        assert all(r['route_status'] == 'forced_classical_control' for r in telemetry)
    sources=unique(audit,'source')
    by_source={r['frame_id']:r for r in telemetry}
    if control == 'scheduler':
        policy = load_refresh_policy(Path(__file__).with_name('policy.json'))
        decisions = unique(ev, 'refresh_decision')
        assert set(decisions) == set(range(frames))
        last_submit = None
        for source in range(frames):
            logged = decisions[source]
            observation = logged['observation']
            assert observation['frame_id'] == source
            assert observation['last_submitted_neural_frame'] == last_submit
            earlier = [s for s,t in terminal.items() if t['recorded_usec'] < logged['recorded_usec'] and t['runtime_accepted']]
            assert observation['last_committed_neural_frame'] == max(earlier, default=None)
            completed_before = sorted(s for s,t in terminal.items() if t['recorded_usec'] < logged['recorded_usec'] and s in callbacks)
            estimate = None
            for previous in completed_before:
                service = by_source[previous]['npu_service_ms']
                estimate = service if estimate is None else policy['service_ewma_alpha'] * service + (1-policy['service_ewma_alpha']) * estimate
            assert (estimate is None and observation['measured_service_ewma_ms'] is None) or (
                estimate is not None and abs(estimate-observation['measured_service_ewma_ms']) < .001)
            expected = choose_refresh_action(policy, RefreshObservation(**observation))
            for key, value in expected.items():
                actual = logged['decision'][key]
                if isinstance(value, float):
                    assert abs(actual - value) < .001, (source, key, actual, value)
                else:
                    assert actual == value, (source, key, actual, value)
            assert (expected['action'] == 'submit') == (source in capture)
            assert by_source[source]['refresh_policy_action'] == expected['action']
            assert by_source[source]['refresh_policy_reason'] == expected['reason']
            if source in capture:
                last_submit = source
        first = decisions[0]['observation']
        assert first['last_submitted_neural_frame'] is None
        assert first['last_committed_neural_frame'] is None
        assert first['measured_service_ewma_ms'] is None
    for s in enter:
        assert enter[s]['recorded_usec']<=terminal[s]['recorded_usec']<=leave[s]['recorded_usec']
    for s,cb in callbacks.items():
        assert cb['native_token']==capture[s]['native_token']==release[s]['native_token']
        assert sources[s]['capture_usec']<=cb['worker_received_usec']<=cb['recorded_usec']<=release[s]['recorded_usec']
    neural=[r for r in audit if r['event']=='draw' and r['selected_path']=='neural']
    draws=[r for r in audit if r['event']=='draw']
    pre_events=[x for x in ev if x['event']=='pre_draw_entry']
    process_events=[x for x in ev if x['event']=='presenter_process_entry']
    assert len(pre_events)==len(draws) and process_events
    for p,draw in zip(pre_events,draws):
        assert p['recorded_usec']<=draw['pre_draw_usec']<=draw['post_draw_usec']
        if draw['selected_path']=='blank':
            assert draw['base_source_id']==-1 and not draw['within_one_frame_at_post']
            continue
        capture_time=sources[draw['base_source_id']]['capture_usec']
        pre_age=(draw['pre_draw_usec']-capture_time)/1000
        assert abs(pre_age-draw['age_at_pre_ms'])<.001
        age=(draw['post_draw_usec']-capture_time)/1000
        assert abs(age-draw['age_at_post_ms'])<.001
        assert draw['within_one_frame_at_post']==(draw['selected_path']=='neural' and age<=1000/30)
    for s,t in terminal.items():
        f=by_source[s]
        score=f['neural_response_age_ms']+f['godot_upload_ms']
        if s in callbacks:
            receipt=(callbacks[s]['worker_received_usec']-sources[s]['capture_usec'])/1000
            assert abs(receipt-f['neural_response_age_ms'])<.001
        strict=(s in callbacks and score<=1000/30)
        assert t['response_eligible']==f['strict_same_frame_neural']==strict
        assert abs(score-t['response_age_ms'])<.001
        assert t['runtime_accepted']==f['has_neural_image']
        assert t['route']==f['route_status']
    if mode=='ordered':
        assignments=unique(ev,'ordered_assignment')
        assert assignments.keys()==terminal.keys()
        for s in callbacks:
            assert abs(assignments[s]['upload_ms']-by_source[s]['godot_upload_ms'])<.001
            assert terminal[s]['runtime_accepted']==(terminal[s]['response_age_ms']<=100)
    if mode=='prompt':
        dispositions=unique(ev,'disposition'); releases=unique(ev,'release')
        assert dispositions.keys()==callbacks.keys()==releases.keys()
        assert all(x['ok'] for x in releases.values())
        assignment=unique(ev,'assignment')
        posts=unique(ev,'validated_post_draw')
        decisions=unique(ev,'decision'); detaches=unique(ev,'detach')
        assert decisions.keys()==detaches.keys()==dispositions.keys()
        assert [r['neural_source_id'] for r in neural]==sorted(r['neural_source_id'] for r in neural)
        for s,d in dispositions.items():
            decision=decisions[s]
            receipt=(callbacks[s]['worker_received_usec']-sources[s]['capture_usec'])/1000
            assert abs(decision['receipt_age_ms']-receipt)<.001
            assert callbacks[s]['recorded_usec']<=decision['recorded_usec']<=detaches[s]['recorded_usec']<=releases[s]['recorded_usec']
            assert any(p['recorded_usec']<=decision['recorded_usec'] for p in process_events)
            previous=[x['source_id'] for x in assignment.values() if x['recorded_usec']<decision['recorded_usec'] and dispositions[x['source_id']]['accepted']]
            assert decision['last_selected']==max(previous,default=-1)
            assert abs(d['upload_ms']-by_source[s]['godot_upload_ms'])<.001
            drawn=[r for r in neural if r['neural_source_id']==s]
            assert d['accepted']==bool(drawn)==terminal[s]['runtime_accepted']
            assert d['reason']==terminal[s]['route']
            assert releases[s]['recorded_usec']<=d['recorded_usec']<=terminal[s]['recorded_usec']
            if d['accepted']:
                assert len(drawn)==1 and s in assignment and s in posts
                draw=drawn[0]
                assert callbacks[s]['recorded_usec']<=assignment[s]['recorded_usec']<=draw['pre_draw_usec']<=draw['post_draw_usec']<=releases[s]['recorded_usec']
                assert posts[s]['draw_id']==draw['draw_id']
                assert draw['post_draw_usec']<=detaches[s]['recorded_usec']
                assert decision['recorded_usec']<=assignment[s]['recorded_usec']
                assert abs(assignment[s]['upload_ms']-d['upload_ms'])<.001
                age=(callbacks[s]['worker_received_usec']-sources[s]['capture_usec'])/1000+d['upload_ms']
                assert abs(age-terminal[s]['response_age_ms'])<.01
                assert age<=100.0
            else:
                assert d['reason'] in ('prompt_superseded','client_late_neural_discarded')
                if d['reason']=='prompt_superseded':assert s<=decision['last_selected']
                else:assert receipt+d['upload_ms']>100
    return {'valid':True,'source_frames':frames,'callback_count':len(callbacks),'mode':mode}
