"""One fixed tick canvas. P2 displays strength; only placements are editable."""
import math
import tkinter as tk
from tkinter import ttk
import intensity_curve
from curve_theme import rounded, font, EMOTION_COLORS, EMOTION_NAMES, EMOTION_INK


def snap_tick(tick):
    return math.floor((tick + 240) / 480) * 480


class CurveCanvas(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Curve.Panel.TFrame')
        self.app = app
        self.project = None
        self.selected_id = None
        self.scale = .085
        self.margin = 36
        self.boxes = {}
        self.drag = None
        self.preview = None
        self.edge_timer = None
        self.canvas = tk.Canvas(self, height=380, highlightthickness=0, takefocus=True, xscrollincrement=1)
        self.canvas.pack(fill='both', expand=True)
        self.scrollbar = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.scrollbar.pack(fill='x')
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        for event, handler in (('<Configure>', self.draw), ('<ButtonPress-1>', self.press),
                               ('<B1-Motion>', self.motion), ('<ButtonRelease-1>', self.release),
                               ('<Escape>', self.cancel), ('<Delete>', self.delete_selected)):
            self.canvas.bind(event, handler)
        self.bind('<Destroy>', self.destroyed, add='+')

    def set_project(self, project):
        self.project = project
        if not project or self.selected_id not in {p['id'] for p in project['placements']}:
            self.selected_id = None
        self.draw()

    def x(self, tick):
        return self.margin + tick * self.scale

    def tick(self, canvas_x):
        return (canvas_x - self.margin) / self.scale

    def level(self, tick):
        return intensity_curve.evaluate([dict(time=p['tick'],level=p['level'])
                                         for p in self.project['intensity_points']], tick)

    def y(self, level):
        height = max(210, self.canvas.winfo_height())
        return 56 + (1-level) * (height-122)

    def draw(self, event=None):
        c = self.canvas
        p = self.app.theme.colors
        view = c.xview()[0]
        c.configure(bg=p['panel'])
        c.delete('all')
        self.boxes = {}
        if self.project is None:
            c.configure(scrollregion=(0,0,max(1,c.winfo_width()),max(1,c.winfo_height())))
            c.create_text(24,80,anchor='nw',text='旧工程只读 · 请选择已有成品试听或导出',fill=p['muted'],font=font())
            return
        total = self.project['total_ticks']
        height = max(210, c.winfo_height())
        width = max(c.winfo_width(), self.x(total)+self.margin)
        c.configure(scrollregion=(0,0,width,height))
        for level in (0., .25, .5, .75, 1.):
            y = self.y(level)
            c.create_line(self.margin,y,self.x(total),y,fill=p['inset'])
            c.create_text(24,y,text=f'{level:g}',fill=p['muted'],font=font(8))
        for tick in range(0,total+1,480):
            x = self.x(tick)
            c.create_line(x,40,x,height-36,fill=p['line'] if tick%1920==0 else p['inset'])
            if tick%1920==0:
                c.create_text(x,22,anchor='w',text=f'{tick//1920+1:02}',fill=p['muted'],font=font(9))
        for blank in self.project['blank_regions']:
            a,b = self.x(blank['start_tick']),self.x(blank['end_tick'])
            c.create_rectangle(a,45,b,height-37,fill=p['inset'],outline=p['line'],dash=(3,3))
            c.create_text((a+b)/2,height-48,text='主动留白',fill=p['muted'],font=font(8))
        occupied = sorted([(v['start_tick'],v['start_tick']+v['length_ticks']) for v in self.project['placements']]
                          + [(v['start_tick'],v['end_tick']) for v in self.project['blank_regions']])
        cursor = 0
        for a,b in occupied+[(total,total)]:
            if a>cursor:
                c.create_text((self.x(cursor)+self.x(a))/2,height-48,text='待补全',fill=p['muted'],font=font(8))
            cursor = b
        coords = []
        for tick in range(0,total+1,max(1,total//400)):
            coords.extend((self.x(tick), self.y(self.level(tick))))
        coords.extend((self.x(total),self.y(self.level(total))))
        if coords:
            c.create_line(*coords,fill=p['muted'],width=2,tags='strength')
        for placement in self.project['placements']:
            a,b = self.x(placement['start_tick']), self.x(placement['start_tick']+placement['length_ticks'])
            center = self.y(self.level(placement['start_tick']+placement['length_ticks']/2))
            box = (a,center-28,b,center+28)
            self.boxes[placement['id']] = box
            if self.app.theme.name=='light':
                rounded(c,(a+2,center-25,b+2,center+31),p['shadow'])
            rounded(c,box,EMOTION_COLORS[placement['emotion']],p['accent'] if placement['id']==self.selected_id else p['line'])
            if b-a >= 52:
                label = placement['base_snapshot']['label']
                limit = max(2,int((b-a-24)/17))
                c.create_text(a+12,center-8,anchor='w',text=label[:limit]+('…' if len(label)>limit else ''),
                              fill=EMOTION_INK,font=font())
                c.create_text(a+12,center+13,anchor='w',text=EMOTION_NAMES[placement['emotion']],fill=EMOTION_INK,font=font(10))
        if self.preview:
            start,length = self.preview
            center = self.y(self.level(start+length/2))
            c.create_rectangle(self.x(start),center-25,self.x(start+length),center+25,
                               outline=p['accent'],width=1,dash=(4,3),tags='drop-preview')
        c.create_text(self.margin,height-16,anchor='w',text='强度只读 · 按拍拖放 · 移动不搬动强度线',fill=p['muted'],font=font(8))
        c.xview_moveto(view)

    def contains_root(self, x_root, y_root):
        c = self.canvas
        return c.winfo_rootx()<=x_root<c.winfo_rootx()+c.winfo_width() and c.winfo_rooty()<=y_root<c.winfo_rooty()+c.winfo_height()

    def root_tick(self, x_root, offset_px=0):
        return self.tick(self.canvas.canvasx(x_root-self.canvas.winfo_rootx())-offset_px)

    def hit(self, x, y):
        return next((ident for ident,(a,t,b,d) in reversed(list(self.boxes.items())) if a<=x<=b and t<=y<=d),None)

    def press(self, event):
        self.cancel()
        self.canvas.focus_set()
        x,y = self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        ident = self.hit(x,y)
        self.selected_id = ident
        if ident:
            self.app.select_target('placement', ident)
            placement = next(p for p in self.project['placements'] if p['id']==ident)
            self.app.show_detail(placement['base_snapshot']['label']+' · 点击仅选择；拖动移动，Delete 删除')
            if self.app.editable:
                self.drag = dict(id=ident,start_root=(event.x_root,event.y_root),
                                 offset=x-self.x(placement['start_tick']),length=placement['length_ticks'],active=False)
        self.draw()

    def motion(self, event):
        if not self.drag:
            return
        d = self.drag
        if not d['active']:
            if max(abs(event.x_root-d['start_root'][0]),abs(event.y_root-d['start_root'][1]))<5:
                return
            d['active'] = True
            self.canvas.grab_set()
        self.preview = (snap_tick(self.root_tick(event.x_root,d['offset'])),d['length'])
        self.edge_scroll(event.x_root,event.y_root)
        self.draw()

    def release(self, event):
        if not self.drag:
            return
        d = self.drag.copy()
        raw = self.root_tick(event.x_root,d['offset'])
        inside = self.contains_root(event.x_root,event.y_root)
        self.cancel()
        if not d['active']:
            return
        if not inside or raw<0 or raw+d['length']>self.project['total_ticks']:
            self.app.tell('移动已取消：落点超出时间轴。',True)
            return
        self.app.edit('move',placement_id=d['id'],start_tick=snap_tick(raw))

    def edge_scroll(self, x_root, y_root):
        self.edge_pointer = (x_root,y_root)
        if self.edge_timer is None:
            self.edge_timer = self.after(60,self._edge_step)

    def _edge_step(self):
        self.edge_timer = None
        x,y = self.edge_pointer
        if not self.contains_root(x,y):
            return
        local = x-self.canvas.winfo_rootx()
        direction = -1 if local<28 else 1 if local>self.canvas.winfo_width()-28 else 0
        if direction:
            self.canvas.xview_scroll(direction*18,'units')
            if self.drag and self.drag['active']:
                self.preview = (snap_tick(self.root_tick(x,self.drag['offset'])),self.drag['length'])
            elif self.app.material_drag and self.app.material_drag['active']:
                d = self.app.material_drag
                self.preview = (snap_tick(self.root_tick(x,d['offset'])),d['material']['length_ticks'])
            self.draw()
            self.edge_timer = self.after(60,self._edge_step)

    def cancel(self, event=None):
        if self.edge_timer is not None:
            self.after_cancel(self.edge_timer)
            self.edge_timer = None
        self.drag = None
        self.preview = None
        if self.canvas.grab_current()==self.canvas:
            self.canvas.grab_release()
        self.draw()
        return 'break' if event else None

    def delete_selected(self, event=None):
        if self.selected_id and self.app.editable:
            self.app.edit('delete',placement_id=self.selected_id)
        return 'break'

    def destroyed(self, event):
        if event.widget==self and self.edge_timer is not None:
            self.after_cancel(self.edge_timer)
            self.edge_timer = None
