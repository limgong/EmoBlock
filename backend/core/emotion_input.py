"""Transactional painting operations for the simple emotion timeline."""
import copy
import math
import story_engine as engine

DEFAULT_STORY=[('calm',1,.25),('suspense',2,.5),('crisis',3,.5),('sad',2,.3),('resolve',4,.85),('calm',1,.25)]


def resize_blocks(project,delta):
    """Extend/trim at the end on the musical grid, without moving existing events."""
    engine.validate(project,require_source=False)
    bar=240/project['bpm'];count=math.ceil(project['duration']/bar-1e-8)
    return resize_duration(project,(count+delta)*bar)


def resize_duration(project,duration):
    engine.number(duration,4,480,'作品时长（4–480 秒）')
    if any(a['time']+a.get('hold',2.)>duration+1e-8 for a in project['anchors']):
        raise ValueError('缩短会截掉固定记忆点，请先移动或删除该记忆点。')
    if any(v['end']>duration+1e-8 for v in project['overrides']):
        raise ValueError('缩短会截掉手动修改块，请先撤销或调整对应修改。')
    result=copy.deepcopy(project);result['duration']=duration;clipped=[]
    for v in result['curve']:
        if v['start']>=duration:continue
        if v['end']>duration:
            fraction=(duration-v['start'])/(v['end']-v['start'])
            v['end_level']=v['level']+(v.get('end_level',v['level'])-v['level'])*fraction
            v['end']=duration
        clipped.append(v)
    result['curve']=clipped
    return normalize(result)


def default_story(project=None):
    result=copy.deepcopy(project if project is not None else engine.new_project())
    result.pop('intensity_points',None)
    bar=240/result['bpm'];cursor=0;curve=[]
    for emotion,count,level in DEFAULT_STORY:
        curve.append(dict(start=cursor*bar,end=(cursor+count)*bar,emotion=emotion,level=level,end_level=level))
        cursor+=count
    result.update(duration=cursor*bar,curve=curve,auto_peak_memory=True)
    return normalize(result)


def is_default_story(project):
    if project['anchors'] or project['overrides']:return False
    if project.get('intensity_points'):
        base=dict(project);base.pop('intensity_points')
        if engine.intensity_curve.controls(project)!=engine.intensity_curve.controls(base):return False
    expected=default_story(dict(project,anchors=[],overrides=[]))
    if abs(project['duration']-expected['duration'])>1e-6 or len(project['curve'])!=len(expected['curve']):return False
    return all(a['emotion']==b['emotion'] and all(abs(a.get(k,a['level'])-b[k])<1e-6 for k in ('start','end','level','end_level'))
               for a,b in zip(project['curve'],expected['curve']))


def grid_seconds(project):
    rate=project['bpm']*engine.PPQ/60
    grid=[t/rate for t in engine.block_grid(project)]
    exact={round(a['time']*rate/10)*10:a['time'] for a in project['anchors']}
    exact.update({round((a['time']+a.get('hold',2.))*rate/10)*10:a['time']+a.get('hold',2.) for a in project['anchors']})
    grid=[exact.get(round(t*rate/10)*10,t) for t in grid]
    grid[-1]=project['duration']
    return grid


def normalize(project):
    """Project every emotion onto whole operational blocks; fill the entire duration."""
    engine.validate(project,require_source=False)
    result=copy.deepcopy(project);result['block_aligned']=True
    old=sorted(project['curve'],key=lambda v:v['start']);regions=[]
    grid=grid_seconds(project)
    for start,end in zip(grid,grid[1:]):
        middle=(start+end)/2
        value=next((v for v in old if v['start']<=middle<v['end']),None)
        if value:
            delta=value.get('end_level',value['level'])-value['level'];span=value['end']-value['start']
            a=value['level']+delta*max(0,min(1,(start-value['start'])/span))
            b=value['level']+delta*max(0,min(1,(end-value['start'])/span))
        else:
            preceding=[v for v in old if v['end']<=middle]
            value=preceding[-1] if preceding else (old[0] if old else dict(emotion='calm',level=.25))
            a=b=value.get('end_level',value['level']) if preceding else value['level']
        item=dict(value,start=start,end=end,level=a,end_level=b)
        if regions:
            prev=regions[-1];slope=(b-a)/(end-start);prior=(prev['end_level']-prev['level'])/(prev['end']-prev['start'])
            if prev['emotion']==item['emotion'] and prev.get('source_id')==item.get('source_id') and abs(prev['end_level']-a)<1e-8 and abs(slope-prior)<1e-8:
                prev.update(end=end,end_level=b);continue
        regions.append(item)
    result['curve']=regions
    if result.get('continuous_intensity'):
        result['intensity_points']=engine.intensity_curve.controls(result)
    engine.validate(result,require_source=False)
    return result


def snapped_range(project,start,end):
    grid=grid_seconds(project);start,end=sorted((start,end))
    a=min(range(len(grid)),key=lambda i:abs(grid[i]-start))
    b=min(range(len(grid)),key=lambda i:abs(grid[i]-end))
    if a==b:
        a=max(0,min(len(grid)-2,a));b=a+1
    return grid[a],grid[b]


def paint_blocks(project,start,end,emotion,level,end_level):
    project=normalize(project);start,end=snapped_range(project,start,end)
    return normalize(paint(project,start,end,emotion,level,end_level))


def resize_boundary(project,index,time):
    """Move one shared edge, never detach its two neighboring regions."""
    result=copy.deepcopy(project);regions=result['curve']
    if not 0<=index<len(regions)-1:raise ValueError('作品起点和终点固定，只能拖动内部边界。')
    left,right=regions[index:index+2]
    options=[v for v in grid_seconds(project) if left['start']+1e-8<v<right['end']-1e-8]
    if not options:raise ValueError('相邻情绪段至少各保留一个完整块。')
    point=min(options,key=lambda v:abs(v-time));left['end']=point;right['start']=point
    return normalize(result)


def move_filled_region(project,index,delta):
    regions=project['curve']
    if len(regions)==1:return copy.deepcopy(project)
    if index==0:return resize_boundary(project,0,regions[0]['end']+delta)
    if index==len(regions)-1:return resize_boundary(project,index-1,regions[index]['start']+delta)
    result=copy.deepcopy(project);grid=grid_seconds(project)
    a=min(range(len(grid)),key=lambda i:abs(grid[i]-regions[index]['start']))
    b=min(range(len(grid)),key=lambda i:abs(grid[i]-regions[index]['end']))
    width=b-a;low=regions[index-1]['start'];high=regions[index+1]['end']
    options=[i for i in range(len(grid)-width) if grid[i]>low+1e-8 and grid[i+width]<high-1e-8]
    if not options:raise ValueError('相邻情绪段至少各保留一个完整块。')
    target=min(options,key=lambda i:abs(grid[i]-regions[index]['start']-delta))
    left,right=grid[target],grid[target+width]
    result['curve'][index].update(start=left,end=right)
    result['curve'][index-1]['end']=left;result['curve'][index+1]['start']=right
    return normalize(result)


def remove_region(project,index):
    result=copy.deepcopy(project);regions=result['curve'];removed=regions.pop(index)
    if regions:
        if index:regions[index-1]['end']=removed['end']
        else:regions[0]['start']=0
    return normalize(result)


def paint(project,start,end,emotion,level,end_level):
    result=copy.deepcopy(project)
    start,end=sorted((max(0,min(project['duration'],start)),max(0,min(project['duration'],end))))
    if end-start<.1:raise ValueError('请拖出一段范围，或使用“整段应用”。')
    regions=[];existing=result['curve']
    for v in existing:
        if v['end']<=start or v['start']>=end:regions.append(copy.deepcopy(v));continue
        for a,b in ((v['start'],start),(end,v['end'])):
            if b-a>=.1:
                delta=v.get('end_level',v['level'])-v['level'];span=v['end']-v['start']
                regions.append(dict(v,start=a,end=b,level=v['level']+delta*(a-v['start'])/span,end_level=v['level']+delta*(b-v['start'])/span))
    # Coloring changes expression independently of an explicitly chosen melody.
    # Keep source boundaries and interpolate the new ramp across the whole stroke.
    source_regions=[v for v in existing if v.get('source_id') and v['start']<end and v['end']>start]
    cuts={start,end}
    for v in source_regions:cuts.update((max(start,v['start']),min(end,v['end'])))
    cuts=sorted(cuts);painted=[]
    for a,b in zip(cuts,cuts[1:]):
        midpoint=(a+b)/2
        source_id=next((v['source_id'] for v in source_regions if v['start']<=midpoint<v['end']),None)
        first=level+(end_level-level)*(a-start)/(end-start)
        last=level+(end_level-level)*(b-start)/(end-start)
        if painted and painted[-1].get('source_id')==source_id:
            painted[-1].update(end=b,end_level=last)
        else:
            value=dict(start=a,end=b,emotion=emotion,level=first,end_level=last)
            if source_id is not None:value['source_id']=source_id
            painted.append(value)
    regions.extend(painted)
    result['curve']=sorted(regions,key=lambda v:v['start'])
    engine.validate(result,require_source=False)
    return result


def put_anchor(project,time,emotion,level):
    result=copy.deepcopy(project);time=round(max(0,min(project['duration']-.1,time)),2)
    existing=next((a for a in result['anchors'] if a['time']<=time<a['time']+a.get('hold',2)),None)
    if existing:existing.update(emotion=emotion,level=level)
    else:
        following=min([a['time'] for a in result['anchors'] if a['time']>time]+[project['duration']])
        result['anchors'].append(dict(time=time,hold=min(2.,following-time),emotion=emotion,level=level))
    engine.validate(result,require_source=False)
    return result
