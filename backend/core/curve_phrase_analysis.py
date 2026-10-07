"""Bounded factual whole-score analysis for the global-v2 bridge planner.

No composition, publication, rendering, or persistent caches. Validation rebuilds
facts through primitives, never through the public analysis/decision entrypoints.
"""
import bisect
import copy
import statistics

import curve_project as m
import curve_bridges as bridges
import curve_melody as melody
import intensity_curve

SCHEMA = 'emoblocks.whole-score-analysis.v1'
ALGORITHM_VERSION = 'curve-phrase-analysis-v1.1'
GLOBAL_ALGORITHM = 'curve-bridge-global-v2'
LIMITS = dict(notes=4096, placements=512, occurrences=1536, terminals=1024,
              endpoints=2048, controls=512, samples=8192, phrases=128,
              candidates=262144, json_bytes=16*1024*1024, depth=64)
FIELDS = ('schema algorithm_version base_fingerprint layout_fingerprint '
          'protection_fingerprint total_ticks occurrences boundaries phrases '
          'motif_relations trajectory analysis_fingerprint')


def _fail(code, message):
    raise m.ProjectError(code, message)


def _check(cancel):
    if cancel is not None and cancel():
        _fail('CANCELLED', 'Whole-score analysis cancelled.')


def _bound(name, value):
    if value > LIMITS[name]:
        _fail('ANALYSIS_LIMIT', 'Whole-score analysis exceeds '+name+' budget.')


def _support(n):
    return n['start_tick'], n['start_tick']+n['duration_tick']


def _order(notes):
    return sorted(notes, key=lambda n:(n['start_tick'], n['pitch'], n['duration_tick'], n['id']))


def _size(value, depth=0):
    _bound('depth', depth)
    if isinstance(value, dict):
        for v in value.values(): _size(v, depth+1)
    elif isinstance(value, list):
        for v in value: _size(v, depth+1)


def _preflight(request):
    _bound('notes', len(request['base_notes']))
    _bound('placements', len(request['base_project']['placements']))
    _bound('controls', len(request['base_project']['intensity_points']))
    _size(request['base_project']['placements'])


def _leaves(material, start, path=(), depth=0):
    if depth > 16:
        _fail('ANALYSIS_LIMIT', 'Component depth exceeds 16.')
    if material['kind'] != 'combination':
        return [(list(path), start, start+material['length_ticks'], material)]
    result = []
    for child in sorted(material['children'], key=lambda c:(c['offset_tick'],c['occurrence_id'])):
        result.extend(_leaves(child['snapshot'],start+child['offset_tick'],
                              (*path,child['occurrence_id']),depth+1))
        _bound('terminals',len(result))
    return result


def _source_refs(notes):
    refs = {(n['origin']['source_id'],n['origin']['track_id']) for n in notes if n['origin'] is not None}
    return [dict(source_id=s,track_id=t) for s,t in sorted(refs)]


def _row(role, owner, performance, start, end, notes, emotion, hint=None):
    identity=dict(role=role,owner_ref=owner,performance_id=performance,start_tick=start,end_tick=end)
    return dict(id=m.digest('emoblocks.phrase-occurrence.v1',identity), **identity,
                placement_id=owner.get('placement_id'),material_snapshot_id=owner['material_snapshot_id'],
                component_path=copy.deepcopy(owner['component_path']),note_ids=[n['id'] for n in _order(notes)],
                source_refs=_source_refs(notes),emotion=emotion,source_phrase_ref=hint)


def _source_phrase_hint(project, leaf):
    """Only captured import segmentation with independently matching source facts.

    A phrase_id alone is not a source phrase. Ordinary/generated material and
    arbitrary user metadata cannot create this evidence.
    """
    parent=leaf
    if leaf['phrase_id'] is not None:
        parent=next((v for v in project['materials'] if v['id']==leaf['phrase_id']),None)
    if parent is None or parent['kind']!='phrase' or parent['generation'] is not None:
        return None
    meta=parent['provenance'];source=next((v for v in project['sources'] if v['id']==meta.get('source_id')),None)
    if (source is None or meta.get('segmentation_version')!=melody.SEGMENTATION_VERSION
            or meta.get('source_provenance')!=source['provenance']
            or meta.get('segmentation_parameters')!=dict(rest_threshold_ticks=240,min_complete_ticks=1920,min_complete_notes=2)
            or type(meta.get('source_start_tick')) is not int):
        return None
    start=meta['source_start_tick'];end=start+parent['length_ticks']
    original=[n for n in source['notes'] if start<=n['start_tick']<end]
    if any(n['start_tick']+n['duration_tick']>end for n in original):return None
    expected=sorted((n['id'],n['pitch'],n['start_tick']-start,n['duration_tick']) for n in original)
    actual=sorted((n['origin']['source_note_id'],n['pitch'],n['start_tick'],n['duration_tick'])
                  for n in parent['notes'] if n['origin'] is not None and n['origin']['source_id']==source['id'])
    if len(actual)!=len(parent['notes']) or actual!=expected:return None
    relative=leaf['provenance'].get('relative_start_tick',0)
    if type(relative) is not int or relative<0 or relative+leaf['length_ticks']>parent['length_ticks']:return None
    return dict(source_id=source['id'],phrase_id=parent['id'],relative_start_tick=relative)


def _owners(request, cancel=None):
    """Resolve by existing authoritative ParentRef; never by time or history ID."""
    import curve_application as application
    project=request['base_project']; notes=_order(request['base_notes'])
    places={p['id']:p for p in project['placements']}; physical={}; accepted={}; keys={}
    scores={}; metadata={}
    for note in notes:
        _check(cancel)
        parent=bridges.parent_ref(request,note['id'])
        if parent.get('kind')=='accepted_score':
            if parent['owner_id'] not in scores:
                score=application.source_score(project,note['id'])
                scores[score['id']]=score
                mapping={}
                for row in score['performance_map']:
                    for ident in row['logical_note_ids']:
                        if ident in mapping: _fail('SOURCE_CLOSURE_INVALID','Ambiguous performance ownership.')
                        mapping[ident]=row
                entries={}
                for layer in score['layers']:
                    if layer['role']!='melody': continue
                    for entry in layer['rules']['entries']:
                        entries.setdefault(entry['note_id'],[]).append(entry)
                metadata[score['id']]=(mapping,entries)
            score=scores[parent['owner_id']]; mapping,entries=metadata[score['id']]
            original=[n for n in score['notes'] if n['id']==note['id']]
            row=mapping.get(note['id']); actual_entries=entries.get(row['emitted_note_id'],[]) if row else []
            if len(original)!=1 or original[0]!=note or row is None or len(actual_entries)!=1:
                _fail('SOURCE_CLOSURE_INVALID','Accepted note lacks exact parent/performance/emission.')
            entry=actual_entries[0]
            if entry['note_id']!=row['emitted_note_id']:
                _fail('SOURCE_CLOSURE_INVALID','Accepted emission is not its declared performance.')
            owner={k:copy.deepcopy(v) for k,v in parent.items() if k!='note_id'}
            token=m.canonical(dict(owner=owner,performance_id=row['performance_id']))
            accepted.setdefault(token,dict(owner=owner,performance=row['performance_id'],notes=[],emotions=[]))
            accepted[token]['notes'].append(note); accepted[token]['emotions'].append(entry['emotion'])
            keys[note['id']]=copy.deepcopy(entry['key_context'])
        else:
            place=places.get(parent['placement_id'])
            if place is None: _fail('SOURCE_CLOSURE_INVALID','Unknown placement parent.')
            owner=dict(kind='placement',**{k:copy.deepcopy(v) for k,v in parent.items() if k!='note_id'})
            physical.setdefault((place['id'],tuple(owner['component_path'])),[]).append(note)
            snapshot=place['emotion_variant'] or place['base_snapshot']
            if parent['material_snapshot_id']!=snapshot['id']:
                _fail('SOURCE_CLOSURE_INVALID','Parent snapshot mismatch.')
    occurrences=[]
    for place in sorted(places.values(),key=lambda p:(p['start_tick'],p['id'])):
        actual=place['emotion_variant'] or place['base_snapshot']
        descendants=[]
        for path,a,b,leaf in _leaves(place['base_snapshot'],place['start_tick']):
            owned=physical.pop((place['id'],tuple(path)),[]); descendants.extend(owned)
            if owned:
                explicit=actual['provenance'].get('key_context') or (actual.get('generation') or {}).get('key_context')
                context=melody._key(actual if explicit is not None else leaf,owned)
                for n in owned:keys[n['id']]=copy.deepcopy(context)
            owner=dict(kind='placement',placement_id=place['id'],component_path=path,material_snapshot_id=actual['id'])
            hint=_source_phrase_hint(project,leaf)
            occurrences.append(_row('terminal',owner,None,a,b,owned,place['emotion'],hint))
        if place['base_snapshot']['kind']=='combination':
            owner=dict(kind='placement',placement_id=place['id'],component_path=[],material_snapshot_id=actual['id'])
            occurrences.append(_row('aggregate',owner,None,place['start_tick'],place['start_tick']+place['length_ticks'],descendants,place['emotion']))
    if physical: _fail('SOURCE_CLOSURE_INVALID','Actual note component path has no leaf.')
    for item in accepted.values():
        owned=item['notes']; levels=set(item['emotions'])
        occurrences.append(_row('terminal',item['owner'],item['performance'],
                          min(n['start_tick'] for n in owned),max(_support(n)[1] for n in owned),
                          owned,next(iter(levels)) if len(levels)==1 else None))
    occurrences.sort(key=lambda o:(o['start_tick'],o['end_tick'],o['role'],o['id']))
    _bound('occurrences',len(occurrences)); _bound('terminals',sum(o['role']=='terminal' for o in occurrences))
    identities=[i for o in occurrences if o['role']=='terminal' for i in o['note_ids']]
    if len(identities)!=len(set(identities)) or set(identities)!={n['id'] for n in notes}:
        _fail('SOURCE_CLOSURE_INVALID','Actual notes do not have one terminal owner.')
    return occurrences,keys


def note_keys(request):
    """Pure actual-parent tonal facts used by assessment authentication."""
    return _owners(request)[1]


def _endpoints(request, occurrences):
    total=request['base_project']['total_ticks']; points={0,total}
    points.update(t for n in request['base_notes'] for t in _support(n))
    points.update(t for o in occurrences for t in (o['start_tick'],o['end_tick']))
    ranges=list(request['resolved_ranges'])+list(request['blank_regions'])
    for lock in request['base_project']['protections']:
        ranges.extend(m.protection_ranges(lock))
        ranges.extend(dict(start_tick=_support(n)[0],end_tick=_support(n)[1]) for n in lock['notes'])
    points.update(r[k] for r in ranges for k in ('start_tick','end_tick'))
    # Sweep releases before attacks. A point may not split any full support.
    events={}
    for n in request['base_notes']:
        a,b=_support(n); events.setdefault(a,[0,0])[1]+=1;events.setdefault(b,[0,0])[0]+=1
    active=0; result=[]
    for t in sorted(points):
        release,attack=events.get(t,(0,0)); active-=release
        if not active: result.append(t)
        active+=attack
    _bound('endpoints',len(result)); return result


def _boundaries(request, occurrences):
    notes=_order(request['base_notes']); total=request['base_project']['total_ticks']
    owners={ident:(o['id'],o['performance_id']) for o in occurrences if o['role']=='terminal' for ident in o['note_ids']}
    evidence={t:[] for t in _endpoints(request,occurrences)}
    def add(t,kind,weight,details):
        if t in evidence and not any(e['kind']==kind for e in evidence[t]):
            evidence[t].append(dict(kind=kind,weight=weight,details=details))
    add(0,'start',1.,{});add(total,'end',1.,{})
    cursor=0
    for n in notes:
        if n['start_tick']>cursor:
            gap=n['start_tick']-cursor
            for t in (cursor,n['start_tick']):add(t,'rest',.60*min(1,gap/480),dict(start_tick=cursor,end_tick=n['start_tick']))
        cursor=max(cursor,_support(n)[1])
    if cursor<total:
        for t in (cursor,total):add(t,'rest',.60*min(1,(total-cursor)/480),dict(start_tick=cursor,end_tick=total))
    for n in notes: add(n['start_tick'],'attack',.1,dict(note_id=n['id']))
    for i,n in enumerate(notes):
        med=statistics.median([v['duration_tick'] for v in notes[max(0,i-2):i+1]])
        add(_support(n)[1],'rhythm_cadence',.20*min(1,n['duration_tick']/(2*med)),dict(note_id=n['id'],median_duration=med))
        if i>=2:
            x=notes[i-1]['pitch']-notes[i-2]['pitch'];y=n['pitch']-notes[i-1]['pitch']
            if x*y<0 and len({owners[v['id']] for v in notes[i-2:i+1]})==1:
                add(n['start_tick'],'contour_turn',.20,dict(note_ids=[v['id'] for v in notes[i-2:i+1]],
                    occurrence_id=owners[n['id']][0],performance_id=owners[n['id']][1]))
    for o in occurrences:
        if o['source_phrase_ref'] is not None and o['source_phrase_ref']['relative_start_tick']==0:
            add(o['start_tick'],'source_hint',.1,dict(occurrence_id=o['id']))
    for p in request['base_project']['placements']:
        for t in (p['start_tick'],p['start_tick']+p['length_ticks']):add(t,'placement_edge',.1,{})
        for path,a,b,_ in _leaves(p['base_snapshot'],p['start_tick']):
            for t in (a,b):add(t,'placement_edge',.1,{})
    order={k:i for i,k in enumerate(('start','end','rest','attack','rhythm_cadence','contour_turn','source_hint','placement_edge'))}
    return [dict(tick=t,confidence=round(min(1,sum(e['weight'] for e in es)),8),
                 evidence=sorted(es,key=lambda e:order[e['kind']]),
                 occurrence_ids=[o['id'] for o in occurrences if o['start_tick']<=t<=o['end_tick']])
            for t,es in sorted(evidence.items())]


def _phrases(request, occurrences, boundaries):
    cuts=[b for b in boundaries if b['confidence']>=.60]
    result=[]; notes=_order(request['base_notes'])
    for left,right in zip(cuts,cuts[1:]):
        a,b=left['tick'],right['tick'];ns=[n for n in notes if a<=n['start_tick']<b]
        result.append(dict(id=m.digest('emoblocks.analysis-phrase.v1',dict(algorithm_version=ALGORITHM_VERSION,
                    base_fingerprint=request['base_fingerprint'],range=dict(start_tick=a,end_tick=b))),
            start_tick=a,end_tick=b,note_ids=[n['id'] for n in ns],
            occurrence_ids=[o['id'] for o in occurrences if o['role']=='terminal' and set(o['note_ids']).intersection(n['id'] for n in ns)],
            contour=[y['pitch']-x['pitch'] for x,y in zip(ns,ns[1:])],
            rhythm=[dict(onset_tick=n['start_tick']-a,duration_tick=n['duration_tick']) for n in ns],
            confidence=min(left['confidence'],right['confidence'])))
    _bound('phrases',len(result));return result


def _similarity(a,b,invert=False):
    def sample(items):return [items[k*(len(items)-1)//15] for k in range(16)]
    ca=sample(a['contour']);cb=sample(b['contour'])
    cs=1-sum(min(1,abs(max(-12,min(12,x))-max(-12,min(12,-y if invert else y)))/12) for x,y in zip(ca,cb))/16
    la=a['end_tick']-a['start_tick'];lb=b['end_tick']-b['start_tick']
    error=sum(abs(x['onset_tick']/la-y['onset_tick']/lb)+abs(x['duration_tick']/la-y['duration_tick']/lb)
              for x,y in zip(sample(a['rhythm']),sample(b['rhythm'])))/16
    na,nb=len(a['note_ids']),len(b['note_ids'])
    rs=.75*(1-min(1,2*error))+.25*min(na,nb)/max(na,nb)
    return cs,rs


def _relations(phrases,cancel):
    eligible=[p for p in phrases if len(p['note_ids'])>=3]
    nonempty=[p['id'] for p in phrases if p['note_ids']]; sim={};result=[]
    for j,right in enumerate(eligible):
        for i,left in enumerate(eligible[:j]):
            _check(cancel);cs,rs=_similarity(left,right);sim[i,j]=(cs,rs)
            returning=j-i>=2 and cs>=.85 and rs>=.85 and any(min(sim[i,k])<.60 for k in range(i+1,j))
            if returning: kind='return'
            elif (left['contour'],left['rhythm'],left['end_tick']-left['start_tick'])==(right['contour'],right['rhythm'],right['end_tick']-right['start_tick']): kind='repeat'
            elif cs>=.75 and rs>=.75:kind='variation'
            elif nonempty.index(right['id'])==nonempty.index(left['id'])+1 and _similarity(left,right,True)[0]>=.85 and rs>=.75:kind='response'
            else:kind='contrast'
            result.append(dict(left_phrase_id=left['id'],right_phrase_id=right['id'],relation=kind,
                contour_similarity=cs,rhythm_similarity=rs,reason=dict(code='MOTIF_'+kind.upper(),
                message='Measured relative contour and rhythm; not a listening judgment.',details=dict(left_phrase_id=left['id'],right_phrase_id=right['id'],contour_similarity=cs,rhythm_similarity=rs))))
    positions={p['id']:i for i,p in enumerate(phrases)}
    return sorted(result,key=lambda r:(positions[r['left_phrase_id']],positions[r['right_phrase_id']]))


def _trajectory(request,occurrences,phrases,boundaries):
    project=request['base_project']; controls=project['intensity_points']
    ticks={b['tick'] for b in boundaries}|{c['tick'] for c in controls}
    ticks.update(t for o in occurrences+phrases for t in (o['start_tick'],o['end_tick'],(o['start_tick']+o['end_tick'])//2))
    _bound('samples',len(ticks));points=[dict(time=c['tick'],level=c['level']) for c in controls]
    samples=[dict(tick=t,level=intensity_curve.evaluate(points,t)) for t in sorted(ticks)]
    segments=[dict(start_tick=a['tick'],end_tick=b['tick'],start_level=a['level'],end_level=b['level'],
              signed_delta=b['level']-a['level'],slope=(b['level']-a['level'])/(b['tick']-a['tick'])) for a,b in zip(samples,samples[1:])]
    runs=[]
    for c in controls:
        if not runs or runs[-1]['level']!=c['level']:runs.append(c)
    peaks=[]
    if len(runs)>1:
        for i,c in enumerate(runs):
            adjacent=([runs[i-1]['level']] if i else [])+([runs[i+1]['level']] if i+1<len(runs) else [])
            if all(c['level']>v for v in adjacent):peaks.append(dict(tick=c['tick'],level=c['level'],kind='peak'))
            elif all(c['level']<v for v in adjacent):peaks.append(dict(tick=c['tick'],level=c['level'],kind='trough'))
    places=sorted(project['placements'],key=lambda p:(p['start_tick'],p['id']));changes=[]
    for t in sorted({v for p in places for v in (p['start_tick'],p['start_tick']+p['length_ticks'])}):
        before=next((p for p in places if p['start_tick']<t<=p['start_tick']+p['length_ticks']),None)
        after=next((p for p in places if p['start_tick']<=t<p['start_tick']+p['length_ticks']),None)
        old=before['emotion'] if before else None;new=after['emotion'] if after else None
        if old!=new:changes.append(dict(tick=t,from_emotion=old,to_emotion=new,placement_id=(after or before)['id']))
    return dict(samples=samples,segments=segments,peaks=peaks,emotion_changes=changes)


def _facts(request,cancel=None):
    _check(cancel);_preflight(request)
    # Local request validation authenticates actual music and every protection.
    import curve_bridge_music
    curve_bridge_music._validate_request(request)
    occurrences,_=_owners(request,cancel);boundaries=_boundaries(request,occurrences)
    phrases=_phrases(request,occurrences,boundaries)
    result=dict(schema=SCHEMA,algorithm_version=ALGORITHM_VERSION,base_fingerprint=request['base_fingerprint'],
        layout_fingerprint=bridges.splice_fingerprint(request['base_project']['total_ticks'],request['base_notes']),
        protection_fingerprint=request['protection_summary']['fingerprint'],total_ticks=request['base_project']['total_ticks'],
        occurrences=occurrences,boundaries=boundaries,phrases=phrases,motif_relations=_relations(phrases,cancel),
        trajectory=_trajectory(request,occurrences,phrases,boundaries))
    _check(cancel);result['analysis_fingerprint']=m.digest(SCHEMA,result)
    _size(result);_bound('json_bytes',len(m.canonical(result).encode('utf-8')))
    return result


def analyze(request,should_cancel=None):
    return _facts(request,should_cancel)


def validate(request,analysis):
    _size(analysis);m.shape(analysis,FIELDS)
    _bound('json_bytes',len(m.canonical(analysis).encode('utf-8')))
    if m.canonical(analysis)!=m.canonical(_facts(request)):
        _fail('INVALID_ANALYSIS','Analysis does not match authenticated whole-score facts.')


def _anchors(analysis):
    positions={p['id']:i for i,p in enumerate(analysis['phrases'])};parents={};salience={}
    def root(i):
        parents.setdefault(i,i)
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for r in analysis['motif_relations']:
        strength=min(r['contour_similarity'],r['rhythm_similarity'])
        if r['relation'] not in ('repeat','variation','return') or strength<.75:continue
        a,b=r['left_phrase_id'],r['right_phrase_id'];ra,rb=root(a),root(b)
        if ra!=rb:
            first,last=sorted((ra,rb),key=lambda i:positions[i]);parents[last]=first
        for i in (a,b):salience[i]=max(salience.get(i,0),strength)
    return {root(i):salience[root(i)] for i in parents}


def _level(analysis,tick):
    # Original controls are not re-created from samples. Window endpoints are E
    # and therefore have exact original-Hermite samples in authenticated analysis.
    samples=analysis['trajectory']['samples'];ticks=[s['tick'] for s in samples]
    i=bisect.bisect_left(ticks,tick)
    if i==len(ticks) or ticks[i]!=tick:_fail('INVALID_WINDOW','Window endpoint has no original trajectory sample.')
    return samples[i]['level']


def window_features(analysis,range):
    m.range_check(range,analysis['total_ticks'])
    if (analysis['schema'],analysis['algorithm_version'])!=(SCHEMA,ALGORITHM_VERSION):
        _fail('INVALID_ANALYSIS','Unsupported analysis version.')
    a,b=range['start_tick'],range['end_tick'];phrases=analysis['phrases'];anchors=_anchors(analysis)
    def fraction(p):
        return sum(n['duration_tick'] for n in p['rhythm'] if a<=p['start_tick']+n['onset_tick'] and p['start_tick']+n['onset_tick']+n['duration_tick']<=b)/max(1,sum(n['duration_tick'] for n in p['rhythm']))
    cut=.5*sum(any(p['note_ids'] and p['start_tick']<t<p['end_tick'] for p in phrases) for t in (a,b))
    preserve=max((s*fraction(p) for p in phrases for ident,s in anchors.items() if p['id']==ident),default=0.)
    lookup={p['id']:p for p in phrases};nonempty=[p for p in phrases if p['note_ids']]
    prep=0.;develop=0.;targets=[];used=[]
    for r in analysis['motif_relations']:
        p=lookup[r['right_phrase_id']];strength=min(r['contour_similarity'],r['rhythm_similarity'])
        if r['relation']=='return' and p['start_tick']==b:
            index=nonempty.index(p)
            if index and fraction(nonempty[index-1])>0:
                prep=max(prep,strength);targets.append(p);used.append(r)
        if r['relation'] in ('repeat','variation') and p['id'] not in anchors:
            amount=strength*max(0,2*fraction(p)-1)
            if amount>0:develop=max(develop,amount);used.append(r)
    contour=sum(min(targets,key=lambda p:p['start_tick'])['contour']) if targets else 0
    if not targets:
        for p in phrases:
            for i,interval in enumerate(p['contour']):
                x,y=p['rhythm'][i:i+2]
                if a<=p['start_tick']+x['onset_tick'] and p['start_tick']+y['onset_tick']+y['duration_tick']<=b:contour+=interval
    sign=(contour>0)-(contour<0)
    alignment=sign*max(-1,min(1,(_level(analysis,b)-_level(analysis,a))/.25))*max(prep,develop)
    gain=.40*prep+.25*develop+.20*alignment-.30*cut-.45*preserve
    return dict(phrase_cut_cost=cut,motif_preservation_cost=preserve,return_preparation=prep,
                repetition_development=develop,trajectory_alignment=alignment,global_gain=gain,
                reason_codes=[dict(code='GLOBAL_PREDICTED_GAIN',message='Whole-score rule prediction, not generated/listened quality.',
                    details=dict(range=copy.deepcopy(range),relations=[dict(left_phrase_id=r['left_phrase_id'],right_phrase_id=r['right_phrase_id'],relation=r['relation']) for r in used],
                                 anchor_phrase_ids=sorted(anchors),global_gain=gain))])


def validate_search(request,proposal):
    """Exact public pure gate seam; validates stored facts, never a provider."""
    from curve_bridge_music import validate_search as validate_stored_search
    validate_stored_search(request,proposal)
