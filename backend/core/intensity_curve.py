"""Dependency-free monotone cubic Hermite interpolation of block-center controls."""
import bisect
import math


def controls(project):
    if project.get('schema')=='emoblocks.assembly.v1' or project.get('assembly_mode'):return [dict(p) for p in project.get('intensity_points',[])]
    bar=240/project['bpm'];duration=project['duration'];stored=project.get('intensity_points',[])
    points=[];start=0.
    while start<duration-1e-8:
        end=min(duration,start+bar);time=(start+end)/2
        old=next((p for p in stored if abs(p['time']-time)<1e-6),None)
        if old:level=old['level']
        elif stored:level=evaluate(stored,time)
        else:
            region=next((v for v in project['curve'] if v['start']<=time<v['end']),None)
            level=(region['level']+(region.get('end_level',region['level'])-region['level'])*(time-region['start'])/(region['end']-region['start'])) if region else .25
        points.append(dict(time=time,level=level));start=end
    return points


def evaluate(points,time):
    if not points:return .25
    if time<=points[0]['time']:return points[0]['level']
    if time>=points[-1]['time']:return points[-1]['level']
    x=[p['time'] for p in points];y=[p['level'] for p in points]
    h=[b-a for a,b in zip(x,x[1:])];d=[(b-a)/w for a,b,w in zip(y,y[1:],h)]
    # Flat endpoint extensions, and harmonic-mean interior slopes: no overshoot.
    slopes=[0.]*len(points)
    for i in range(1,len(points)-1):
        if d[i-1]*d[i]>0:
            w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1]
            slopes[i]=(w1+w2)/(w1/d[i-1]+w2/d[i])
    i=bisect.bisect_right(x,time)-1;t=(time-x[i])/h[i]
    return max(0.,min(1.,(2*t**3-3*t*t+1)*y[i]+(t**3-2*t*t+t)*h[i]*slopes[i]+(-2*t**3+3*t*t)*y[i+1]+(t**3-t*t)*h[i]*slopes[i+1]))


def level_at(project,time):return evaluate(controls(project),time)


def validate(project):
    previous=-1.
    for p in project.get('intensity_points',[]):
        t=p['time'];v=p['level']
        if not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (t,v)) or t<=previous or t<0 or not 0<=v<=1:
            raise ValueError('程度曲线控制点无效。')
        previous=t
