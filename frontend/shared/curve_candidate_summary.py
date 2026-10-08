"""Short comparisons derived from actual candidate melody notes, never labels."""
def pitch_name(pitch):
    return ('C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B')[pitch%12]+str(pitch//12-1)

def melody_events(candidate):
    notes=(candidate.get('preview') or {}).get('notes',[])
    events={}
    for n in notes:
        events.setdefault(n['start_tick'],[]).append((n['pitch'],n['duration_tick']))
    return {tick:tuple(sorted(group)) for tick,group in events.items()}

def candidate_difference(candidate,candidates):
    if not candidate:return ''
    events=melody_events(candidate)
    other=next((c for c in candidates if c['id']!=candidate['id']),None)
    if other:
        comparison=melody_events(other)
        different=next((tick for tick in sorted(set(events)|set(comparison)) if events.get(tick)!=comparison.get(tick)),None)
        if different is not None:
            notes=events.get(different,())
            content='留白' if not notes else ' / '.join(pitch_name(pitch)+f'·{duration/480:g}拍' for pitch,duration in notes[:3])
            return f'差异位置·第{different/480+1:g}拍：{content}'
        return '旋律音高与节奏一致·连接及编配见详情'
    return f'{sum(len(group) for group in events.values())}音·仅有一个候选'
