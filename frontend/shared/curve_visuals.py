"""Presentation geometry and material identity; never changes musical data."""
import re

TYPE_COLORS = dict(original='#d4e8ec', derived='#e4ddf2', phrase='#eee3c8',
                   combination='#d6e7de', bridge='#ead9de')
TYPE_NAMES = dict(original='原始块', derived='新旋律', phrase='整句', combination='组合', bridge='Bridge')
DATA_INK = '#25313a'


def material_type(material, materials=()):
    if material['kind']=='combination':return 'combination'
    generation = material.get('generation') or {}
    if material['kind']=='bridge' or generation.get('method') in ('bridge_phrase','bridge_emotion_once'):
        return 'bridge'
    parent = next((m for m in materials if m['id']==material.get('phrase_id')),None)
    if parent is not None:return material_type(parent)
    if generation:return 'derived'
    return 'phrase' if material['kind']=='phrase' else 'original'


def stable_number(material):
    # Only the terminal assignment made by the persisted import transaction.
    match = re.search(r' · ([MS]\d+)$',material['label'])
    return match.group(1) if match else '#'+material['id'][:8]


def note_segments(box, notes, start_tick, length_ticks, stroke=2):
    """Return contained visual strokes, clipping only display geometry."""
    x1,y1,x2,y2 = box
    pad = stroke/2
    if x2-x1<=stroke or y2-y1<=stroke or length_ticks<=0:return []
    visible = [n for n in notes if n['start_tick']<start_tick+length_ticks
               and n['start_tick']+n['duration_tick']>start_tick]
    low = min((n['pitch'] for n in visible),default=60)
    high = max((n['pitch'] for n in visible),default=60)
    result = []
    for note in visible:
        a = max(start_tick,note['start_tick']);b = min(start_tick+length_ticks,note['start_tick']+note['duration_tick'])
        left = x1+pad+(a-start_tick)/length_ticks*(x2-x1-stroke)
        right = x1+pad+(b-start_tick)/length_ticks*(x2-x1-stroke)
        y = (y1+y2)/2 if low==high else y2-pad-(note['pitch']-low)/(high-low)*(y2-y1-stroke)
        result.append((left,y,right,y,note['id']))
    return result


def draw_notes(canvas, box, notes, start_tick, length_ticks, ink=DATA_INK, stroke=2, tags=()):
    return [canvas.create_line(a,y,b,y,fill=ink,width=stroke,capstyle='round',tags=tags)
            for a,y,b,_,ident in note_segments(box,notes,start_tick,length_ticks,stroke)]
