"""P6 pure, bounded connection music over authenticated actual P5 emissions.

No project edits, lock writes, emotion recomputation, rendering or P7. Frozen
identity, seed and ledger helpers come from the independent public service.
"""
import copy
import math
import random

import curve_connections as service
import curve_melody as melody
import curve_project as m
import intensity_curve

CONTRACT_REV = 'curve-workflow-v2-r3-p6'
ALGORITHM_VERSION = 'curve-connection-v1'
RNG_VERSION = 'python.random-v3'
TECHNIQUES = ('diatonic_guide', 'motif_reply', 'density_shift', 'retain_develop', 'breath_close')


def _fail(code, message):
    raise m.ProjectError(code, message)


def _error(code, message, **details):
    return dict(code=code, message=message, details=details)


def _check(cancel):
    if cancel is not None and cancel():
        _fail('CANCELLED', '连接阶段已协作取消。')


def _progress(callback, message):
    if callback is not None:
        callback(message)


def _range(a, b):
    return dict(start_tick=a, end_tick=b)


def _support(n):
    return _range(n['start_tick'], n['start_tick']+n['duration_tick'])


def _pair(r):
    return r['start_tick'], r['end_tick']


def _ordered(notes):
    return sorted(copy.deepcopy(notes), key=lambda n:(n['start_tick'], n['pitch'], n['duration_tick'], n['id']))


def _music(notes):
    return sorted((n['pitch'], n['start_tick'], n['duration_tick']) for n in notes)


def _union(regions):
    merged = []
    for a, b in sorted(set(map(_pair, regions))):
        if merged and a <= merged[-1]['end_tick']:
            merged[-1]['end_tick'] = max(merged[-1]['end_tick'], b)
        else:
            merged.append(_range(a, b))
    return merged


def _forbidden(request):
    return service.forbidden_ranges(request)


def _request_hash(request):
    return service.request_fingerprint(request)


def _seed(request, window, joints, locked_plan=None):
    # During planning this is only a music helper context, never a published
    # Plan. Actual generation passes the full independently validated Plan.
    context = locked_plan if locked_plan is not None else dict(joint_boundary_conditions=joints)
    return service.musical_seed(request, context, window)


def _validate_request(request):
    service.validate_request(request)


def _context(request, window, windows):
    return service.window_context(request, window, windows)


def _legal(request, region):
    if not 0<=region['start_tick']<region['end_tick']<=request['actual_layout']['total_ticks']:
        return False
    if any(m.intersects(region,r) for r in _forbidden(request)):
        return False
    return all(not m.intersects(_support(n),region) or region['start_tick']<=n['start_tick']<_support(n)['end_tick']<=region['end_tick']
               for n in request['actual_layout']['notes'])


def _writable_regions(request):
    regions=[_range(0,request['actual_layout']['total_ticks'])]
    for guard in _forbidden(request):
        kept=[]
        for r in regions:
            a,b=_pair(r);x,y=_pair(guard)
            if y<=a or b<=x:kept.append(r)
            else:
                if a<x:kept.append(_range(a,x))
                if y<b:kept.append(_range(y,b))
        regions=kept
    return regions


def _captured_key(request, notes):
    if not notes:
        _fail('EMPTY_MATERIAL','没有实际动机或邻接父发声。')
    parent=service.parent_ref(request,notes[0]['id'])
    if parent['kind']=='bridge':
        snapshot=next(r['material'] for r in request['bridge_ref']['results'] if r['bridge_id']==parent['owner_id'])
    else:
        place=next(p for p in request['actual_layout']['base_project']['placements'] if p['id']==parent['owner_id'])
        snapshot=place['emotion_variant'] or place['base_snapshot']
    key=melody._key(snapshot,notes);key['confidence']=min(1.,key['confidence'])
    return key


def _window(request, region, technique, windows=()):
    notes=[n for n in request['actual_layout']['notes'] if m.intersects(_support(n),region)]
    left,right=_context(request,region,list(windows) or [region])
    motif=notes[:8]+([left] if left else [])+([right] if right else [])
    if technique=='retain_develop':
        motif += [n for n in notes if _support(n)['end_tick']<=(region['start_tick']+region['end_tick'])/2]
    if not motif:
        _fail('EMPTY_MATERIAL','没有真实连接动机。')
    motif=list({n['id']:n for n in motif}.values())
    key=_captured_key(request,motif)
    values=list(_pair(region))+[n[k] for n in notes+([left] if left else [])+([right] if right else []) for k in ('start_tick','duration_tick')]
    unit=10 if all(v%10==0 for v in values) else 1
    ident=m.digest('emoblocks.connection-window.v1',dict(request_fingerprint=_request_hash(request),range=region,technique=technique))
    return dict(id=ident,**region,technique=technique,context=dict(left=copy.deepcopy(left),right=copy.deepcopy(right),motif_note_ids=[n['id'] for n in motif]),
        original_notes=_ordered(notes),reasons=[_error('MUSICAL_DEVELOPMENT','根据真实左右发声和动机发展连接，保留所有桥及保护。')],
        key_context=key,parameters=dict(target_ticks=region['end_tick']-region['start_tick'],unit_ticks=unit))


def _joint_endpoints(window,joints):
    entry=exit_=None;entry_null=exit_null=False
    for j in joints:
        if j['right_connection_id']==window['id']:
            entry=j['right_endpoint'];entry_null=entry is None
        if j['left_connection_id']==window['id']:
            exit_=j['left_endpoint'];exit_null=exit_ is None
    return entry,exit_,entry_null,exit_null


def _compose(request,window,joints,cancel=None,locked_plan=None):
    """Fresh motif cells plus exact retained prefix and frozen joint anchors."""
    _check(cancel);a,b=_pair(window);unit=window['parameters']['unit_ticks'];technique=window['technique']
    by_id=m.indexed(request['actual_layout']['notes']);motif=[by_id[i] for i in window['context']['motif_note_ids']]
    parents={n['id']:service.parent_ref(request,n['id']) for n in motif}
    seed=_seed(request,window,joints,locked_plan);rng=random.Random(seed)
    scale=melody._scale(window['key_context']);notes=[];operations=[];budget=request['parameters']['max_notes']
    entry,exit_,entry_null,exit_null=_joint_endpoints(window,joints)
    if unit==10 and any(ep[k]%10 for ep in (entry,exit_) if ep for k in ('start_tick','duration_tick')):
        _fail('OUTPUT_TIME_UNREPRESENTABLE','共同条件与明确10tick作曲单位不兼容，不静默改动计划。')
    def emit(parent,onset,duration,pitch,preserve=False):
        _check(cancel)
        if len(notes)>=budget:
            _fail('CONNECTION_GENERATION_FAILED','本窗实际音符预算耗尽，不截短或挪用兄弟预算。')
        if preserve:
            note=copy.deepcopy(parent)
        else:
            note=dict(copy.deepcopy(parent),id=m.digest('emoblocks.connection-note.v1',[window['id'],seed,len(notes)]),
                pitch=pitch,start_tick=onset,duration_tick=duration,slice=None,
                lineage=list(dict.fromkeys(parent['lineage']+[parent['id']])))
        notes.append(note)
        operations.append(dict(operation='connection-motif-cell',input_note_id=parent['id'],output_note_id=note['id'],
            parent_ref=copy.deepcopy(parents[parent['id']]),rule='preserve' if preserve else technique,
            from_pitch=parent['pitch'],to_pitch=note['pitch'],start_tick=note['start_tick'],duration_tick=note['duration_tick']))
    prefix=[n for n in window['original_notes'] if _support(n)['end_tick']<=(a+b)/2] if technique=='retain_develop' else []
    for n in prefix:
        emit(n,n['start_tick'],n['duration_tick'],n['pitch'],True)
    if entry and prefix:
        if {k:prefix[0][k] for k in ('pitch','start_tick','duration_tick')}!=entry:
            _fail('PROTECTION_CONFLICT','共同入口不能改变必须原样保留的前段。')
    elif entry:
        emit(motif[0],entry['start_tick'],entry['duration_tick'],entry['pitch'])
    if exit_:
        emit(motif[-1],exit_['start_tick'],exit_['duration_tick'],exit_['pitch'])
    low=a+(b-a+1)//2 if prefix or technique=='retain_develop' else a
    low=max(low,entry['start_tick']+entry['duration_tick'] if entry else a+unit if entry_null else a)
    low=((low+unit-1)//unit)*unit if unit==10 else low
    rest=max(1,min(120,(b-a)//8)) if technique=='breath_close' else unit if exit_null else 0
    if unit==10:rest=((rest+9)//10)*10
    high=min(b-rest,exit_['start_tick'] if exit_ else b)
    if technique=='density_shift':
        target=len(window['original_notes'])+1
        if target>budget:target=max(2,len(window['original_notes'])//2)
        if target==len(window['original_notes']):target+=1
        target=max(2,target)
    elif technique=='motif_reply':target=max(3,min(8,(b-a)//max(120,unit)))
    else:target=max(2,len(prefix)+2,min(8,(b-a)//max(240,unit)))
    remaining=target-len(notes)
    if remaining<0 or high-low<remaining*unit:
        _fail('CONNECTION_GENERATION_FAILED','冻结窗口不足以容纳真实发展及共同端点。')
    if remaining:
        cells=(high-low)//unit
        # Integer allocation for new cells is explicit composition, not output
        # rounding or rewriting any captured input onset/duration.
        weights=[max(1,min(960,motif[i%len(motif)]['duration_tick']//unit)) for i in range(remaining)]
        widths=[1]*remaining;spare=cells-remaining;total=sum(weights)
        for i in range(remaining):widths[i]+=spare*weights[i]//total
        for i in range(cells-sum(widths)):widths[i%remaining]+=1
        cursor=low;prior=len(notes)
        for i,width in enumerate(widths):
            parent=motif[(prior+i)%len(motif)]
            degree=melody._degree(scale,parent['pitch'])
            if technique=='motif_reply':step=(0,1,-1,2)[i%4]
            elif technique=='density_shift':step=(0,1,0,-1)[i%4]
            elif technique=='breath_close':step=-min(2,i)
            else:step=(0,1,-1)[i%3]
            # A small seeded sequence choice develops the captured contour.
            if i and i%3==0:step+=rng.choice((-1,1))
            pitch=scale[max(0,min(len(scale)-1,degree+step))]
            if technique=='diatonic_guide' and window['context']['right']:
                right=window['context']['right']['pitch']
                if i==remaining-1 and exit_ is None:
                    pitch=min(scale,key=lambda p:(abs(p-right),abs(p-parent['pitch']),p))
                if not notes:
                    last_pitch=exit_['pitch'] if exit_ else min(scale,key=lambda p:(abs(p-right),p))
                    eligible=[p for p in scale if abs(p-right)>=abs(last_pitch-right)]
                    pitch=min(eligible,key=lambda p:(abs(p-parent['pitch']),p))
            duration=width*unit
            if technique in ('motif_reply','density_shift') and width>=4:
                duration-=unit*min(6,max(1,width//8))
            emit(parent,cursor,duration,pitch)
            cursor+=width*unit
    paired=sorted(zip(notes,operations),key=lambda p:(p[0]['start_tick'],p[0]['id']))
    notes=[p[0] for p in paired];operations=[p[1] for p in paired]
    _verify_music(request,window,joints,notes,operations)
    return notes,operations,seed


def _verify_music(request,window,joints,notes,operations):
    if len(notes)<2 or _music(notes)==_music(window['original_notes']):
        _fail('CONNECTION_GENERATION_FAILED','连接必须有至少两次真实发声及实际pitch/time发展。')
    m.indexed(notes)
    if any(n['start_tick']<window['start_tick'] or _support(n)['end_tick']>window['end_tick'] for n in notes):
        _fail('PROTECTION_CONFLICT','实际连接音符越出窗口。')
    if any(_support(a)['end_tick']>b['start_tick'] for a,b in zip(notes,notes[1:])):
        _fail('CONNECTION_GENERATION_FAILED','连接不是单旋律。')
    if any(m.intersects(_support(n),r) for n in notes for r in _forbidden(request)):
        _fail('PROTECTION_CONFLICT','实际连接发声或延音进入独立保护。')
    key=window['key_context'];degrees=(0,2,4,5,7,9,11) if key['mode']=='major' else (0,2,3,5,7,8,10)
    tech=window['technique'];original=window['original_notes']
    if tech in ('diatonic_guide','motif_reply','density_shift') and any((n['pitch']-key['tonic'])%12 not in degrees for n in notes):
        _fail('CONNECTION_GENERATION_FAILED','调内技术产生了调外音高。')
    if tech=='diatonic_guide' and window['context']['right']:
        right=window['context']['right']['pitch']
        if abs(notes[-1]['pitch']-right)>abs(notes[0]['pitch']-right):
            _fail('CONNECTION_GENERATION_FAILED','调内导向没有接近实际右入口。')
    if tech=='motif_reply' and (len(notes)<3 or len({n['pitch'] for n in notes})<2 or len({o['input_note_id'] for o in operations if o['rule']!='preserve'})<2):
        _fail('CONNECTION_GENERATION_FAILED','回应缺少多个父动机与不同音高。')
    if tech=='density_shift' and len(notes)==len(original):
        _fail('CONNECTION_GENERATION_FAILED','疏密技术未改变实际攻击数量。')
    if tech=='retain_develop':
        mid=window['start_tick']+(window['end_tick']-window['start_tick'])//2
        for n in original:
            if _support(n)['end_tick']<=mid and n not in notes:
                _fail('PROTECTION_CONFLICT','保留展开改变了原窗前段。')
        if not any(o['rule']!='preserve' and o['start_tick']>=mid for o in operations) or _music([n for n in notes if n['start_tick']>=mid])==_music([n for n in original if n['start_tick']>=mid]):
            _fail('CONNECTION_GENERATION_FAILED','后半没有实际发展。')
    if tech=='breath_close' and _support(notes[-1])['end_tick']>window['end_tick']-max(1,min(120,(window['end_tick']-window['start_tick'])//8)):
        _fail('CONNECTION_GENERATION_FAILED','收束缺少真实句尾休止。')
    entry,exit_,entry_null,exit_null=_joint_endpoints(window,joints)
    for spec,n in ((entry,notes[0]),(exit_,notes[-1])):
        if spec and spec!={k:n[k] for k in ('pitch','start_tick','duration_tick')}:
            _fail('PROTECTION_CONFLICT','实际连接没有兑现共同端点。')
    if entry_null and notes[0]['start_tick']<=window['start_tick'] or exit_null and _support(notes[-1])['end_tick']>=window['end_tick']:
        _fail('PROTECTION_CONFLICT','共同边界声明休止但实际仍发声。')


def _generation(request,plan,window,operations):
    return service.generation_data(request,plan,window,operations)


def _joints(windows):
    ordered=sorted(windows,key=_pair);result=[]
    for left,right in zip(ordered,ordered[1:]):
        if left['end_tick']!=right['start_tick']:continue
        left_scale=melody._scale(left['key_context']);right_scale=melody._scale(right['key_context'])
        common=sorted(set(left_scale)&set(right_scale))
        pitch=min(common,key=lambda p:(abs(p-64),p)) if common else 60
        duration=min(120,(left['end_tick']-left['start_tick'])//4,(right['end_tick']-right['start_tick'])//4)
        unit=max(left['parameters']['unit_ticks'],right['parameters']['unit_ticks']);duration=max(unit,duration//unit*unit)
        exit_=None if left['technique']=='breath_close' else dict(pitch=pitch,start_tick=left['end_tick']-duration,duration_tick=duration)
        prefix=[n for n in right['original_notes'] if _support(n)['end_tick']<=right['start_tick']+(right['end_tick']-right['start_tick'])//2]
        entry=({k:prefix[0][k] for k in ('pitch','start_tick','duration_tick')} if right['technique']=='retain_develop' and prefix else dict(pitch=pitch,start_tick=right['start_tick'],duration_tick=duration))
        result.append(dict(id=m.digest('emoblocks.connection-joint.v1',[left['id'],right['id']]),left_connection_id=left['id'],right_connection_id=right['id'],
            tick=left['end_tick'],relation='joint-motif-arrival-entry',left_endpoint=exit_,right_endpoint=entry))
    return result


def _analyze(request,tick):
    notes=request['actual_layout']['notes'];left=[n for n in notes if _support(n)['end_tick']<=tick];right=[n for n in notes if n['start_tick']>=tick]
    a=left[-1] if left else None;b=right[0] if right else None
    leap=abs(a['pitch']-b['pitch']) if a and b else 0
    rhythm=abs(math.log2(a['duration_tick']/b['duration_tick'])) if a and b else 0.
    lcount=sum(tick-960<=n['start_tick']<tick for n in notes);rcount=sum(tick<=n['start_tick']<tick+960 for n in notes)
    density=abs(lcount-rcount)/max(1,lcount,rcount)
    base=request['actual_layout']['base_project'];places=base['placements']
    lp=next((p for p in places if p['start_tick']<tick<=p['start_tick']+p['length_ticks']),None)
    rp=next((p for p in places if p['start_tick']<=tick<p['start_tick']+p['length_ticks']),None)
    emo=bool(lp and rp and lp['emotion']!=rp['emotion'])
    points=[dict(time=p['tick'],level=p['level']) for p in base['intensity_points']]
    trend=abs(intensity_curve.evaluate(points,max(0,tick-480))-intensity_curve.evaluate(points,min(base['total_ticks'],tick+480)))
    keys=[_captured_key(request,[n]) for n in (a,b) if n]
    key_change=len(keys)==2 and (keys[0]['tonic'],keys[0]['mode'])!=(keys[1]['tonic'],keys[1]['mode'])
    motion=max(0,leap-7)/12 + .2*rhythm + .15*key_change
    cost=.7*max(0,leap-7)/12+.14*rhythm+.08*density+.1*key_change+.06*emo*min(1,motion)+.04*trend*min(1,motion)
    return dict(tick=tick,left_note_id=a['id'] if a else None,right_note_id=b['id'] if b else None,
        baseline_cost=round(cost,8),pitch_leap=leap,rhythm_contrast=rhythm,density_contrast=density,
        emotion_change=emo,intensity_trend=trend,key_change=key_change)


def plan_connection_blocks(request,should_cancel=None,on_progress=None):
    _validate_request(request);_check(should_cancel);_progress(on_progress,'分析真实P5拼接的动机、入口、密度及保护外空间。')
    layout=request['actual_layout'];params=request['parameters'];seams={0,layout['total_ticks']}
    for p in layout['base_project']['placements']:
        seams.update((p['start_tick'],p['start_tick']+p['length_ticks']))
    for overlay in layout['bridge_overlays']:
        seams.update(_pair(overlay['range']))
    # An internal fourbeat grid line alone is never a seam. A strong actual
    # interval discontinuity can be considered independently of that grid.
    seams.update(b['start_tick'] for a,b in zip(layout['notes'],layout['notes'][1:]) if abs(a['pitch']-b['pitch'])>10)
    analyses=[]
    for tick in sorted(seams):
        _check(should_cancel);analyses.append(_analyze(request,tick))
    needs=[a for a in analyses if a['baseline_cost']>.22]
    assessments=copy.deepcopy(analyses);candidates=[];tested=0;termination='EXHAUSTED'
    if params['policy']=='none' or not needs:
        none_reason='NOT_NEEDED';termination='POLICY_NONE' if params['policy']=='none' else 'NOT_NEEDED'
    else:
        writable=_writable_regions(request)
        points={0,layout['total_ticks']}
        points.update(v for n in layout['notes'] for v in _pair(_support(n)))
        points.update(v for r in _forbidden(request) for v in _pair(r));points=sorted(points)
        seen=set()
        for analysis in needs:
            tick=analysis['tick'];_check(should_cancel)
            starts=[x for x in points if tick-params['max_window_ticks']<=x<=tick]
            ends=[x for x in points if tick<=x<=tick+params['max_window_ticks']]
            # Include one-sided windows bordering a protected bridge or rest.
            for a in starts:
                for b in ends:
                    _check(should_cancel)
                    if not params['min_window_ticks']<=b-a<=params['max_window_ticks']:continue
                    region=_range(a,b)
                    if not any(r['start_tick']<=a<b<=r['end_tick'] for r in writable):continue
                    if (a,b) in seen:continue
                    seen.add((a,b));_check(should_cancel)
                    if tested>=params['max_window_tests']:
                        termination='WINDOW_BUDGET';break
                    tested+=1
                    if not _legal(request,region):continue
                    preference=('density_shift','motif_reply','diatonic_guide','retain_develop','breath_close') if analysis['density_contrast']>.5 else TECHNIQUES
                    for technique in preference:
                        _check(should_cancel)
                        try:
                            w=_window(request,region,technique)
                            notes,ops,_=_compose(request,w,[],should_cancel)
                        except m.ProjectError as exc:
                            if exc.code=='CANCELLED':raise
                            if exc.code not in ('EMPTY_MATERIAL','CONNECTION_GENERATION_FAILED','PROTECTION_CONFLICT'):raise
                            continue
                        benefit=analysis['baseline_cost']*.8-.06-.02*(b-a)/1920
                        if benefit>.03:
                            candidates.append(dict(window=w,benefit=round(benefit,8)))
                            assessments.append(dict(range=region,technique=technique,baseline_cost=analysis['baseline_cost'],
                                expected_connection_cost=round(analysis['baseline_cost']-benefit,8),benefit=round(benefit,8),
                                actual_music_differs=_music(notes)!=_music(w['original_notes']),reason='有限实际动机试作通过发展规则；听感待独立验收。'))
                        break
                if termination=='WINDOW_BUDGET':break
            if termination=='WINDOW_BUDGET':break
        none_reason='NO_LEGAL_WINDOW'
    # Global mutually exclusive allocation. Avoid a greedy early window
    # occupying a better later connection; equal scores prefer less rewriting.
    candidates.sort(key=lambda c:(c['window']['end_tick'],c['window']['start_tick'],c['window']['technique']))
    states={(0,0):(0.,[])}
    def rank(value):
        score,ws=value
        return (-round(score,8),len(ws),sum(w['end_tick']-w['start_tick'] for w in ws),tuple((w['start_tick'],w['end_tick'],w['technique']) for w in ws))
    for i,c in enumerate(candidates,1):
        _check(should_cancel);w=c['window']
        prev=next((j for j in range(i-1,0,-1) if candidates[j-1]['window']['end_tick']<=w['start_tick']),0)
        for count in range(params['max_windows']+1):
            options=[states.get((i-1,count),(0.,[]))]
            if count:
                old=states.get((prev,count-1),(0.,[]));options.append((old[0]+c['benefit'],old[1]+[w]))
            states[i,count]=min(options,key=rank)
    chosen=min((states.get((len(candidates),k),(0.,[])) for k in range(params['max_windows']+1)),key=rank)[1]
    chosen=sorted(chosen,key=_pair)
    # Rebind contexts after allocation, then jointly freeze endpoints. If a
    # joint makes a technique impossible, drop that window and redo contexts.
    while chosen:
        _check(should_cancel)
        rebound=[];bad=None
        for w in chosen:
            try:rebound.append(_window(request,_range(*_pair(w)),w['technique'],chosen))
            except m.ProjectError as exc:
                if exc.code!='EMPTY_MATERIAL':raise
                bad=w['id'];break
        if bad is not None:
            chosen=[w for w in chosen if w['id']!=bad];continue
        chosen=rebound
        joints=_joints(chosen);bad=None
        for w in chosen:
            try:_compose(request,w,joints,should_cancel)
            except m.ProjectError as exc:
                if exc.code=='CANCELLED':raise
                if exc.code not in ('EMPTY_MATERIAL','CONNECTION_GENERATION_FAILED','PROTECTION_CONFLICT'):raise
                bad=w['id'];break
        if bad is None:break
        chosen=[w for w in chosen if w['id']!=bad]
    if not chosen and candidates:
        # A mutually dependent batch can fail while its independently checked
        # single windows are valid. Do not misreport that as no legal window.
        chosen=[min(candidates,key=lambda c:(-c['benefit'],c['window']['end_tick']-c['window']['start_tick'],_pair(c['window'])))['window']]
        joints=[]
    if not chosen and termination=='WINDOW_BUDGET':
        _fail('SEARCH_BUDGET_EXHAUSTED','有限规划预算耗尽，尚未证明不存在合法有收益连接。')
    if not chosen:joints=[]
    reasons=[_error('SELECTED' if chosen else none_reason,
        '根据实际音乐收益分配保护外连接，窗口统一认证后生成。' if chosen else '实际音乐已成立，保留原拼接。' if none_reason=='NOT_NEEDED' else '真实关系需要连接，但已检查的完整音符、保护及发展条件无合法窗口。')]
    if termination=='WINDOW_BUDGET':reasons.append(_error('SEARCH_BUDGET_EXHAUSTED','搜索到达预算，仅提交已验证的合法提案。'))
    _progress(on_progress,'实际连接分析完成；等待后端原子认证完整计划。')
    return dict(schema='emoblocks.connection-proposal.v1',spec_rev=m.SPEC_REV,contract_rev=CONTRACT_REV,
        request_fingerprint=_request_hash(request),decision='selected' if chosen else 'none',none_reason=None if chosen else none_reason,
        windows=chosen,reasons=reasons,assessments=assessments,joint_boundary_conditions=joints,
        search=dict(tested_windows=tested,termination=termination))


def _validate_plan(request,plan):
    service.validate_request(request)
    service.validate_plan(request,plan)


def _header(request,plan,w):
    return service.result_header(request,plan,w['id'])


def generate_connection_blocks(request,plan,actual_layout,should_cancel=None,on_progress=None,on_result=None):
    _validate_plan(request,plan)
    if actual_layout!=request['actual_layout']:_fail('STALE_SNAPSHOT','生成器收到另一份实际布局。')
    _progress(on_progress,'已收到完整认证连接计划；从实际P5发声构作保护外音乐。')
    results=[];failure=None;status='SUCCEEDED'
    for w in plan['windows']:
        if failure is None:
            try:
                notes,ops,seed=_compose(request,w,plan['joint_boundary_conditions'],should_cancel,locked_plan=plan)
                row=dict(_header(request,plan,w),status='READY',notes=notes,operations=ops,
                    generation=_generation(request,plan,w,ops),
                    content_fingerprint=service.content_fingerprint(_range(*_pair(w)),notes),error=None)
                service.validate_result(request,plan,row)
            except m.ProjectError as exc:
                status='CANCELLED' if exc.code=='CANCELLED' else 'FAILED';failure=_error(exc.code,str(exc))
                row=dict(_header(request,plan,w),status=status,notes=[],operations=[],generation=None,content_fingerprint=None,error=copy.deepcopy(failure))
        else:
            row=dict(_header(request,plan,w),status=status,notes=[],operations=[],generation=None,content_fingerprint=None,
                error=dict(failure,details=dict(not_generated=True)))
        results.append(row)
        if on_result is not None:on_result(copy.deepcopy(row))
        _progress(on_progress,'已产出实际连接结果，等待独立认证。' if row['status']=='READY' else '连接生成已停止，原桥和先前实际结果保持。')
    if failure is None:
        try:_check(should_cancel)
        except m.ProjectError as exc:status='CANCELLED';failure=_error(exc.code,str(exc))
    return dict(schema='emoblocks.connection-raw-outcome.v1',spec_rev=m.SPEC_REV,contract_rev=CONTRACT_REV,
        request_fingerprint=_request_hash(request),plan_id=plan['id'],plan_version=plan['version'],status=status,results=results,error=failure)


plan = plan_connection_blocks
generate = generate_connection_blocks
