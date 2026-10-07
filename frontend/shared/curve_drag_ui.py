"""Static root-overlay ghost and cached detached transaction checks."""
import copy
import tkinter as tk
from curve_visuals import TYPE_COLORS,DATA_INK,material_type,stable_number,draw_notes
from curve_theme import rounded,font
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

    def show(self,material,x_root,y_root,result=None,text=None):
        self.material=copy.deepcopy(material)
        p=self.app.theme.colors;self.configure(bg=p['panel']);self.delete('all')
        w,h=pixels(self.app.root,208),pixels(self.app.root,76)
        allowed=(result or {}).get('allowed')
        ink=p['error'] if allowed is False else p['accent']
        face=TYPE_COLORS[material_type(material,self.app.state_data['project']['materials'])]
        rounded(self,(1,1,w-2,h-2),face,ink)
        self.create_text(8,7,anchor='nw',text=stable_number(material),fill=DATA_INK,font=font(11,True))
        draw_notes(self,(8,28,w-8,h-25),material['notes'],0,material['length_ticks'],DATA_INK,tags='ghost-note')
        message=text or ((result or {}).get('error') or {}).get('message') or ('可放置' if allowed else '释放时核对落点')
        self.create_text(8,h-15,anchor='w',text=self.app.compact(message,w-16),fill=DATA_INK,font=font(10))
        root=self.app.root
        x=max(0,min(root.winfo_width()-w,x_root-root.winfo_rootx()+pixels(root,18)))
        y=max(0,min(root.winfo_height()-h,y_root-root.winfo_rooty()+pixels(root,18)))
        self.place(x=x,y=y,width=w,height=h);self.tk.call('raise',self._w)

    def clear(self):self.place_forget();self.memo.clear();self.material=None
