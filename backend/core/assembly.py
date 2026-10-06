"""Reusable melody snapshots and independent, ordered uses in assembly projects."""
import copy
import math
import uuid
import intensity_curve

SCHEMA='emoblocks.assembly.v1'
PPQ=480
BAR=4*PPQ


def uid():return uuid.uuid4().hex

def is_project(project):return isinstance(project,dict) and project.get('schema')==SCHEMA


def new_project(sample=None):
    p=dict(schema=SCHEMA,sources=[],library=[],uses=[],bpm=120.,duration=0.,curve=[],anchors=[],overrides=[],
           intensity_points=[],continuous_intensity=True,auto_peak_memory=True,memory_mode='automatic')
    return add_source(p,sample) if sample else p


def material(project,ident):return next(m for m in project['library'] if m['id']==ident)


def notes_in(notes,start,end):
    result=[]
    for n in notes:
        a=max(start,n['start']);b=min(end,n['start']+n['duration'])
        if b>a:result.append(dict(n,start=a-start,duration=b-a))
    return result


def add_source(project,source):
    result=copy.deepcopy(project);source=copy.deepcopy(source);result['sources'].append(source)
    group=len(result['sources']);letter=chr(64+group) if group<=26 else f'M{group}'
    for index,start in enumerate(range(0,source['ticks'],BAR)):
        end=min(source['ticks'],start+BAR);ident=uid();name=f'{letter}{index+1}'
        leaf=dict(kind='block',id=ident,name=name,ticks=end-start,notes=notes_in(source['notes'],start,end),
                  tonic=source['tonic'],mode=source['mode'],role=source['role'],
                  origin=dict(source_id=source['id'],source_name=source['name'],block_index=index,
                              start_tick=start,end_tick=end,source=copy.deepcopy(source.get('source',{}))))
        result['library'].append(leaf)
    return normalize(result)


def combine(project,items,name):
    if not name.strip():raise ValueError('请为组合素材命名。')
    if not items:raise ValueError('请先加入分块。')
    parts=copy.deepcopy(items);offset=0;notes=[]
    for item in parts:
        notes.extend(dict(n,start=n['start']+offset) for n in item['notes']);offset+=item['ticks']
    return dict(kind='combination',id=uid(),name=name.strip(),ticks=offset,notes=notes,components=parts,
                tonic=parts[0]['tonic'],mode=parts[0]['mode'],role='auto')


def save_combination(project,items,name):
    result=copy.deepcopy(project);result['library'].append(combine(project,items,name));return normalize(result)


def set_source_role(project,ident,role):
    result=copy.deepcopy(project)
    source=next(s for s in result['sources'] if s['id']==ident);source['role']=role
    def apply(asset):
        if asset['kind']=='block' and asset['origin']['source_id']==ident:asset['role']=role
        for part in asset.get('components',[]):apply(part)
    for asset in result['library']:apply(asset)
    for use in result['uses']:apply(use['material'])
    return normalize(result)


def ranges(project):
    cursor=0;result=[]
    for use in project['uses']:
        end=cursor+use['material']['ticks'];result.append((cursor,end,use));cursor=end
    return result


def insert(project,material_id,index=None):
    result=copy.deepcopy(project);asset=copy.deepcopy(material(project,material_id))
    index=len(result['uses']) if index is None else max(0,min(index,len(result['uses'])))
    result['uses'].insert(index,dict(id=uid(),material_id=asset['id'],material=asset,emotion='calm'))
    return normalize(result)


def reorder(project,index,target):
    result=copy.deepcopy(project)
    use=result['uses'].pop(index);result['uses'].insert(max(0,min(target,len(result['uses']))),use)
    return normalize(result)


def delete(project,indexes):
    result=copy.deepcopy(project);indexes=set(indexes)
    result['uses']=[v for i,v in enumerate(result['uses']) if i not in indexes];return normalize(result)


def paint(project,indexes,emotion):
    result=copy.deepcopy(project)
    for i in indexes:result['uses'][i]['emotion']=emotion
    return normalize(result)


def normalize(project):
    result=copy.deepcopy(project);rate=result['bpm']*PPQ/60
    duration=sum(u['material']['ticks'] for u in result['uses'])/rate
    stored=result.get('intensity_points',[])
    if not duration:points=[]
    elif not stored:points=[dict(time=0.,level=.25),dict(time=duration,level=.25)]
    elif abs(duration-project.get('duration',0))<1e-9:points=copy.deepcopy(stored)
    else:
        points=[copy.deepcopy(p) for p in stored if p['time']<duration]
        points.append(dict(time=duration,level=intensity_curve.evaluate(stored,duration)))
    result.update(duration=duration,intensity_points=points,curve=[])
    for start,end,use in ranges(result):
        result['curve'].append(dict(start=start/rate,end=end/rate,emotion=use['emotion'],level=.25,end_level=.25,
                                    source_id=use['material_id'],use_id=use['id']))
    validate(result,require_source=False);return result


def change_bpm(project,bpm):
    result=copy.deepcopy(project);old=result['bpm'];result['bpm']=bpm
    ratio=old/bpm
    for point in result['intensity_points']:point['time']*=ratio
    result['duration']*=ratio
    return normalize(result)


def leaves(asset,offset=0):
    if asset['kind']=='block':return [dict(asset,start=offset,end=offset+asset['ticks'])]
    result=[]
    for part in asset['components']:
        result.extend(leaves(part,offset));offset+=part['ticks']
    return result


def composition(asset):return '＋'.join(p['name'] for p in asset.get('components',[])) if asset['kind']=='combination' else asset['origin']['source_name']


def validate_asset(asset,depth=0):
    import story_engine as engine
    if depth>32:raise ValueError('组合层级过深。')
    if not isinstance(asset.get('id'),str) or not asset['id'] or not isinstance(asset.get('name'),str):raise ValueError('素材身份或名称无效。')
    if type(asset['ticks']) is not int or asset['ticks']<=0:raise ValueError('素材拍数无效。')
    if asset['role'] not in engine.ROLES or type(asset['tonic']) is not int or not 0<=asset['tonic']<=11 or asset['mode'] not in ('major','minor'):raise ValueError('素材调性或用途无效。')
    if not isinstance(asset['notes'],list):raise ValueError('素材音符快照无效。')
    last=0
    for n in asset['notes']:
        if any(type(n.get(k)) is not int for k in ('start','duration','pitch','velocity')) or n['start']<last or n['duration']<=0 or n['start']+n['duration']>asset['ticks'] or not 0<=n['pitch']<=127 or not 1<=n['velocity']<=127:raise ValueError('素材音符时间或单声部顺序无效。')
        last=n['start']+n['duration']
    if asset['kind']=='block':
        origin=asset['origin']
        if not isinstance(origin.get('source_id'),str) or type(origin.get('block_index')) is not int or origin['block_index']<0 or origin['end_tick']-origin['start_tick']!=asset['ticks']:raise ValueError('分块来源无效。')
    elif asset['kind']=='combination':
        parts=asset['components']
        if not isinstance(parts,list) or not parts:raise ValueError('组合素材不能为空。')
        for part in parts:validate_asset(part,depth+1)
        offset=0;notes=[]
        for part in parts:
            notes.extend(dict(n,start=n['start']+offset) for n in part['notes']);offset+=part['ticks']
        if offset!=asset['ticks'] or notes!=asset['notes']:raise ValueError('组合快照与组成不一致。')
    else:raise ValueError('未知素材类型。')


def validate(project,require_source=True):
    import story_engine as engine
    if not is_project(project):raise ValueError('组装工程版本无效。')
    engine.number(project['bpm'],40,220,'速度')
    for key in ('sources','library','uses','curve','anchors','overrides'):
        if not isinstance(project[key],list):raise ValueError('组装数据无效。')
    if project['anchors'] or project['overrides']:raise ValueError('新组装工程使用连续强度与自动记忆点。')
    ids=set()
    for source in project['sources']:
        validate_asset(dict(source,kind='block',origin=dict(source_id=source['id'],block_index=0,start_tick=0,end_tick=source['ticks'])))
        if source['id'] in ids:raise ValueError('原始素材身份重复。')
        ids.add(source['id'])
    ids=set()
    for m in project['library']:
        validate_asset(m)
        if m['id'] in ids:raise ValueError('素材身份重复。')
        ids.add(m['id'])
    ids=set()
    for use in project['uses']:
        if not isinstance(use.get('id'),str) or not use['id'] or use['id'] in ids:raise ValueError('使用身份重复或无效。')
        ids.add(use['id']);validate_asset(use['material'])
        if use['material_id']!=use['material']['id'] or use['emotion'] not in engine.music.EMOTIONS:raise ValueError('使用素材或情绪无效。')
    if require_source and not project['uses']:raise ValueError('请拖入旋律分块，搭建你的情绪积木。')
    total=sum(u['material']['ticks'] for u in project['uses']);duration=total/(project['bpm']*PPQ/60)
    if not isinstance(project['duration'],(int,float)) or not math.isfinite(project['duration']) or abs(project['duration']-duration)>1e-8:raise ValueError('作品时长与组装拍数不一致。')
    rate=project['bpm']*PPQ/60
    expected=[dict(start=a/rate,end=b/rate,emotion=u['emotion'],level=.25,end_level=.25,source_id=u['material_id'],use_id=u['id']) for a,b,u in ranges(project)]
    if project['curve']!=expected:raise ValueError('情绪条与组装顺序不一致。')
    intensity_curve.validate(project)
    if any(p['time']>duration+1e-8 for p in project['intensity_points']):raise ValueError('强度点超出作品。')
    return project


def render_project(project):
    result=copy.deepcopy(project);result['schema']='emoblocks.story.v1';result['assembly_mode']=True
    # Render each use from its own snapshot, even when two uses share a reusable identity.
    result['sources']=[dict(copy.deepcopy(u['material']),id=u['id'],reusable_material_id=u['material_id']) for u in project['uses']]
    for region,use in zip(result['curve'],project['uses']):region['source_id']=use['id']
    return result


def generation_edges(project):
    edges={0}
    for a,b,use in ranges(project):
        edges.update((a,b))
        for leaf in leaves(use['material'],a):
            edges.update(range(leaf['start'],leaf['end'],BAR));edges.add(leaf['end'])
    return sorted(edges)
