"""Accepted P7 music views and atomic, prepared application data."""
import copy

import curve_project as m
import curve_final as final
import curve_memory as memory


def binding_fingerprint(project):
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('label','path','file_path')}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return m.digest('emoblocks.accepted-binding.v1',clean({k:project[k] for k in ('project_id','ppq','bpm','total_ticks','placements','intensity_points','blank_regions','settings','protections')}))


def accepted_overlay(project):
    accepted=next((r for r in project['records'] if r['id']==project['accepted_candidate_id'] and r['kind']=='accepted_candidate'),None)
    if accepted is None:return None
    record=next((r for r in project['records'] if r['id']==accepted['payload']['final_score_id'] and r['kind']=='final_score'),None)
    return (accepted,record,record['payload'].get('p7')) if record else None


def accepted_state(project):
    row=accepted_overlay(project)
    if not row or not row[2]:return dict(status='NONE',candidate_ref=None,score_ref=None,result_id=None,mode=None,remaining_gaps=m.gaps(project),message='尚未接受完整方案。')
    accepted,record,overlay=row
    active=record['status']=='READY' and accepted['status']=='READY' and overlay['binding_fingerprint']==binding_fingerprint(project)
    return dict(status='ACTIVE' if active else 'STALE',candidate_ref=copy.deepcopy(overlay['candidate_ref']),score_ref=copy.deepcopy(overlay['score_ref']),
        result_id=accepted['payload']['result_id'],mode=overlay['mode'],remaining_gaps=copy.deepcopy(overlay['final_score']['remaining_gaps']) if active else m.gaps(project),
        message='当前编辑使用已接受乐谱。' if active else '编辑已改变，连接与边界结果失效；已锁定桥接仍受保护。')


def current_notes(project):
    row=accepted_overlay(project)
    if row and row[2] and row[1]['status']=='READY' and row[0]['status']=='READY' and row[2]['binding_fingerprint']==binding_fingerprint(project):
        return copy.deepcopy(row[2]['final_score']['notes'])
    carry=next((r for r in project['records'] if r['kind']=='captured_music' and r['status']=='READY'),None)
    if carry:
        payload=carry['payload'];ids=set(payload['added_placement_ids'])
        return final.ordered(copy.deepcopy(payload['source_notes'])+[n for p in project['placements'] if p['id'] in ids for n in m.placed_notes(p)])
    notes=[n for p in project['placements'] for n in m.placed_notes(p)]
    for lock in project['protections']:
        if lock['kind']!='bridge':continue
        # A failed range stays unavailable; do not fabricate notes in its lock.
        notes=[n for n in notes if not m.intersects(final.support(n),lock)]
        if lock['status']=='CONTENT_READY':
            actual=lock['notes']
            if row and row[2]:
                prior=[n for n in row[2]['final_score']['notes'] if m.intersects(final.support(n),lock)]
                if m.structural_notes(prior)==m.structural_notes(lock['notes']):actual=prior
            notes.extend(copy.deepcopy(actual))
    return final.ordered(notes)


def source_score(project,note_id):
    carry=next((r for r in project['records'] if r['kind']=='captured_music' and r['status']=='READY'),None)
    accepted=accepted_overlay(project)
    active=accepted and accepted[2] and accepted[0]['status']=='READY' and accepted[1]['status']=='READY' and accepted[2]['binding_fingerprint']==binding_fingerprint(project)
    target=accepted[2]['score_ref'] if active else (carry['payload']['source_score_ref'] if carry else (accepted[2]['score_ref'] if accepted and accepted[2] else None))
    if target is None:m.reject('实际输入没有绑定已接受父谱。','SOURCE_CLOSURE_INVALID')
    for record in project['records']:
        overlay=record['payload'].get('p7') if record['kind']=='final_score' else None
        if overlay and overlay['score_ref']==target and any(n['id']==note_id for n in overlay['final_score']['notes']):
            score=overlay['final_score']
            if final.ref(score)!=target or final.score_fingerprint(score)!=target['fingerprint']:m.reject('已接受父谱实际内容或身份改变。','SOURCE_CLOSURE_INVALID')
            return copy.deepcopy(score)
    m.reject('接受音符缺少真实原谱。','SOURCE_CLOSURE_INVALID')


def accepted_parent_ref(project,note_id):
    score=source_score(project,note_id)
    row=next((r for r in score['performance_map'] if note_id in r['logical_note_ids']),None)
    if row is None:m.reject('接受音符缺失真实演奏归属。','SOURCE_CLOSURE_INVALID')
    paths=[[]]
    def components(material,path):
        for child in material['children']:
            current=path+[child['occurrence_id']];paths.append(current);components(child['snapshot'],current)
    for place in project['placements']:components(place['base_snapshot'],[])
    owners=[('placement',p['id']) for p in project['placements']]
    for record in project['records']:
        overlay=record['payload'].get('p7') if record['kind']=='final_score' else None
        if overlay:
            owners.append(('final_score',overlay['final_score']['id']))
            owners.extend(('bridge',r['id']) for r in overlay['bridge_overlays'])
            owners.extend(('connection',r['id']) for r in overlay['connection_overlays'])
    matching=[path for stage,owner in owners for path in paths if final._performance(stage,owner,path)==row['performance_id']]
    if not matching:m.reject('接受音符的完整组合演奏路径不可解析。','SOURCE_CLOSURE_INVALID')
    return dict(kind='accepted_score',owner_id=score['id'],component_path=matching[0],material_snapshot_id=None,note_id=note_id)


def parent_snapshot(project,parent):
    if parent.get('kind')=='accepted_score':
        score=source_score(project,parent['note_id'])
        if score['id']!=parent['owner_id']:
            m.reject('接受父音符与指定旧谱不匹配。','SOURCE_CLOSURE_INVALID')
        return score
    place=m.indexed(project['placements'])[parent['placement_id']]
    return copy.deepcopy(place['emotion_variant'] or place['base_snapshot'])


def parent_identity(parent):return parent.get('material_snapshot_id') or parent.get('owner_id')


def context_notes(project,placement):
    if placement is None:return []
    if project['contract_rev']!=final.REV:return m.placed_notes(placement)
    extent=dict(start_tick=placement['start_tick'],end_tick=placement['start_tick']+placement['length_ticks'])
    return [n for n in current_notes(project) if m.intersects(final.support(n),extent)]


def capture_private_music(before,project,added):
    if before['contract_rev']!=final.REV or accepted_state(before)['status']!='ACTIVE':return
    score=accepted_overlay(before)[2]['final_score']
    payload=dict(source_score_ref=final.ref(score),source_input_fingerprint=m.fingerprint(before),source_notes=copy.deepcopy(score['notes']),
        performance_map=copy.deepcopy(score['performance_map']),base_binding_fingerprint=binding_fingerprint(before),added_placement_ids=list(added))
    project['records'].append(dict(id=m.digest('emoblocks.captured-music.v1',payload),kind='captured_music',version=1,status='READY',
        input_fingerprint=m.fingerprint(before),dependencies=[],payload=payload))


def effective_music(project,fact_registry=None):
    state=accepted_state(project);notes=current_notes(project)
    if state['status']=='ACTIVE':
        score=accepted_overlay(project)[2]['final_score'];events=score['emitted_notes']
        if fact_registry is not None:
            import curve_recommendations as rec
            if rec.resolve(fact_registry,state['score_ref'],'final_score')!=score:m.reject('接受覆盖与事实乐谱不一致。')
    else:events=notes
    segments=[dict(id=p['id'],start_tick=p['start_tick'],end_tick=p['start_tick']+p['length_ticks'],emotion=p['emotion'],kind='placement') for p in project['placements']]
    return dict(project_id=project['project_id'],total_ticks=project['total_ticks'],bpm=project['bpm'],notes=copy.deepcopy(notes),emitted_notes=copy.deepcopy(events),
        segments=segments,protections=copy.deepcopy(project['protections']),remaining_gaps=copy.deepcopy(state['remaining_gaps']),memory_info=memory.memory_info(project),
        accepted_ref=copy.deepcopy(state['candidate_ref']),derived_layers_status=state['status'])


def prepare_application(project,candidate,facts,input_snapshot_id,transaction_id,revision,mode=None):
    import curve_recommendations as rec
    rows=rec.validate_facts(facts);mode=mode or next(iter(candidate['modes']))
    member=candidate['modes'][mode];score=rec.resolve(rows,member['final_score_ref'],'final_score')
    request=rec.resolve(rows,score['boundary_request_ref'],'boundary_request');plan=rec.resolve(rows,score['boundary_plan_ref'],'boundary_plan')
    validation=final.validate_final_score(request,plan,score)
    bridge=request['connection_ref']['request']['bridge_ref'];base=bridge['request']['base_project']
    if bridge['request']['input_project']!=project:m.reject('方案输入与当前工程不一致。','STALE_SNAPSHOT')
    future=copy.deepcopy(base);future['contract_rev']=final.REV
    # Library labels are presentation metadata, not writes to a placement capture.
    # A prepared P4 dict may share Python objects even though JSON cannot.
    future['materials']=copy.deepcopy(base['materials'])
    for historical in future['records']:
        if historical['kind'] in ('final_score','accepted_candidate') and historical['status']!='INVALIDATED':
            historical['status']='INVALIDATED'
            historical['payload']['audit_total_ticks']=base['total_ticks']
            historical['payload']['audit_context']=dict(placements=copy.deepcopy(base['placements']),protections=copy.deepcopy(base['protections']))
    old_sources={s['id'] for s in project['sources']};old_materials={s['id'] for s in project['materials']}
    old_locks={p['id'] for p in future['protections']}
    future['protections']=copy.deepcopy(bridge['protections'])
    def record(ident,kind,payload,version=1,dependencies=()):
        row=dict(id=ident,kind=kind,version=version,status='READY',input_fingerprint=m.fingerprint(project),dependencies=list(dependencies),payload=payload)
        if any(r['id']==ident for r in future['records']):m.reject('接受计划身份重复。')
        future['records'].append(row)
    # Existing manual/inherited bridge plans retain their original ownership.
    automatic=[p for p in future['protections'] if p['id'] not in old_locks and p['kind']=='bridge']
    if automatic:
        bp=bridge['plan'];locks={p['owner_id']:p for p in automatic};ids=[w['id'] for w in bp['windows']]
        record(bp['id'],'bridge_plan',dict(candidate_id=candidate['id'],candidate_fingerprint=candidate['id'],automatic_decision='selected',bridge_ids=ids,manual_bridge_ids=[],
            ranges=[{k:w[k] for k in ('start_tick','end_tick')} for w in bp['windows']],reasons=bp['reasons'],joint_boundary_conditions=bp['joint_boundary_conditions']),bp['version'])
        for result in bridge['results']:
            if result['bridge_id'] not in locks:continue
            lock=locks[result['bridge_id']]
            record('accepted-bridge:'+result['bridge_id'],'bridge_result',dict(bridge_id=result['bridge_id'],plan_id=bp['id'],plan_version=bp['version'],protection_id=lock['id'],
                material_snapshot=copy.deepcopy(result['material']),validation=dict(status='VALID')),dependencies=[dict(id=bp['id'],version=bp['version'])])
            for material in [result['material']]+result['children']:
                if material['id'] not in {x['id'] for x in future['materials']}:future['materials'].append(copy.deepcopy(material))
    registered_materials=[x['id'] for x in future['materials'] if x['id'] not in old_materials]
    for old_record in future['records']:
        if old_record['kind']=='captured_music' and old_record['status']=='READY':
            old_record['status']='INVALIDATED';old_record['payload']['audit_total_ticks']=future['total_ticks']
            old_record['payload']['audit_context']=dict(placements=copy.deepcopy(future['placements']),protections=copy.deepcopy(future['protections']))
    for material in future['materials']:
        if material['id'] in registered_materials:
            count=future['label_counters'].get('materials',0)+1;future['label_counters']['materials']=count
            material['label']=material['label']+' · M'+str(count)
    binding=binding_fingerprint(future);candidate_ref=dict(id=candidate['id'],version=candidate['version'],fingerprint=candidate['id'])
    def overlay(values,idfield):return [dict(id=r[idfield],range=copy.deepcopy(r['range']),notes=copy.deepcopy(r['notes'])) for r in values]
    score_id='accepted-score:'+transaction_id;accepted_id='accepted:'+transaction_id;result_id='result:'+transaction_id
    original_notes=m.indexed(m.current_notes(project));final_notes=m.indexed(score['notes'])
    changed_notes=[note for ident,note in original_notes.items() if ident not in final_notes or m.structural_notes([note])!=m.structural_notes([final_notes[ident]])]
    changed_notes.extend(note for ident,note in final_notes.items() if ident not in original_notes or m.structural_notes([note])!=m.structural_notes([original_notes[ident]]))
    p7=dict(schema='emoblocks.accepted-overlay.v1',candidate_ref=candidate_ref,score_ref=final.ref(score),final_score=copy.deepcopy(score),mode=mode,binding_fingerprint=binding,
        bridge_overlays=overlay(bridge['results'],'bridge_id'),connection_overlays=overlay(request['connection_ref']['results'],'connection_id'),
        boundary_operations=copy.deepcopy(plan['operations']),write_ranges=final.b.union([final.support(n) for n in changed_notes]))
    record(score_id,'final_score',dict(total_ticks=score['total_ticks'],notes=copy.deepcopy(score['notes']),protection_summary_fingerprint=score['protection_summary_fingerprint'],validation=validation,p7=p7))
    receipt=dict(transaction_id=transaction_id,candidate_ref=candidate_ref,score_ref=final.ref(score),input_snapshot_id=input_snapshot_id,pre_revision=revision,post_revision=revision+1,
        accepted_binding_fingerprint=binding,registered_source_ids=[x['id'] for x in future['sources'] if x['id'] not in old_sources],registered_material_ids=registered_materials,
        accepted_record_id=accepted_id,result_id=result_id)
    application_ref=dict(id=transaction_id,version=1,fingerprint=m.digest('emoblocks.application.v1',receipt))
    record(accepted_id,'accepted_candidate',dict(final_score_id=score_id,transaction_id=transaction_id,input_snapshot_id=input_snapshot_id,mode=mode,candidate_ref=candidate_ref,
        score_ref=final.ref(score),application_ref=application_ref,result_id=result_id),dependencies=[dict(id=score_id,version=1)])
    future['accepted_candidate_id']=accepted_id;m.validate(future)
    return future,receipt,rec.fact('application',receipt,[final.ref(score)])
