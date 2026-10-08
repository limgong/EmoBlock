"""Static root-overlay ghost and cached detached transaction checks."""
import copy
import tkinter as tk
from curve_visuals import TYPE_COLORS,DATA_INK,material_type,stable_number,draw_notes,brick
from curve_theme import font,EMOTION_COLORS,EMOTION_NAMES
from curve_raster import pixels


class DragGhost(tk.Canvas):
    def __init__(self,app):
        self.app=app;self.target=None;self.memo={};self.material=None
        super().__init__(app.root,width=pixels(app.root,208),height=pixels(app.root,76),highlightthickness=0,takefocus=False)

    def check(self,action,**args):
        key=(self.app.input_key(),action,tuple(sorted(args.items())))
        if key not in self.memo:
            self.memo.clear()
            query=getattr(self.app.controller,'preview_edit',None)
            self.memo[key]=query(action,**args) if query else dict(allowed=None,changed=None,error=None)
        return self.memo[key]

    def show(self,material,x_root,y_root,result=None,text=None,offset=None,emotion=None):
        self.material=copy.deepcopy(material)
        p=self.app.theme.colors;self.configure(bg=p['panel']);self.delete('all')
        timeline=self.app.page.timeline
        inside=timeline.contains_root(x_root,y_root)
        w=max(4,round(material['length_ticks']*timeline.scale)) if inside or offset is not None else pixels(self.app.root,208)
        h=pixels(self.app.root,76);body=pixels(self.app.root,56)
        allowed=(result or {}).get('allowed')
        ink=p['error'] if allowed is False else p['accent']
        face=EMOTION_COLORS[emotion or 'calm'] if inside or emotion else TYPE_COLORS[material_type(material,self.app.state_data['project']['materials'])]
        brick(self,(1,1,max(2,w-2),body),face,self.app.theme,True,tags='ghost-body')
        self.create_rectangle(1,1,max(2,w-2),body,outline=ink,width=1,tags='ghost-state')
        label=stable_number(material)+(' · '+EMOTION_NAMES[emotion or 'calm'] if inside or emotion else '')
        if w>pixels(self.app.root,30):
            self.create_text(8,7,anchor='nw',text=self.fit(label,w-16),fill=DATA_INK,font=font(11,True))
            draw_notes(self,(8,28,w-8,body-7),material['notes'],0,material['length_ticks'],DATA_INK,stroke=3,tags='ghost-note')
        message=text or ((result or {}).get('error') or {}).get('message') or ''
        if message and w>pixels(self.app.root,60):self.create_text(4,h-9,anchor='w',text=self.fit(('⊘ ' if allowed is False else '')+message,w-8),fill=p['error'] if allowed is False else p['ink'],font=font(9))
        root=self.app.root
        offset=offset or (w/2,body/2)
        self.grab_offset=offset
        x=x_root-root.winfo_rootx()-offset[0]
        y=y_root-root.winfo_rooty()-offset[1]
        self.place(x=x,y=y,width=w,height=h);self.tk.call('raise',self._w)

    def fit(self,text,width):
        from tkinter.font import Font
        measure=Font(root=self,font=font(11,True)).measure
        value=text
        while value and measure(value+('…' if value!=text else ''))>width:value=value[:-1]
        return value+('…' if value and value!=text else '')

    def clear(self):self.place_forget();self.memo.clear();self.material=None
