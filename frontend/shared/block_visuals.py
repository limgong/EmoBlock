"""Resolution-independent toy-block surfaces and short nonblocking motion."""
import time
from ui_hints import rounded
from ui_theme import color


def mix(shade,target,amount):
    a=[int(shade[i:i+2],16) for i in (1,3,5)];b=[int(target[i:i+2],16) for i in (1,3,5)]
    return '#'+''.join(f'{round(x+(y-x)*amount):02x}' for x,y in zip(a,b))


def brick(canvas,left,top,right,bottom,shade,selected=False,lift=0,tags=()):
    top-=lift;bottom-=lift;radius=10
    rounded(canvas,left+1,top+5+lift/2,right+1,bottom+5+lift/2,color('shadow'),tags=tags,radius=radius)
    rounded(canvas,left,top,right,bottom,shade,color('ink') if selected else mix(shade,'#000000',.14),2 if selected else 1,tags=tags,radius=radius)
    if right-left>14:
        canvas.create_line(left+7,top+3,right-7,top+3,fill=mix(shade,'#ffffff',.42),width=2,tags=tags)
        canvas.create_line(left+7,bottom-2,right-7,bottom-2,fill=mix(shade,'#000000',.16),width=3,tags=tags)


class BlockMotion:
    def __init__(self,widget,redraw):
        self.widget=widget;self.redraw=redraw;self.positions={};self.target={};self.origin={};self.started=0;self.timer=None
        widget.bind('<Destroy>',lambda event:self.cancel() if event.widget is widget else None,add='+')

    def boxes(self,targets,animate):
        now=time.perf_counter()
        if targets!=self.target:
            self.origin=dict(self.positions);self.target=targets;self.started=now if animate else now-1
        t=min(1,(now-self.started)/.16);ease=1-(1-t)**3
        self.positions={key:tuple(a+(b-a)*ease for a,b in zip(self.origin.get(key,value),value)) for key,value in targets.items()}
        if t<1 and self.timer is None:self.timer=self.widget.after(16,self.tick)
        return self.positions

    def tick(self):
        self.timer=None
        if self.widget.winfo_exists():self.redraw()

    def cancel(self):
        if self.timer is not None:
            self.widget.after_cancel(self.timer);self.timer=None
        self.positions={};self.target={};self.origin={}
