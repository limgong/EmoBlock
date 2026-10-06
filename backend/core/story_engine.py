"""Offline, explainable short-block planner. Seconds at the boundary, ticks internally."""
import copy
import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path
import flow_engine as flow
import assembly

music = flow.music
PPQ = music.PPQ
SCHEMA = 'emoblocks.story.v1'
ROLES = ('auto', 'main', 'secondary', 'climax', 'ending')


def new_project():
    return dict(schema=SCHEMA, sources=[], duration=48., bpm=120., curve=[], anchors=[], overrides=[])


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(label + '超出范围。')
    return value


def import_source(path, track=0, role='auto', policy='reject', assembly_mode=False):
    source = music.load_source(path)
    if not 0 <= track < len(source.tracks):
        raise ValueError('请选择有效旋律音轨。')
    if role not in ROLES or policy not in ('reject', 'upper', 'lower'):
        raise ValueError('无效角色或同时起音处理方式。')
    raw = sorted(source.tracks[track].notes, key=lambda n: (n.start, n.pitch))
    music._check_notes(raw)
    groups = {}
    for n in raw:
        groups.setdefault(n.start, []).append(n)
    if policy == 'reject' and any(len(ns) > 1 for ns in groups.values()):
        raise ValueError('轨道含同时起音：请显式选择高音或低音声部，或改选单旋律轨。')
    ns = [min(ns, key=lambda n: n.pitch) if policy == 'lower' else max(ns, key=lambda n: n.pitch) for ns in groups.values()]
    origin = ns[0].start
    notes = []
    for i, n in enumerate(ns):
        end = min(n.start+n.duration, ns[i+1].start) if i+1 < len(ns) else n.start+n.duration
        notes.append(dict(pitch=n.pitch, start=n.start-origin, duration=end-n.start, velocity=n.velocity))
    length = max(n['start']+n['duration'] for n in notes)
    if length > PPQ*256 and not assembly_mode:
        raise ValueError('首版每段输入最多 256 拍，请截取主要旋律。')
    tonic, mode, confidence = music.infer_key([music.Note(**n) for n in notes])
    return dict(id=flow.structure.uid(), name=Path(path).stem+' · '+source.tracks[track].name,
                notes=notes, ticks=length, bpm=source.bpm, role=role, tonic=tonic, mode=mode,
                source=dict(path=str(path), sha256=source.sha256, track=track),
                warnings=source.warnings+['已移除开头空白；交叠音符截至下一起音，按项目速度解释节奏。'], confidence=confidence)


def validate(project, require_source=True):
    if assembly.is_project(project):return assembly.validate(project,require_source)
    return _validate_legacy(project,require_source)


def _validate_legacy(project, require_source=True, assembled=False):
    if not isinstance(project, dict) or project.get('schema') != SCHEMA:
        raise ValueError('简要工程格式无效。')
    duration = number(project['duration'], 1e-6 if assembled else 4, float('inf') if assembled else 480, '作品时长')
    number(project['bpm'], 40, 220, '速度')
    sources = project['sources']
    if not isinstance(sources, list) or (len(sources) > 12 and not assembled) or (require_source and not sources):
        raise ValueError('请提供 1–12 段旋律。')
    ids = set()
    for s in sources:
        if s['id'] in ids or s['role'] not in ROLES:
            raise ValueError('素材 ID 重复或角色无效。')
        ids.add(s['id'])
        number(s['ticks'], 1, float('inf') if assembled else PPQ*256, '素材长度')
        if type(s['tonic']) is not int or not 0 <= s['tonic'] <= 11 or s['mode'] not in ('major', 'minor'):
            raise ValueError('素材调性无效。')
        ns = [music.Note(**n) for n in s['notes']]
        if ns or not assembled:music._check_notes(ns)
        last = 0
        for n in ns:
            if any(type(v) is not int for v in (n.start, n.duration, n.pitch, n.velocity)) or n.start < last or n.start+n.duration > s['ticks']:
                raise ValueError('素材音符时间或单声部顺序无效。')
            last = n.start+n.duration
    for key in ('curve', 'anchors', 'overrides'):
        if not isinstance(project[key], list) or (len(project[key]) > 256 and not assembled):
            raise ValueError('情绪或编辑记录过多。')
    for key in ('curve', 'overrides'):
        previous = 0
        for v in sorted(project[key], key=lambda v: v['start']):
            number(v['start'], 0, duration, '区间起点');number(v['end'], 0, duration, '区间终点')
            if v['start'] < previous-1e-8 or v['end']-v['start'] < (1e-8 if assembled else .1-1e-8):
                raise ValueError('同类区间不能重叠，长度至少 0.1 秒。')
            previous = v['end']
            expression(v)
            if v.get('source_id') and v['source_id'] not in ids:
                raise ValueError('区间引用了不存在的旋律。')
    previous = -1
    for a in sorted(project['anchors'], key=lambda a: a['time']):
        number(a['time'], 0, duration-(1e-8 if assembled else .1), '锚点时间')
        number(a.get('hold', 2.), 1e-8 if assembled else .1, float('inf') if assembled else (6 if a.get('auto_peak') else 4), '锚点保持时间')
        if a['time'] < previous-1e-8 or a['time']+a.get('hold', 2.) > duration+1e-8:
            raise ValueError('锚点保持区间互相冲突或超出作品结尾，请调整时间/保持时长。')
        previous = a['time']+a.get('hold', 2.)
        expression(a)
        if a.get('source_id') and a['source_id'] not in ids:
            raise ValueError('锚点旋律不存在。')
        for o in project['overrides']:
            if o['start'] < previous and o['end'] > a['time']:
                raise ValueError('普通块编辑不能覆盖固定锚点，请直接修改锚点。')
    return project


import intensity_curve


def expression(v):
    if v['emotion'] not in music.EMOTIONS:
        raise ValueError('未知情绪种类。')
    number(v.get('level', .5), 0, 1, '情绪程度')
    number(v.get('end_level', v.get('level', .5)), 0, 1, '结束程度')


def state_at(project,seconds):
    state=raw_state_at(project,seconds)
    auto_anchor=any(a.get('auto_peak') and a['time']<=seconds<a['time']+a['hold'] for a in project['anchors'])
    if project.get('continuous_intensity') and (not state.get('anchor') or auto_anchor) and not any(v['start']<=seconds<v['end'] for v in project['overrides']):
        state['level']=intensity_curve.level_at(project,seconds)
    return state


def raw_state_at(project, seconds):
    for a in project['anchors']:
        if a['time'] <= seconds < a['time']+a.get('hold', 2.):
            fraction=(seconds-a['time'])/a.get('hold',2.)
            return dict(emotion=a['emotion'], level=a['level']+(a.get('end_level',a['level'])-a['level'])*fraction,
                        specified=True, source_id=a.get('source_id'), anchor=True,original_only=a.get('original_only',False))
    for key in ('overrides', 'curve'):
        for v in project[key]:
            if v['start'] <= seconds < v['end']:
                fraction=(seconds-v['start'])/(v['end']-v['start'])
                return dict(emotion=v['emotion'], level=v['level']+(v.get('end_level',v['level'])-v['level'])*fraction,
                            specified=True, source_id=v.get('source_id'), anchor=False)
    # Blank regions inherit/interpolate neighboring requests; categories switch halfway.
    points=[(0., 'calm', .25)]
    for v in project['curve']:
        points += [(v['start'], v['emotion'], v['level']), (v['end'], v['emotion'], v.get('end_level',v['level']))]
    for a in project['anchors']:
        points += [(a['time'], a['emotion'], a['level']), (a['time']+a.get('hold',2.), a['emotion'], a['level'])]
    points.sort(key=lambda x:x[0])
    left=max((p for p in points if p[0]<=seconds),key=lambda p:p[0],default=points[0])
    right=min((p for p in points if p[0]>seconds),key=lambda p:p[0],default=left)
    f=0 if right[0]==left[0] else (seconds-left[0])/(right[0]-left[0])
    return dict(emotion=(left if f<.5 else right)[1], level=left[2]+(right[2]-left[2])*f, specified=False, anchor=False)


def develop(project):
    result=[]
    for source in project['sources']:
        ns=source['notes'];length=source['ticks']
        span=max((n['pitch'] for n in ns),default=60)-min((n['pitch'] for n in ns),default=60)
        density=len(ns)/max(1,length/PPQ)
        energy=min(1, .3*density+.4*span/24)
        role=source['role'] if source['role']!='auto' else ('climax' if energy>.7 else 'ending' if density<.6 else 'main')
        scale=[p for p in range(12,120) if (p-source['tonic'])%12 in ([0,2,4,5,7,9,11] if source['mode']=='major' else [0,2,3,5,7,8,10])]
        snap=lambda p:min(scale,key=lambda k:abs(k-p))
        phrase_edges=[0]
        previous_end=0
        for n in ns:
            if n['start']-phrase_edges[-1]>=8*PPQ or (n['start']-previous_end>=PPQ//2 and n['start']-phrase_edges[-1]>=2*PPQ):
                phrase_edges.append(n['start'])
            previous_end=n['start']+n['duration']
        phrase_edges.append(length)
        for version in ('original','variant','answer','secondary'):
            notes=copy.deepcopy(ns)
            for i,n in enumerate(notes):
                if version=='variant' and n['start']>=length*.5:
                    n['pitch']=snap(n['pitch']+(2 if i%2 else -2))
                elif version=='answer':
                    n['pitch']=snap(ns[0]['pitch']-(n['pitch']-ns[0]['pitch'])+2)
                elif version=='secondary':
                    n['pitch']=snap(n['pitch']+4-(i%3)*2)
                    n['duration']=max(10,round(n['duration']*.8))
            result.append(dict(id=source['id']+':'+version, source_id=source['id'],name=source['name']+' / '+version,
                               version=version, notes=notes,ticks=length, role=role,energy=energy,
                               tonic=source['tonic'],mode=source['mode'],
                               phrases=[dict(id=source['id']+':p'+str(i),start=a,end=b,order=i) for i,(a,b) in enumerate(zip(phrase_edges,phrase_edges[1:]))],
                               method={'original':'原节奏与旋律','variant':'后半句调内邻音变化','answer':'动机轮廓反向回答','secondary':'保留节奏动机的调内移位与短奏'}[version]))
    return result


def block_grid(project):
    """Four beats per block from song origin; hard deadlines only split locally."""
    rate=project['bpm']*PPQ/60
    tick=lambda s:round(s*rate/10)*10
    total=tick(project['duration'])
    edges=set(range(0,total,music.BAR))|{total}
    for a in project['anchors']:edges.update((tick(a['time']),tick(a['time']+a.get('hold',2.))))
    return sorted(edges)


def automatic_memory_project(project):
    """Migrate the quick editor to derived memory without losing legacy data."""
    if assembly.is_project(project):return copy.deepcopy(project)
    result=copy.deepcopy(project)
    if result.get('anchors'):
        result.setdefault('legacy_memory_anchors',copy.deepcopy(result['anchors']))
    result.update(anchors=[],auto_peak_memory=True,memory_mode='automatic',continuous_intensity=True)
    return result


def automatic_peak_anchor(project):
    """Derived from the current curve; never overwrite user anchors or overrides."""
    if assembly.is_project(project):return automatic_peak_anchor(assembly.render_project(project))
    if not project.get('auto_peak_memory',False) or not project['curve'] or not project['sources']:return None
    if project.get('assembly_mode'):
        points=intensity_curve.controls(project);peak=max(points,key=lambda p:(p['level'],-p['time']))
        time=min(project['duration']-1e-8,peak['time']);region=next(v for v in project['curve'] if v['start']<=time<v['end'])
        rate=project['bpm']*PPQ/60;asset=next(s for s in project['sources'] if s['id']==region['source_id'])
        leaf=next(p for p in assembly.leaves(asset) if p['start']/rate<=time-region['start']<p['end']/rate)
        bar=240/project['bpm'];origin=region['start']+leaf['start']/rate
        start=origin+math.floor((time-origin)/bar)*bar;end=min(region['start']+leaf['end']/rate,start+bar)
        return dict(time=start,hold=end-start,emotion=region['emotion'],level=peak['level'],source_id=region['source_id'],
                    use_id=region['use_id'],original_only=True,auto_peak=True,memory_time=peak['time'])
    if project.get('continuous_intensity'):
        points=intensity_curve.controls(project);peak=max(points,key=lambda p:(p['level'],-p['time']))
        bar=240/project['bpm'];start=max(0,peak['time']-bar/2);end=min(project['duration'],start+bar)
        # Partial final block uses its actual midpoint.
        start=math.floor((peak['time']+1e-8)/bar)*bar;end=min(project['duration'],start+bar)
        region=next(v for v in project['curve'] if v['start']<=peak['time']<v['end'])
        if any(a['time']<end and a['time']+a.get('hold',2.)>start for a in project['anchors']):return None
        if project.get('memory_mode')!='automatic' and any(v['start']<end and v['end']>start for v in project['overrides']):return None
        source=next((s for s in project['sources'] if s['id']==region.get('source_id')),None)
        source=source or next((s for s in project['sources'] if s['role']=='main'),project['sources'][0])
        return dict(time=start,hold=end-start,emotion=region['emotion'],level=peak['level'],source_id=source['id'],
                    original_only=True,auto_peak=True,memory_time=peak['time'])
    region=max(project['curve'],key=lambda v:(max(v['level'],v.get('end_level',v['level'])),-v['start']))
    bar=240/project['bpm']
    rising=region.get('end_level',region['level'])>region['level']
    grid=[t/(project['bpm']*PPQ/60) for t in range(0,round(project['duration']*project['bpm']*PPQ/60),music.BAR)]
    starts=[t for t in grid if region['start']-1e-8<=t<region['end']-.099999]
    if not starts:return None
    start=starts[-1] if rising else starts[0];end=min(start+bar,region['end'],project['duration'])
    if any(a['time']<end-1e-8 and a['time']+a.get('hold',2.)>start+1e-8 for a in project['anchors']):return None
    if any(v['start']<end-1e-8 and v['end']>start+1e-8 for v in project['overrides']):return None
    source=next((s for s in project['sources'] if s['id']==region.get('source_id')),None)
    if source is None:source=next((s for s in project['sources'] if s['role']=='main'),project['sources'][0])
    delta=region.get('end_level',region['level'])-region['level'];span=region['end']-region['start']
    return dict(time=start,hold=end-start,emotion=region['emotion'],level=region['level']+delta*(start-region['start'])/span,
                end_level=region['level']+delta*(end-region['start'])/span,source_id=source['id'],original_only=True,auto_peak=True)


def plan(project):
    intensity_curve.validate(project)
    validate(project)
    requested_project=copy.deepcopy(project)
    assembled=assembly.is_project(project)
    project=assembly.render_project(project) if assembled else copy.deepcopy(project)
    automatic=automatic_peak_anchor(project)
    if automatic:
        if project.get('memory_mode')=='automatic':
            # Memory wins only inside its current block. Keep the saved overrides
            # untouched so moving the peak restores their previous behavior.
            start=automatic['time'];end=start+automatic['hold'];retained=[]
            for value in project['overrides']:
                for left,right in ((value['start'],min(value['end'],start)),(max(value['start'],end),value['end'])):
                    if right<=left:continue
                    piece=copy.deepcopy(value);span=value['end']-value['start'];delta=value.get('end_level',value['level'])-value['level']
                    piece.update(start=left,end=right,level=value['level']+delta*(left-value['start'])/span,
                                 end_level=value['level']+delta*(right-value['start'])/span)
                    retained.append(piece)
            project['overrides']=retained
        project['anchors'].append(automatic)
    _validate_legacy(project,assembled=assembled)
    requested_anchors=copy.deepcopy(project['anchors'])
    bpm=project['bpm'];rate=bpm*PPQ/60
    tick=(lambda s:round(s*rate)) if assembled else (lambda s:round(s*rate/10)*10)
    project['duration']=tick(project['duration'])/rate
    for key in ('curve','overrides'):
        for v in project[key]:
            v['start']=tick(v['start'])/rate;v['end']=tick(v['end'])/rate
    for a in project['anchors']:
        end=tick(a['time']+a.get('hold',2.))/rate
        a['time']=tick(a['time'])/rate;a['hold']=end-a['time']
    total=tick(project['duration'])
    bank=develop(project)
    originals=[m for m in bank if m['version']=='original']
    main=max(originals,key=lambda m:(m['role']=='main',len(m['notes'])/(1+m['energy'])))
    aligned=project.get('block_aligned',False)
    grid=assembly.generation_edges(requested_project) if assembled else block_grid(project)
    points=set(grid)
    for key in ('curve','overrides'):
        for v in project[key]:points.update((tick(v['start']),tick(v['end'])))
    for a in project['anchors']:points.update((tick(a['time']),tick(a['time']+a.get('hold',2.))))
    # Reserve time BEFORE arrangement, never insert time after anchoring.
    windows=[];warnings=[]
    requests=[dict(a, at=a['time'], hard=True) for a in project['anchors']]
    requests += [dict(v, at=v['start'], hard=False) for v in project['curve'] if v['start']>0]
    requests += [dict(v,at=v['end'],level=v.get('end_level',v['level']),ramp_start=v['start'],hard=False)
                 for v in project['curve'] if abs(v.get('end_level',v['level'])-v['level'])>=.35]
    for request in sorted(requests,key=lambda r:r['at']):
        end=request['at']
        # Measure the gap from the last *requested* state, not our own interpolation.
        # Otherwise anticipating a climax would make its transition budget disappear.
        history=[(0.,dict(emotion='calm',level=.25))]
        for key in ('curve','overrides'):
            for v in project[key]:
                if v['start']<end:
                    at=min(end-1e-7,v['end'])
                    fraction=max(0,min(1,(at-v['start'])/(v['end']-v['start'])))
                    history.append((at,dict(emotion=v['emotion'],level=v['level']+(v.get('end_level',v['level'])-v['level'])*fraction)))
        for a in project['anchors']:
            if a['time']<end:history.append((min(end,a['time']+a.get('hold',2.)),a))
        before=max(history,key=lambda v:v[0])[1]
        if project.get('continuous_intensity'):
            before=state_at(project,max(0,end-1e-7))
            request=dict(request,level=state_at(project,min(project['duration']-1e-7,end+1e-7))['level'])
        if 'ramp_start' in request:before=state_at(project,request['ramp_start']+1e-7)
        gap=abs(request['level']-before['level'])+(.35 if before['emotion']!=request['emotion'] else 0)
        if gap<.35 or end<=0:continue
        boundary=tick(end);wanted=(16 if gap>=.65 else 4)*PPQ
        # A final calm region after resolve is a cadence, not a fresh calm theme.
        terminal=(request.get('emotion')=='calm' and before['emotion']=='resolve'
                  and tick(request.get('end',-1))==total and not request['hard']
                  and 'ramp_start' not in request and max(request['level'],request.get('end_level',request['level']))<.7)
        protected=any(tick(a['time'])<total and tick(a['time']+a.get('hold',2.))>boundary for a in project['anchors'])
        protected=protected or any(tick(v['start'])<total and tick(v['end'])>boundary for v in project['overrides'])
        if terminal and not protected:
            windows.append(dict(start=boundary,end=total,kind='transition_ending',from_state=before,target=request,gap=gap,
                                boundary_seconds=end,direction='after',carrier='calm',protection='terminal-cadence; preserve-climax-and-fixed-points'))
            continue
        candidate_edges=sorted(points|{boundary})
        intervals=list(zip(candidate_edges,candidate_edges[1:]))
        def candidate(side):
            cells=([c for c in intervals if c[1]<=boundary][::-1] if side=='before'
                   else [c for c in intervals if c[0]>=boundary])
            selected=[];cost=0.;cursor=boundary
            carrier=None
            for a,b in cells:
                if (b if side=='before' else a)!=cursor:break
                # Never steal a pinned moment, a manual override, or a previous transition.
                if any(a<w['end'] and b>w['start'] for w in windows):break
                if any(a<tick(v['time']+v.get('hold',2.)) and b>tick(v['time']) for v in project['anchors']):break
                if any(a<tick(v['end']) and b>tick(v['start']) for v in project['overrides']):break
                states=[state_at(project,t/rate) for t in (a+.001,(a+b)/2,b-.001)]
                state=states[1]
                if carrier is None:carrier=state['emotion']
                if state['specified'] and state['emotion']!=carrier:break
                # Give each explicit non-transition phrase its first block to state its theme.
                region=next((v for v in project['curve'] if tick(v['start'])<=a and b<=tick(v['end'])),None)
                if region and carrier!='suspense' and a<tick(region['start'])+music.BAR:
                    break
                specified=[s['level'] for s in states if s['specified']]
                level=max(specified,default=0.)
                # 70% and above is protected core expression, regardless of emotion label.
                if level>=.7:break
                weighted=(b-a)/max(.1,1-level)
                if selected and cost+weighted>wanted:break
                if b-a>wanted:break
                selected.append((a,b));cost+=weighted;cursor=a if side=='before' else b
                if cost>=wanted:break
            if not selected:return None
            return min(a for a,b in selected),max(b for a,b in selected)
        # Suspense is the preferred carrier: preserve the preceding calm theme.
        suspense_carrier=before['emotion']=='suspense' or request['emotion']=='suspense'
        direction=('after' if request['emotion']=='suspense' else 'before') if suspense_carrier else ('after' if before['level']>request['level'] else 'before')
        chosen_window=candidate(direction)
        if chosen_window is None and not suspense_carrier:
            direction='before' if direction=='after' else 'after'
            chosen_window=candidate(direction)
        if chosen_window is None:
            warnings.append('%.2fs 附近主体/固定点受保护，无可用低强度块；仅做边界衔接。'%end);continue
        begin,finish=chosen_window
        carrier=state_at(project,(begin+finish)/2/rate)['emotion']
        # Two boundaries can share a single suspense passage instead of rewriting its neighbors.
        if carrier=='suspense':
            touching=[w for w in windows if w.get('carrier')=='suspense' and (w['end']==begin or w['start']==finish)]
            for prior in touching:
                begin=min(begin,prior['start']);finish=max(finish,prior['end']);windows.remove(prior)
        windows.append(dict(start=begin,end=finish,kind='bridge' if finish-begin>=2*music.BAR else 'transition',
                            from_state=state_at(project,max(0,begin/rate-.01)),target=request,gap=gap,
                            boundary_seconds=end,direction=direction,carrier=carrier,protection='strong-expression-and-theme-opening; suspense-first'))
        points.update((begin,finish))
    edges=sorted(points);rows=[];cursor_by_source={};cycle_by_source={};last_source=None
    for left,right in zip(edges,edges[1:]):
        if right<=left:continue
        # Never rebalance by seconds or split slow-tempo four-beat bars again.
        cuts=[left,right]
        for start,end in zip(cuts,cuts[1:]):
            if end<=start:continue
            seconds=start/rate;state=state_at(project,seconds+1e-7)
            window=next((w for w in windows if w['start']<=start and end<=w['end']),None)
            if window and not state['specified']:
                f=(start-window['start'])/max(1,window['end']-window['start'])
                state=dict(state,emotion=window['from_state']['emotion'] if f<.5 else window['target']['emotion'],
                           level=window['from_state']['level']+(window['target']['level']-window['from_state']['level'])*f)
            binding=next(((a,b,u) for a,b,u in assembly.ranges(requested_project) if a<=start<b),None) if assembled else None
            preferred=binding[2]['id'] if binding else state.get('source_id')
            selection_level=state_at(project,(start+end)/2/rate)['level'] if project.get('continuous_intensity') else state['level']
            targetrole='climax' if selection_level>=.7 else 'ending' if seconds>=project['duration']*.88 else 'main'
            chosen=next((m for m in originals if m['source_id']==preferred),None)
            if chosen is None:
                if last_source and not state.get('anchor') and cursor_by_source.get(last_source,0)>0:
                    chosen=next(m for m in originals if m['source_id']==last_source)
                else:
                    chosen=max(originals,key=lambda m:(m['role']==targetrole, -abs(m['energy']-selection_level), m['id']==main['id']))
            sid=chosen['source_id'];offset=cursor_by_source.get(sid,0);cycle=cycle_by_source.get(sid,0)
            if binding:
                offset=start-binding[0]
                cycle=sum(u['material_id']==binding[2]['material_id'] for a,b,u in assembly.ranges(requested_project) if a<binding[0])
            version=('original','variant','answer','secondary')[cycle%4]
            material=next(m for m in bank if m['source_id']==sid and m['version']==version)
            if state.get('original_only'):material=chosen;cycle=0
            if not assembled and state.get('anchor') and (last_source!=sid or any(tick(a['time'])==start for a in project['anchors'])):
                offset=0;material=chosen
            size=end-start;notes=[];remaining=size;pos=0;source_spans=[]
            # Continue rather than shuffle the source. Short inspirations repeat into a phrase.
            while remaining>0:
                take=min(remaining,material['ticks']-offset)
                source_spans.append(dict(source_id=sid,material_id=material['id'],start=offset,end=offset+take,cycle=cycle,
                                         phrase_ids=[p['id'] for p in material['phrases'] if p['start']<offset+take and p['end']>offset]))
                for note_index,n in enumerate(material['notes']):
                    a=max(offset,n['start']);b=min(offset+take,n['start']+n['duration'])
                    if b>a:
                        notes.append(dict(n,start=pos+a-offset,duration=b-a,
                                          source_note_id=[material['id'],cycle,note_index,start+pos+n['start']-offset],
                                          continuation=a>n['start']))
                pos+=take;remaining-=take;offset+=take
                if offset>=material['ticks']:offset=0;cycle+=1
            cursor_by_source[sid]=offset;cycle_by_source[sid]=cycle;last_source=sid
            final_state=state_at(project,max(seconds,(end-1)/rate))
            if window and not final_state['specified']:
                f=(end-window['start'])/max(1,window['end']-window['start'])
                final_state=dict(final_state,level=window['from_state']['level']+(window['target']['level']-window['from_state']['level'])*f)
            rows.append(dict(id='b'+str(start),start_tick=start,end_tick=end,start_seconds=seconds,end_seconds=end/rate,
                             source_id=sid,material_id=material['id'],source_offset=(cursor_by_source[sid]-size)%material['ticks'],
                             source_spans=source_spans,
                             name=('Bridge' if window and window['kind']=='bridge' else '连接' if window else chosen['name'])+' · '+str(len(rows)+1),
                             kind=window['kind'] if window else 'content',notes=notes,emotion=state['emotion'],level=state['level'],end_level=final_state['level'],
                             pinned=bool(state.get('anchor')),order_policy='source-order; explicit target may interrupt',version=material['version']))
            if binding:
                use=binding[2]
                rows[-1].update(use_id=use['id'],assembly_material_id=use['material_id'],assembly_order=requested_project['uses'].index(use),
                    assembly_sources=[dict(source_id=leaf['origin']['source_id'],block_index=leaf['origin']['block_index'],
                        material_id=leaf['id'],name=leaf['name'],start_tick=max(start,leaf['start']),end_tick=min(end,leaf['end']))
                        for leaf in assembly.leaves(use['material'],binding[0]) if leaf['start']<end and leaf['end']>start])
            if size!=music.BAR and not assembled:warnings.append('%.2f–%.2fs 为固定时间/结尾约束截段（%g 拍）；普通块固定 4 拍，后续拍网格不重排。'%(seconds,end/rate,size/PPQ))
    # Actual neighboring endpoints determine every transition run.
    for w in windows:
        if w['kind']=='transition_ending':
            apply_ending(rows,w,originals)
            continue
        group=[r for r in rows if w['start']<=r['start_tick'] and r['end_tick']<=w['end']]
        left=next((r for r in reversed(rows) if r['end_tick']<=w['start']),None)
        right=next((r for r in rows if r['start_tick']>=w['end']),None)
        lp=left['notes'][-1]['pitch'] if left and left['notes'] else (main['notes'][0]['pitch'] if main['notes'] else 60+main['tonic'])
        rp=right['notes'][0]['pitch'] if right and right['notes'] else lp
        tonic=next(m['tonic'] for m in originals if m['source_id']==(right or group[0])['source_id'])
        mode=next(m['mode'] for m in originals if m['source_id']==(right or group[0])['source_id'])
        scale=[p for p in range(24,109) if (p-tonic)%12 in ([0,2,4,5,7,9,11] if mode=='major' else [0,2,3,5,7,8,10])]
        for index,r in enumerate(group):
            length=r['end_tick']-r['start_tick']
            if len(group)>1 and index==0:
                r['kind']='transition_keep';r['connection_method']='保留正在发展的旋律片段，配器渐变'
                if r['notes']:lp=r['notes'][-1]['pitch']
                continue
            ns=[];step=PPQ//2 if w['target']['level']>.65 else PPQ
            for t in range(0,length,step):
                f=(r['start_tick']+t-w['start'])/max(1,w['end']-w['start']-step)
                pitch=lp+(rp-lp)*min(1,f)
                if w['kind']=='bridge' and t+step<length:pitch+= (0,2,-1,0)[(t//step)%4]
                p=min(scale,key=lambda p:abs(p-pitch))
                ns.append(dict(pitch=p,start=t,duration=min(step,length-t),velocity=80))
            if ns:ns[-1]['pitch']=rp
            r['reference_spans']=r['source_spans'];r['source_spans']=[]
            r['connection_endpoints']=dict(from_pitch=lp,to_pitch=rp,left_entry=left['id'] if left else None,right_entry=right['id'] if right else None)
            r['notes']=ns;r['connection_method']='实际前句末音 → 后句首音；调内导向'+('与经过句展开' if w['kind']=='bridge' else '')
    anchors=[]
    for a,requested in zip(project['anchors'],requested_anchors):
        actual=tick(a['time'])/rate
        row=next(r for r in rows if r['start_tick']==tick(a['time']))
        if not row['pinned'] or row['emotion']!=a['emotion']:
            raise ValueError('锚点量化与区间冲突，未生成；请将时间稍作调整。')
        anchors.append(dict(requested=requested['time'],actual=actual,error_seconds=actual-requested['time'],entry_id=row['id'],
                            auto_peak=bool(a.get('auto_peak')),original_only=bool(a.get('original_only')),
                            **(dict(use_id=row['use_id'],material_id=row['assembly_material_id'],sources=row['assembly_sources']) if assembled else {})))
    return dict(source_catalog=project['sources'],assembly_blocks=[dict(use_id=u['id'],material_id=u['material_id'],name=u['material']['name'],
                     start_tick=a,end_tick=b,start_seconds=a/rate,end_seconds=b/rate,emotion=u['emotion']) for a,b,u in assembly.ranges(requested_project)] if assembled else [],
                schema='emoblocks.story-plan.v1',project=requested_project,materials=bank,blocks=rows,anchors=anchors,
                connection_windows=[dict(start_seconds=w['start']/rate,end_seconds=w['end']/rate,kind=w['kind'],gap=w['gap'],policy='replace-existing-time',
                                         boundary_seconds=w['boundary_seconds'],direction=w['direction'],protection=w['protection']) for w in windows],
                total_ticks=total,bpm=bpm,warnings=list(dict.fromkeys(warnings)),
                main_source_id=main['source_id'],timing_tolerance_seconds=5/rate)


def apply_ending(rows,window,originals):
    """Use existing ending time: echo the outgoing pitch, then settle on the tonic."""
    group=[r for r in rows if window['start']<=r['start_tick']<window['end']]
    left=next((r for r in reversed(rows) if r['end_tick']<=window['start']),None)
    if not group or left is None:return
    source=next(m for m in originals if m['source_id']==left['source_id'])
    lp=left['notes'][-1]['pitch'] if left['notes'] else (source['notes'][0]['pitch'] if source['notes'] else 60+source['tonic'])
    tonic=min((p for p in range(36,85) if p%12==source['tonic']%12),key=lambda p:abs(p-lp))
    scale=[p for p in range(24,109) if (p-source['tonic'])%12 in ([0,2,4,5,7,9,11] if source['mode']=='major' else [0,2,3,5,7,8,10])]
    length=window['end']-window['start'];split=max(10,round(length/2/10)*10)
    events=[]
    for t in range(0,split,PPQ):
        pitch=lp if t==0 else min(scale,key=lambda p:abs(p-(lp+(tonic-lp)*t/split)))
        events.append(dict(pitch=pitch,start=t,duration=min(PPQ,split-t),velocity=80))
    if split<length:events.append(dict(pitch=tonic,start=split,duration=length-split,velocity=65))
    start_level=left['end_level'];end_level=window['target'].get('end_level',window['target']['level'])
    for r in group:
        a=r['start_tick']-window['start'];b=r['end_tick']-window['start'];notes=[]
        for i,n in enumerate(events):
            lo=max(a,n['start']);hi=min(b,n['start']+n['duration'])
            if hi>lo:notes.append(dict(n,start=lo-a,duration=hi-lo,continuation=lo>n['start'],
                                      source_note_id=['ending',window['start'],i],ending_mix=lo/length,
                                      ending_from=left['emotion']))
        r.update(kind='transition_ending',name='过渡＋结尾 · '+str(rows.index(r)+1),notes=notes,
                 source_id=left['source_id'],reference_spans=r['source_spans'],source_spans=[],
                 level=start_level+(end_level-start_level)*a/length,end_level=start_level+(end_level-start_level)*b/length,
                 ending_start=window['start'],ending_length=length,ending_from=left['emotion'],
                 connection_endpoints=dict(from_pitch=lp,to_pitch=tonic,left_entry=left['id'],right_entry=None),
                 connection_method='承接振奋末音与音色 → 力度及节奏渐退 → 主音长音收尾（不增加时长）')


def continuous_melody(planned):
    """Reassemble one musical voice, tying only fragments of the SAME source note."""
    events=[];joined=0
    for row in planned['blocks']:
        length=row['end_tick']-row['start_tick']
        for note in row['notes']:
            event=dict(note,start=row['start_tick']+note['start'],emotion=row['emotion'],
                       level=row['level']+(row['end_level']-row['level'])*note['start']/max(1,length))
            if planned['project'].get('continuous_intensity') and row['kind']!='transition_ending':
                event['level']=state_at(planned['project'],event['start']/(planned['bpm']*PPQ/60))['level']
            previous=events[-1] if events else None
            if (previous and event.get('continuation') and event.get('source_note_id') is not None
                    and previous.get('source_note_id')==event['source_note_id']
                    and previous['pitch']==event['pitch']
                    and previous['start']+previous['duration']==event['start']):
                previous['duration']+=event['duration'];joined+=1
            else:events.append(event)
    return events,joined


def compile_score(planned):
    project=planned['project'];rate=planned['bpm']*PPQ/60;layers={};boundaries=[]
    presets=dict(calm='soft',hope='bell',sad='dark',suspense='pluck',crisis='pluck',resolve='brass')
    def add(name,preset,pitch,start,duration,velocity,volume=22,drum=None):
        start=max(0,round(start/10)*10);duration=min(planned['total_ticks']-start,max(10,round(duration/10)*10))
        if duration<=0:return
        layer=layers.setdefault(name,dict(name=name,preset=preset,volume=volume,pan=0,drum=drum,notes=[]))
        layer['notes'].append(music.Note(max(12,min(119,int(pitch))),start,duration,max(1,min(127,round(velocity)))))
    sources={s['id']:s for s in planned.get('source_catalog',project['sources'])}
    solo=bool(project.get('melody_only',False))
    melody,joined=continuous_melody(planned)
    for note in melody:
        # A sustained note keeps its onset timbre; a block boundary is not a new attack.
        preset='soft' if solo else presets[note['emotion']]
        if not solo and 'ending_mix' in note:
            mix=note['ending_mix'];outgoing=presets[note['ending_from']]
            velocity=55+40*note['level']
            if mix<1:add('melody_'+outgoing,outgoing,note['pitch'],note['start'],note['duration'],velocity*(1-mix))
            if mix>0:add('melody_soft','soft',note['pitch'],note['start'],note['duration'],velocity*mix)
            continue
        add('melody_'+preset,preset,note['pitch'],note['start'],note['duration'],80 if solo else 55+40*note['level'])
    for index,r in enumerate(planned['blocks']):
        start=r['start_tick'];length=r['end_tick']-start;s=sources[r['source_id']]
        if solo:
            if index:boundaries.append(dict(tick=start,from_entry=planned['blocks'][index-1]['id'],to_entry=r['id'],actions=[r.get('connection_method','仅主旋律：沿用内容排布，跨块长音保持连续')]))
            continue
        scale=[0,2,4,5,7,9,11] if s['mode']=='major' else [0,2,3,5,7,8,10]
        chords=[tuple((s['tonic']+scale[(d+k)%7])%12 for k in (0,2,4)) for d in range(7)]
        chord=max(chords,key=lambda c:sum(n['duration'] for n in r['notes'] if n['pitch']%12 in c)+(20 if c==chords[0] else 0))
        if r['kind']=='transition_ending':chord=chords[0]
        voicing=[48+chord[0]]
        for pc in chord[1:]:voicing.append(min(p for p in range(voicing[-1]+1,85) if p%12==pc))
        for offset in range(0,length,PPQ):
            level=r['level']+(r['end_level']-r['level'])*offset/max(1,length)
            if project.get('continuous_intensity') and r['kind']!='transition_ending':level=state_at(project,(start+offset)/rate)['level']
            span=min(PPQ,length-offset);root=voicing[0]
            harmonic_preset='dark' if r['emotion'] in ('sad','suspense') else 'pad'
            for p in voicing:add('harmony_'+harmonic_preset,harmonic_preset,p,start+offset,span,28+20*level,14)
            add('bass','bass',root-12,start+offset,span*.85,40+28*level,20)
            ending_phase=(start+offset-r.get('ending_start',start))/max(1,r.get('ending_length',length))
            if level>.35 and not (r['kind']=='transition_ending' and ending_phase>=.5) and not (r['emotion']=='sad' and (offset//PPQ)%2):
                stride=PPQ//4 if level>.8 else PPQ//2 if level>.6 else PPQ
                for t in range(0,span,stride):
                    if r['emotion']=='suspense' and (offset//PPQ+t//stride)%3==1:continue
                    add('pulse','pluck',voicing[(offset//PPQ+t//stride)%3]+12,start+offset+t,min(stride*.6,span-t),30+25*level,15)
            ending_phase=(start+offset-r.get('ending_start',start))/max(1,r.get('ending_length',length))
            ending_drums=r['kind']=='transition_ending' and ending_phase<.5
            if (r['emotion'] in ('crisis','resolve') or ending_drums) and level>.45:
                beat=(start+offset)//PPQ
                if beat%2==0:add('kick','bass',36,start+offset,min(100,span),50+25*level,20,'bassdrum01.ogg')
                else:add('snare','bass',38,start+offset,min(100,span),45+20*level,15,'snare01.ogg')
                stride=PPQ//4 if r['emotion']=='crisis' and level>.8 else PPQ//2
                for t in range(0,span,stride):add('hat','bass',42,start+offset+t,min(60,span-t),30+20*level,10,'hihat_closed01.ogg')
        if index:
            prev=planned['blocks'][index-1]
            gap=abs(prev['end_level']-r['level'])+(.35 if prev['emotion']!=r['emotion'] else 0)
            actions=[r.get('connection_method','小落差：伴奏力度交接与末拍导向' if gap<.35 else '边界配器交接')]
            # Tail ornament on accompaniment only; no time insertion.
            if prev['notes'] and r['notes']:
                add('handoff','soft',r['notes'][0]['pitch'],max(prev['start_tick'],start-PPQ//2),min(PPQ//2,start-prev['start_tick']),35,12)
            boundaries.append(dict(tick=start,from_entry=prev['id'],to_entry=r['id'],actions=actions))
    blocks=[dict(entry_id=r['id'],name=r['name'],kind=r['kind'],start_seconds=r['start_seconds'],end_seconds=r['end_seconds'],
                 emotion=r['emotion'],intensity_start=r['level'],intensity_end=r['end_level']) for r in planned['blocks']]
    if project.get('continuous_intensity'):
        points=intensity_curve.controls(project)
        for block in blocks:
            midpoint=(block['start_seconds']+block['end_seconds'])/2
            manual=any(a['time']<=midpoint<a['time']+a.get('hold',2.) for a in project['anchors']) or any(v['start']<=midpoint<v['end'] for v in project['overrides'])
            if block['kind']!='transition_ending' and not manual:block['intensity_points']=points
    for block,row in zip(blocks,planned['blocks']):
        for key in ('use_id','assembly_material_id','assembly_order','assembly_sources'):
            if key in row:block[key]=row[key]
    for l in layers.values():l['notes'].sort(key=lambda n:(n.start,n.pitch))
    return dict(bpm=planned['bpm'],total_ticks=planned['total_ticks'],layers=list(layers.values()),
                report=dict(engine='story-rules-v1',bars=round(planned['total_ticks']/music.BAR,3),duration_seconds=planned['total_ticks']/rate,
                            render_mode='melody_only' if solo else 'arranged',
                            melody_continuity=dict(joined_fragments=joined,output_notes=len(melody),policy='same-source-note-only; retain-onset-timbre'),
                            assembly_blocks=planned.get('assembly_blocks',[]),connections_enabled=True,boundaries=boundaries,playback_blocks=blocks,anchors=planned['anchors'],
                            warnings=planned['warnings']+['离线规则原型；非生成式 AI。锚点误差不超过半个 LMMS 时间格。']))


def generate(project, progress=lambda _:None, render=True):
    progress('发展关联素材，按情绪线和锚点预留连接窗口…')
    planned=plan(project);score=compile_score(planned)
    folder=flow.structure.ROOT/'renders'/flow.structure.uid();folder.mkdir(parents=True)
    report=score['report'];report['output_directory']=str(folder)
    write=flow.structure.materials.write_json
    write(folder/'story.json',project);write(folder/'story-plan.json',planned)
    try:
        music.export_midi(score,folder/'composition.mid');music.export_mmp(score,folder/'composition.mmp')
        write(folder/'score.json',dict(bpm=score['bpm'],total_ticks=score['total_ticks'],layers=[dict(l,notes=[asdict(n) for n in l['notes']]) for l in score['layers']]))
        report['score_sha256']=hashlib.sha256((folder/'score.json').read_bytes()).hexdigest()
        if render:
            progress('连续渲染整首音乐；固定锚点不会因连接而后移…')
            proc=subprocess.run([str(music.LMMS),'render',str(folder/'composition.mmp'),'-o',str(folder/'dry.wav'),'-s','44100'],capture_output=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (folder/'render.log').write_bytes(proc.stdout+proc.stderr)
            if proc.returncode or not (folder/'dry.wav').is_file():raise ValueError('音频渲染失败：'+str(folder/'render.log'))
            report['audio']=flow.finish_audio(folder/'dry.wav',folder/'preview.wav',report['duration_seconds'])
            if report['audio']['peak']<.0001:raise ValueError('生成音频为静音。')
        report['status']='complete' if render else 'score_only'
    except Exception as exc:
        report.update(status='failed',error=str(exc));raise
    finally:write(folder/'report.json',report)
    return planned,report


def edit_block(project, block, emotion, level, source_id=None):
    if block['pinned']:raise ValueError('此块由锚点固定，请在锚点列表修改。')
    result=copy.deepcopy(project)
    start=block['start_seconds'];end=min(project['duration'],block['end_seconds'])
    tolerance=5/(project['bpm']*PPQ/60)+1e-8
    for a in project['anchors']:
        if abs(end-a['time'])<=tolerance:end=a['time']
        if abs(start-a['time']-a.get('hold',2.))<=tolerance:start=a['time']+a.get('hold',2.)
    retained=[]
    for v in result['overrides']:
        if v['end']<=start or v['start']>=end:retained.append(v);continue
        for left,right in ((v['start'],min(v['end'],start)),(max(v['start'],end),v['end'])):
            if right-left>=.1:
                delta=v.get('end_level',v['level'])-v['level'];span=v['end']-v['start']
                retained.append(dict(v,start=left,end=right,level=v['level']+delta*(left-v['start'])/span,end_level=v['level']+delta*(right-v['start'])/span))
    result['overrides']=retained
    result['overrides'].append(dict(start=start,end=end,emotion=emotion,level=level,end_level=level,source_id=source_id))
    validate(result)
    return result


def move_region(project,index,delta):
    result=copy.deepcopy(project);v=result['curve'][index];span=v['end']-v['start']
    v['start']=round(max(0,min(project['duration']-span,v['start']+delta)),2);v['end']=v['start']+span
    validate(result,require_source=False)
    return result
