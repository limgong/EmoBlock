"""Read-only browser projection of authenticated final-score ownership."""
from .core import short_name, model


def result_view(c, candidate, attempt):
    from curve_recommendations import resolve
    facts=c._bundle['final_facts']
    mode=attempt['recommendation']['request']['mode']
    score=resolve(facts,candidate['modes'][mode]['final_score_ref'],'final_score')
    request=resolve(facts,score['boundary_request_ref'],'boundary_request')
    base=request['actual_layout']['base_project']
    original={p['id'] for p in request['connection_ref']['request']['bridge_ref']['request']['input_project']['placements']}
    placements={p['id']:p for p in base['placements']}
    memory=__import__('curve_memory').memory_info(base)
    segments=[]
    counts={}
    names={}
    for span in request['actual_layout']['segments']:
        owner=span['owner_ref']['id'];place=placements.get(owner)
        role=span['kind']
        if role=='placement':
            role='original' if owner in original else 'completion'
            if role=='original' and place and place['base_snapshot']['generation']:
                role='melody'
            if place and model.manual_bridge_material(base,place['base_snapshot']):
                role='bridge'
        label={'original':'原始积木','melody':'新旋律','completion':'补全积木','bridge':'Bridge','connection':'连接块','blank':'主动留白'}.get(role,'保留旋律')
        if (role,owner) not in names:
            counts[role]=counts.get(role,0)+1
            name=short_name(place['base_snapshot']) if place else {'bridge':'BR','connection':'CN','blank':'留白'}.get(role,'片段')+str(counts[role])
            if name.startswith('#'):
                name=('补全' if role=='completion' else '素材')+str(counts[role])
            names[role,owner]=name
        name=names[role,owner]
        start,end=span['start_tick'],span['end_tick']
        notes=[]
        for note in score['notes']:
            a=max(start,note['start_tick']);z=min(end,note['start_tick']+note['duration_tick'])
            if a<z:
                notes.append(dict(pitch=note['pitch'],start_tick=a-start,duration_tick=z-a,velocity=note['velocity']))
        segments.append(dict(id=span['id'],start_tick=start,end_tick=end,role=role,role_label=label,
            display_name=name,emotion=span['emotion'],notes=notes,
            memory=owner==memory['placement_id'],partial=bool(place and (start!=place['start_tick'] or end!=place['start_tick']+place['length_ticks']))))
    return dict(segments=segments,source_fingerprint=model.fingerprint(base))
