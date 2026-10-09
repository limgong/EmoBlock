"""User-authored melody assemblies, musical-grid placement and drawn emotions."""
import bisect
import copy
import math
import uuid
BAR=1920
PPQ=480

def brick(project,ident):
    value=next((b for b in project.get('melody_bricks',[]) if b['id']==ident),None)
    if value is None:raise ValueError('积木不存在，请重新选择。')
    return value

def compose(source,indices):
    count=math.ceil(source['ticks']/BAR)
    if not isinstance(indices,list) or not indices or any(type(i) is not int or not 0<=i<count for i in indices):
        raise ValueError('请选择有效的四拍分块。')
    if indices!=sorted(set(indices)):raise ValueError('分块按原旋律顺序拼接，不能重复或倒序。')
    notes=[];origins=[]
    for j,index in enumerate(indices):
        for k,n in enumerate(source['notes']):
            left=max(index*BAR,n['start']);right=min((index+1)*BAR,n['start']+n['duration'])
            if right<=left:continue
            value=dict(pitch=n['pitch'],start=j*BAR+left-index*BAR,duration=right-left,velocity=n['velocity'])
            if (notes and origins[-1]==k and j and indices[j-1]+1==index
                    and notes[-1]['start']+notes[-1]['duration']==value['start']):
                notes[-1]['duration']+=value['duration']
            else:notes.append(value);origins.append(k)
    return notes

def create(project,source_id,indices,name=None,emotion='calm'):
    import story_engine as engine
    engine.validate(project)
    source=next((s for s in project['sources'] if s['id']==source_id),None)
    if source is None:raise ValueError('旋律素材不存在。')
    indices=sorted(set(indices));notes=compose(source,indices)
    value=dict(id='brick-'+uuid.uuid4().hex[:12],source_id=source_id,block_indices=indices,
               notes=notes,ticks=len(indices)*BAR,name=(name or '旋律 '+','.join(str(i+1) for i in indices))[:64],emotion=emotion)
    result=copy.deepcopy(project);result.setdefault('melody_bricks',[]).append(value)
    engine.validate(result);return result,value['id']

def validate(project):
    import story_engine as engine
    values=project.get('melody_bricks',[]);placements=project.get('brick_placements',[])
    if not isinstance(values,list) or len(values)>64 or not isinstance(placements,list) or len(placements)>256:
        raise ValueError('最多保存 64 个旋律积木、256 次摆放。')
    source_by_id={s['id']:s for s in project['sources']};ids=set()
    for b in values:
        if not isinstance(b.get('id'),str) or b['id'] in ids or not b['id']:raise ValueError('积木 ID 无效或重复。')
        ids.add(b['id']);source=source_by_id.get(b['source_id'])
        if source is None:raise ValueError('积木引用的旋律已不存在。')
        if b['ticks']!=len(b['block_indices'])*BAR or b['notes']!=compose(source,b['block_indices']):raise ValueError('积木音符快照与所选分块不一致。')
        if not isinstance(b['name'],str) or not 1<=len(b['name'])<=64:raise ValueError('积木名称为 1–64 个字符。')
        engine.expression(b)
    occupied=[];pids=set();bar=240/project['bpm']
    for p in placements:
        if not isinstance(p.get('id'),str) or p['id'] in pids:raise ValueError('摆放 ID 重复或无效。')
        pids.add(p['id']);b=brick(project,p['brick_id'])
        if type(p['start_bar']) is not int or p['start_bar']<0:raise ValueError('积木必须吸附在四拍网格。')
        if p.get('variant','original') not in ('original','simple') or type(p.get('edge_connect',True)) is not bool:raise ValueError('积木变体或连接设置无效。')
        engine.expression(p);start=p['start_bar']*bar;end=start+b['ticks']/BAR*bar
        if end>project['duration']+1e-8:raise ValueError('积木超出时间线，请先加长时间线。')
        if any(start<right-1e-8 and end>left+1e-8 for left,right in occupied):raise ValueError('这里已有旋律积木，请换一个空位。')
        occupied.append((start,end))
        locked=[(a['time'],a['time']+a.get('hold',2.)) for a in project['anchors']]
        locked.extend((v['start'],v['end']) for v in project['overrides'])
        if any(start<right-1e-8 and end>left+1e-8 for left,right in locked):raise ValueError('此处有固定锚点或旧局部修改，请先解除。')

def spans(project,protected=False):
    bar=240/project['bpm'];result=[]
    for p in project.get('brick_placements',[]):
        b=brick(project,p['brick_id']);start=p['start_bar']*bar;end=start+b['ticks']/BAR*bar
        if protected and p.get('edge_connect',True) and b['ticks']>=3*BAR:start+=bar;end-=bar
        result.append((start,end,p,b))
    return result

def placement_at(project,time):
    return next(((p,b) for start,end,p,b in spans(project) if start<=time<end),None)

def place(project,brick_id,start_bar,emotion=None,placement_id=None,variant='original',edge_connect=True):
    import story_engine as engine
    b=brick(project,brick_id);result=copy.deepcopy(project)
    ident=placement_id or 'place-'+uuid.uuid4().hex[:12]
    result['brick_placements']=[p for p in result.get('brick_placements',[]) if p['id']!=ident]
    result['brick_placements'].append(dict(id=ident,brick_id=brick_id,start_bar=start_bar,
        emotion=emotion or b['emotion'],variant=variant,edge_connect=edge_connect))
    result['brick_placements'].sort(key=lambda p:p['start_bar']);engine.validate(result);return result,ident

def remove(project,ident,library=False):
    result=copy.deepcopy(project)
    if library:
        result['melody_bricks']=[b for b in result.get('melody_bricks',[]) if b['id']!=ident]
        result['brick_placements']=[p for p in result.get('brick_placements',[]) if p['brick_id']!=ident]
    else:result['brick_placements']=[p for p in result.get('brick_placements',[]) if p['id']!=ident]
    return result

def remove_source(project,source_id):
    result=copy.deepcopy(project)
    for b in project.get('melody_bricks',[]):
        if b['source_id']==source_id:result=remove(result,b['id'],library=True)
    return result

def first_gap(project,ident):
    b=brick(project,ident);length=b['ticks']//BAR;bar=240/project['bpm']
    for i in range(math.floor(project['duration']/bar+1e-8)-length+1):
        locked=[(a['time'],a['time']+a.get('hold',2.)) for a in project['anchors']]
        locked.extend((v['start'],v['end']) for v in project['overrides'])
        if (all(i+length<=p['start_bar'] or i>=p['start_bar']+brick(project,p['brick_id'])['ticks']//BAR for p in project.get('brick_placements',[]))
                and all((i+length)*bar<=a or i*bar>=b for a,b in locked)):
            return i
    raise ValueError('没有足够的连续空位，请加长时间线或移动已放积木。')

def summary(project):
    total=math.ceil(project['duration']/(240/project['bpm'])-1e-8)
    fixed=sum(brick(project,p['brick_id'])['ticks']//BAR for p in project.get('brick_placements',[]))
    return dict(total=total,fixed=fixed,empty=total-fixed)

def apply_rows(project,rows):
    """Constrain the lead melody, not its emotional arrangement.

    Keep row emotion/intensity for compile_score's timbre, dynamics and backing.
    ``pinned`` protects melody content from connection replacement, not rendering.
    """
    source_by_id={s['id']:s for s in project['sources']};bar=240/project['bpm']
    for r in rows:
        value=placement_at(project,(r['start_seconds']+r['end_seconds'])/2)
        if value is None:continue
        p,b=value;start=p['start_bar']*BAR;offset=r['start_tick']-start;size=r['end_tick']-r['start_tick']
        source=source_by_id[b['source_id']];scale=[v for v in range(12,120) if (v-source['tonic'])%12 in ([0,2,4,5,7,9,11] if source['mode']=='major' else [0,2,3,5,7,8,10])]
        notes=[]
        for i,n in enumerate(b['notes']):
            left=max(offset,n['start']);right=min(offset+size,n['start']+n['duration'])
            if right<=left:continue
            pitch=n['pitch']
            if p.get('variant')=='simple' and i%4==2:
                pitch=min(scale,key=lambda v:abs(v-(pitch+2)))
            notes.append(dict(n,pitch=pitch,start=left-offset,duration=right-left,
                source_note_id=['brick',p['id'],i],continuation=left>n['start']))
        edge=p.get('edge_connect',True) and b['ticks']>=3*BAR and (offset<BAR or offset+size>b['ticks']-BAR)
        source_start=b['block_indices'][min(len(b['block_indices'])-1,offset//BAR)]*BAR+offset%BAR
        r.update(notes=notes,source_id=b['source_id'],source_offset=source_start,material_id=b['source_id']+':original',
                 version='variant' if p.get('variant')=='simple' else 'original',kind='content',pinned=not edge,
                 name=b['name']+' · '+str(offset//BAR+1),placement_id=p['id'],brick_id=b['id'],manual_brick=True,
                 edge_connect_allowed=edge,source_spans=[dict(source_id=b['source_id'],material_id=b['source_id']+':original',
                    start=source_start,end=min(source_start+size,source['ticks']),cycle=0,phrase_ids=[])])

def draw_emotion(project,samples,emotion):
    import emotion_input
    import intensity_curve
    import story_engine as engine
    if not samples:raise ValueError('请画一段情绪曲线。')
    merged={}
    for time,level in samples:
        engine.number(time,0,project['duration'],'手绘时间');engine.number(level,0,1,'手绘程度')
        merged[round(time,6)]=level
    points=sorted(merged.items());times=[t for t,v in points]
    def value(time):
        i=bisect.bisect_right(times,time)
        if i==0:return points[0][1]
        if i==len(points):return points[-1][1]
        a,x=points[i-1];b,y=points[i];return x+(y-x)*(time-a)/(b-a)
    bar=240/project['bpm'];first=min(math.floor(times[0]/bar),math.ceil(project['duration']/bar)-1)
    last=min(math.floor(times[-1]/bar),math.ceil(project['duration']/bar)-1)
    result=emotion_input.paint_blocks(project,first*bar,min(project['duration'],(last+1)*bar),emotion,value(times[0]),value(times[-1]))
    controls=intensity_curve.controls(project);levels={round(p['time'],6):p['level'] for p in controls}
    for i in range(first,last+1):
        middle=(i*bar+min(project['duration'],(i+1)*bar))/2;levels[round(middle,6)]=value(middle)
    result['intensity_points']=[dict(time=t,level=v) for t,v in sorted(levels.items())]
    result['continuous_intensity']=True;result['emotion_drawn']=True
    engine.validate(result,require_source=False);intensity_curve.validate(result);return result
