"""Ephemeral immutable playback captures. No project IDs or music are created."""
import copy


def neutral_context(kind,ident,snapshot,key,input_key):
    material=copy.deepcopy(snapshot['target']);project=snapshot['project']
    segments=[]
    def visit(value,start,path):
        if value.get('kind')=='combination':
            for i,child in enumerate(value['children']):visit(child['snapshot'],start+child['offset_tick'],path+[i])
        else:
            for offset in range(0,value['length_ticks'],1920):
                segments.append(dict(start_tick=start+offset,end_tick=start+min(value['length_ticks'],offset+1920),component_path=path))
    visit(material,0,[])
    placement=next((p for p in project['placements'] if kind=='placement' and p['id']==ident),None)
    return dict(neutral=True,key=key,kind=kind,id=ident,snapshot=material,bpm=project['bpm'],
                total_ticks=material['length_ticks'],notes=copy.deepcopy(material['notes']),segments=segments,
                input_key=input_key,placement=copy.deepcopy(placement),mapping_available=True,mapping_reason=None)


def same_card(playing,material):
    context=(playing or {}).get('context') or {}
    return context.get('neutral') and context.get('kind')=='material' and context['snapshot']==material


def playing_owner(app,canvas):
    playing=app.playing_target
    if not playing or app.player.status()[1] not in ('playing','paused'):return None
    context=playing.get('context') or {}
    if context.get('neutral'):
        if context['kind']!='placement' or context['input_key']!=app.input_key() or canvas.readonly:return None
        current=next((p for p in canvas.project['placements'] if p['id']==context['id']),None)
        return context['id'] if current==context['placement'] else None
    if context.get('schema')!='emoblocks.ui-playback.v1' or not canvas.recommendation_preview:return None
    target=context['target'];rec=app.recommendation
    candidate=rec.candidate()
    # Current canvas is final preview, never comparison or inferred historical music.
    if not candidate or target['side']!='final' or target['id']!=candidate['id'] or target['mode']!=rec.mode_key():return None
    member=candidate['modes'].get(target['mode'],{})
    if member.get('final_score_ref')!=context['score_ref']:return None
    if (canvas.display_notes()!=context['notes'] or canvas.project['total_ticks']!=context['total_ticks']
            or canvas.project['bpm']!=context['bpm']):return None
    tick=app.player.status()[0]*480*context['bpm']/60
    segment=next((s for s in context['segments'] if s['start_tick']<=tick<s['end_tick']),None)
    if not segment:return None
    return (segment.get('owner_ref') or {}).get('id') or segment.get('id')
