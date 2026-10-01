"""Reorder filled emotion regions while retaining the musical time grid."""
import copy
import emotion_input
import intensity_curve
import story_engine as engine


def clear_overrides(project,start,end):
    """Clear only this time range, preserving the outside parts of local edits."""
    engine.validate(project,require_source=False)
    engine.number(start,0,project['duration'],'清除区间起点')
    engine.number(end,0,project['duration'],'清除区间终点')
    if start>=end:raise ValueError('清除区间终点必须晚于起点。')
    result=copy.deepcopy(project);retained=[]
    for value in result['overrides']:
        if value['end']<=start or value['start']>=end:
            retained.append(value);continue
        delta=value.get('end_level',value['level'])-value['level']
        span=value['end']-value['start']
        for left,right in ((value['start'],min(value['end'],start)),
                           (max(value['start'],end),value['end'])):
            if right<=left:continue
            if right-left<.1-1e-8:
                raise ValueError('清除后剩余修改块不足 0.1 秒，请调整清除范围。')
            retained.append(dict(value,start=left,end=right,
                                 level=value['level']+delta*(left-value['start'])/span,
                                 end_level=value['level']+delta*(right-value['start'])/span))
    result['overrides']=retained
    engine.validate(result,require_source=False)
    return result


def reorder(project,index,target):
    """Target is the new region index. Anchors/overrides lock crossed regions."""
    regions=project['curve']
    if not 0<=index<len(regions) or not 0<=target<len(regions):
        raise ValueError('请选择有效的积木位置。')
    if index==target:return copy.deepcopy(project)
    first,last=sorted((index,target));start=regions[first]['start'];end=regions[last]['end']
    locked=[(a['time'],a['time']+a.get('hold',2.)) for a in project['anchors']]
    locked.extend((v['start'],v['end']) for v in project['overrides'])
    if any(a<end-1e-8 and b>start+1e-8 for a,b in locked):
        raise ValueError('这里有固定记忆点或手动修改块，请先解除固定再移动。')
    # A shortened final block stays at the end; moving it would break beat alignment.
    bar=240/project['bpm']
    for region in regions[first:last+1]:
        count=(region['end']-region['start'])/bar
        if abs(count-round(count))>1e-6:
            raise ValueError('尾部不足四拍的积木保留在原位，请先调整长度。')
    result=copy.deepcopy(project);order=list(range(len(regions)))
    order.insert(target,order.pop(index));points=[]
    old_points=intensity_curve.controls(project)
    result['curve']=[];cursor=0.
    for original in order:
        old=regions[original];span=old['end']-old['start']
        result['curve'].append(dict(old,start=cursor,end=cursor+span))
        for point in old_points:
            if old['start']<=point['time']<old['end']:
                points.append(dict(time=cursor+point['time']-old['start'],level=point['level']))
        cursor+=span
    if project.get('continuous_intensity') or project.get('intensity_points'):
        result['intensity_points']=sorted(points,key=lambda p:p['time'])
    return emotion_input.normalize(result)


def insertion_index(project,index,time):
    remaining=[r for i,r in enumerate(project['curve']) if i!=index]
    return sum(time>(r['start']+r['end'])/2 for r in remaining)
