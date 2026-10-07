"""One fixed tick canvas with local intensity drafts and Facade transactions."""
import copy
import importlib
import math
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import intensity_curve
import ui_platform
from curve_theme import rounded, font, hint, EMOTION_COLORS, EMOTION_NAMES, EMOTION_INK


def snap_tick(tick):
    return math.floor((tick + 240) / 480) * 480


def _normalize_trace(points, total_ticks):
    return importlib.import_module('curve_memory').normalize_trace(points,total_ticks,tolerance=.02)


class CurveCanvas(ttk.Frame):
    def __init__(self, parent, app, stage_parent=None):
        super().__init__(parent, style='Curve.Panel.TFrame')
        self.app = app
        self.project = None
        self.readonly = False
        self.view_memory_info = None
        self.bridge_preview = None
        self.connection_preview = None
        self.recommendation_preview = None
        self.accepted_music = None
        self.boundary_boxes = {}
        self.accepted_bridge_boxes = {}
        self.range_badges = []
        self.range_badge_targets = {}
        self.bridge_boxes = {}
        self.connection_boxes = {}
        self.selected_bridge_id = None
        self.selected_connection_id = None
        self.selected_id = None
        self.scale = .085
        self.margin = 36
        self.boxes = {}
        self.drag = None
        self.preview = None
        self.edge_timer = None
        self.intensity_draft = None
        self.point_boxes = []
        self.gap_boxes = {}
        self.mode = 'points'
        tools = self.tools = ttk.Frame(self,style='Curve.Panel.TFrame')
        tools.pack(fill='x',pady=(0,4))
        self.mode_buttons = {}
        for mode,text in (('arrange','编排'),('points','控制点'),('trace','手绘'),('gaps','选空缺')):
            button = ttk.Button(tools,text=text,width=0,style='Curve.TButton',command=lambda m=mode:self.set_mode(m))
            if mode!='gaps':button.pack(side='left',padx=(0,4))
            self.mode_buttons[mode] = button
        hint(self.mode_buttons['points'],'点击空白添加控制点；拖动控制点调整时间与强度，Esc 取消。',app.show_detail)
        hint(self.mode_buttons['trace'],'局部手绘保留区外控制点；释放一次提交，Esc 或拖出取消。',app.show_detail)
        hint(self.mode_buttons['gaps'],'只选择后端查询的精确空缺；默认补全全部，点击不会计算或播放。',app.show_detail)
        self.all_gaps_button = ttk.Button(tools,text='全部空缺',width=0,style='Curve.TButton',
            command=lambda:app.completion.select_gap(None))
        self.all_gaps_button.pack(side='left')
        self.stage_choice = tk.StringVar(value='补全')
        self.stage_selector = ttk.Combobox(stage_parent if stage_parent is not None else tools,textvariable=self.stage_choice,
            values=('补全','Bridge','连接','完整建议'),state='readonly',width=7,style='Curve.TCombobox')
        self.stage_selector.bind('<<ComboboxSelected>>',lambda _:app.show_curve_stage(self.stage_choice.get()))
        hint(self.stage_selector,'分阶段折叠：补全、Bridge、连接和完整建议共用唯一画布；切换不会修改工程或播放对象。',app.show_detail)
        self.canvas = tk.Canvas(self, height=380, highlightthickness=0, takefocus=True, xscrollincrement=1)
        self.canvas.pack(fill='both', expand=True)
        self.scrollbar = ttk.Scrollbar(self,style='Curve.Horizontal.TScrollbar', orient='horizontal', command=self.canvas.xview)
        self.scrollbar.pack(fill='x')
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        self.empty_import=ttk.Button(self.canvas,text='导入旋律，开始创作',style='Curve.Primary.TButton',command=lambda:app.safe(app.import_file))
        self.canvas.bind('<Motion>',self.hover)
        for event, handler in (('<Configure>', self.draw), ('<ButtonPress-1>', self.press),
                               ('<B1-Motion>', self.motion), ('<ButtonRelease-1>', self.release),
                               ('<Escape>', self.cancel)):
            self.canvas.bind(event, handler)
        for event in ui_platform.DELETE_SHORTCUT_EVENTS:
            self.canvas.bind(event, self.delete_selected)
        self.bind('<Destroy>', self.destroyed, add='+')

    def set_project(self, project, readonly=False, memory_info=None, bridge_preview=None, connection_preview=None,
                    recommendation_preview=None, accepted_music=None):
        if self.intensity_draft and project!=self.project:
            self.cancel()
        self.project = project
        self.readonly = readonly
        self.view_memory_info = memory_info
        self.bridge_preview = bridge_preview
        self.connection_preview = connection_preview
        self.recommendation_preview = recommendation_preview
        self.accepted_music = accepted_music
        if not connection_preview or self.selected_connection_id not in {o['id'] for o in connection_preview['connection_overlays']}:
            self.selected_connection_id = None
        if not bridge_preview or self.selected_bridge_id not in {o['id'] for o in bridge_preview['overlays']}:
            self.selected_bridge_id = None
        if not project or self.selected_id not in {p['id'] for p in project['placements']}:
            self.selected_id = None
        self.draw()
        for mode,button in self.mode_buttons.items():
            button.configure(style='Curve.Primary.TButton' if mode==self.mode else 'Curve.TButton')
            enabled = not readonly and self.app.can_edit('edit' if mode=='arrange' else 'completion' if mode=='gaps' else 'intensity_edit')
            button.state(['!disabled'] if enabled else ['disabled'])
        self.all_gaps_button.state(['!disabled'] if not readonly and self.app.can_edit('completion') else ['disabled'])
        if self.app.state_data['capabilities'].get('connection',False) or self.app.state_data['capabilities'].get('recommendation',False):
            self.stage_selector.configure(values=('补全','Bridge','连接')+(
                ('完整建议',) if self.app.state_data['capabilities'].get('recommendation',False) else ()))
            self.stage_choice.set('完整建议' if self.app.recommendation.visible else '连接' if self.app.connection.visible else 'Bridge' if self.app.bridge.visible else '补全')
            self.stage_selector.pack(side='right') if self.app.advanced else self.stage_selector.pack_forget()
        else:self.stage_selector.pack_forget()

    def set_mode(self, mode):
        if self.readonly:return
        self.cancel()
        self.mode = mode
        self.draw()
        for value,button in self.mode_buttons.items():button.configure(style='Curve.Primary.TButton' if value==mode else 'Curve.TButton')

    def points(self):
        return self.intensity_draft['points'] if self.intensity_draft else self.project['intensity_points']

    def x(self, tick):
        return self.margin + tick * self.scale

    def tick(self, canvas_x):
        return (canvas_x - self.margin) / self.scale

    def level(self, tick):
        return intensity_curve.evaluate([dict(time=p['tick'],level=p['level'])
                                         for p in self.points()], tick)

    def y(self, level):
        return 36 + (1-level) * max(1,self.canvas.winfo_height()-80)

    def root_point(self, x_root, y_root):
        tick = min(self.project['total_ticks'],max(0,math.floor(self.root_tick(x_root)+.5)))
        y = self.canvas.canvasy(y_root-self.canvas.winfo_rooty())
        level = min(1.,max(0.,1-(y-36)/max(1,self.canvas.winfo_height()-80)))
        return dict(tick=tick,level=level)

    def draw(self, event=None):
        if event is not None and self.intensity_draft:
            self.cancel()
        c = self.canvas
        p = self.app.theme.colors
        view = c.xview()[0]
        c.configure(bg=p['panel'])
        c.delete('all')
        self.boxes = {}
        self.point_boxes = []
        self.gap_boxes = {}
        self.bridge_boxes = {}
        self.connection_boxes = {}
        self.boundary_boxes = {}
        self.accepted_bridge_boxes = {}
        self.range_badges = []
        self.range_badge_targets = {}
        if self.project is None:
            c.configure(scrollregion=(0,0,max(1,c.winfo_width()),max(1,c.winfo_height())))
            c.create_text(24,80,anchor='nw',text='旧工程只读 · 请选择已有成品试听或导出',fill=p['muted'],font=font())
            return
        total = self.project['total_ticks']
        height = max(1, c.winfo_height())
        width = max(c.winfo_width(), self.x(total)+self.margin)
        c.configure(scrollregion=(0,0,width,height))
        for level in (0., .25, .5, .75, 1.):
            y = self.y(level)
            c.create_line(self.margin,y,self.x(total),y,fill=p['inset'])
            c.create_text(24,y,text=f'{level*100:g}%',fill=p['muted'],font=font(8))
        for tick in range(0,total+1,480):
            x = self.x(tick)
            c.create_line(x,40,x,height-36,fill=p['line'] if tick%1920==0 else p['inset'])
            if tick%1920==0:
                c.create_text(x,22,anchor='w',text=f'{tick//1920+1}格 · {tick//480+1}拍',fill=p['muted'],font=font(9))
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
        completion = getattr(self.app,'completion',None)
        if completion and not self.readonly:
            for gap in completion.gaps:
                a,b = self.x(gap['start_tick']),self.x(gap['end_tick'])
                self.gap_boxes[gap['id']] = (a,45,b,height-37)
                selected = completion.selected_gap_id==gap['id']
                if self.mode=='gaps' or selected:
                    c.create_rectangle(a,45,b,height-37,outline=p['accent'] if selected else p['line'],
                                       width=1,dash=() if selected else (3,3),tags='gap-range')
        coords = []
        for tick in range(0,total+1,max(1,total//400)):
            coords.extend((self.x(tick), self.y(self.level(tick))))
        coords.extend((self.x(total),self.y(self.level(total))))
        if coords:
            c.create_line(*coords,fill=p['muted'],width=2,tags='strength')
        memory = self.memory_overlay()
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
                remembered = memory and memory[0]['placement_id']==placement['id']
                c.create_text(a+12,center+1 if remembered else center-8,anchor='w',text=label[:limit]+('…' if len(label)>limit else ''),
                              fill=EMOTION_INK,font=font())
                c.create_text(a+12,center+20 if remembered else center+13,anchor='w',text=EMOTION_NAMES[placement['emotion']],fill=EMOTION_INK,font=font(10))
        if self.preview:
            start,length = self.preview
            center = self.y(self.level(start+length/2))
            c.create_rectangle(self.x(start),center-25,self.x(start+length),center+25,
                               outline=p['accent'],width=1,dash=(4,3),tags='drop-preview')
        self.draw_connections()
        self.draw_memory()
        self.draw_bridges()
        self.draw_final_music()
        for index,point in enumerate(self.points()):
            x,y = self.x(point['tick']),self.y(point['level'])
            self.point_boxes.append((index,x,y))
            c.create_oval(x-6,y-6,x+6,y+6,fill=p['panel'],outline=p['accent'] if self.mode=='points' and not self.readonly else p['muted'],width=1,tags='control-point')
        text = ('手绘 · 释放提交，Esc 取消' if self.mode=='trace' else '控制点 · 点击添加，拖动调整')
        if self.mode in ('arrange','gaps'):text = '编排 · 拖放每拍吸附 · 选择空缺可仅生成此处方案'
        if not self.app.can_edit('intensity_edit'):text = '强度不可编辑'
        if self.readonly:text = '基础候选只读 · 尚未处理bridge与连接'
        if self.bridge_preview is not None:text = 'Bridge阶段只读 · 尚未处理连接与最终边界'
        if self.connection_preview is not None:text = '连接阶段只读 · 尚未最终块间处理'
        if self.recommendation_preview is not None:text = '完整建议只读 · 点击仅选择，明确播放/确认'
        elif self.accepted_music and self.accepted_music['derived_layers_status']=='STALE':text = '已接受派生层失效 · 固定Bridge保留'
        c.create_text(self.margin,height-16,anchor='w',text=text+' · 移动不搬动强度线',fill=p['muted'],font=font(8))
        c.xview_moveto(view)

    def draw_final_music(self):
        p = self.app.theme.colors
        preview = self.recommendation_preview
        music = preview if preview is not None else self.accepted_music
        if music is None:return
        if preview is None:
            for protection in music['protections']:
                if protection['kind']!='bridge' or protection['origin']!='automatic':continue
                start,end = protection['start_tick'],protection['end_tick']
                center = self.y(self.level((start+end)/2))
                box = (self.x(start),center-28,self.x(end),center+28)
                self.accepted_bridge_boxes[protection['id']] = box
                self.canvas.create_rectangle(*box,fill=p['selected'],outline=p['ink'],width=1,
                    dash=() if protection['status']=='CONTENT_READY' else (3,3),tags='accepted-bridge')
                if box[2]-box[0]>70:
                    self.canvas.create_text(box[0]+4,center-14,anchor='w',text='Bridge · 保护/只读',
                        fill=p['ink'],font=font(10),tags='accepted-bridge')
                else:
                    state = '音乐已就绪/保护' if protection['status']=='CONTENT_READY' else '范围已保护，音乐尚未就绪'
                    self.range_badge(box,'Bridge',p['ink'],'accepted-bridge',1,
                        f'已接受Bridge · {state} · {start}–{end} tick · 后续算法不得覆盖。')
        # The displayed note marks come exclusively from this authenticated layout.
        notes = music['notes']
        if notes:
            low,high = min(n['pitch'] for n in notes),max(n['pitch'] for n in notes)
            for note in notes:
                center = self.y(self.level(note['start_tick']))
                y = center+14-(note['pitch']-low)/max(1,high-low)*20
                start,end = self.x(note['start_tick']),self.x(note['start_tick']+note['duration_tick'])
                data_faces = [box for box in self.boxes.values() if box[1]<=y<=box[3]]
                stage_faces = [box for box in (*self.bridge_boxes.values(),*self.connection_boxes.values(),
                                              *self.accepted_bridge_boxes.values()) if box[1]<=y<=box[3]]
                edges = sorted({start,end,*[x for box in data_faces+stage_faces
                                            for x in (box[0],box[2]) if start<x<end]})
                for left,right in zip(edges,edges[1:]):
                    midpoint = (left+right)/2
                    data_face = any(box[0]<=midpoint<=box[2] for box in data_faces)
                    stage_face = any(box[0]<=midpoint<=box[2] for box in stage_faces)
                    # Emotion surfaces are data colors, while stage overlays use theme surfaces.
                    ink = EMOTION_INK if data_face and not stage_face else p['ink']
                    self.canvas.create_line(left,y,right,y,fill=ink,width=1,tags='final-note')
        if preview is not None:
            for overlay in preview['boundary_overlays']:
                x = self.x(overlay['tick'])
                self.boundary_boxes[overlay['id']] = (x-4,43,x+4,self.canvas.winfo_height()-38)
                self.canvas.create_line(x,43,x,self.canvas.winfo_height()-38,fill=p['accent'],dash=(2,4),tags='final-boundary')
                self.canvas.create_text(x+4,50,anchor='nw',text='边界',fill=p['ink'],font=font(9),tags='final-boundary')

    def hit_boundary(self, x, y):
        return next((ident for ident,(a,t,b,d) in reversed(list(self.boundary_boxes.items()))
                     if a<=x<=b and t<=y<=d),None)

    def hit_accepted_bridge(self, x, y):
        return next((ident for ident,(a,t,b,d) in reversed(list(self.accepted_bridge_boxes.items()))
                     if a-(.5 if b-a<1 else 0)<=x<=b+(.5 if b-a<1 else 0) and t<=y<=d),None)

    def final_detail(self, x, y):
        ident = self.hit_boundary(x,y)
        if ident:
            overlay = next(o for o in self.recommendation_preview['boundary_overlays'] if o['id']==ident)
            self.app.show_detail(self.app.recommendation.describe_overlay(overlay,'boundary'))
            return True
        ident = self.hit_accepted_bridge(x,y)
        if ident:
            protection = next(p for p in self.accepted_music['protections'] if p['id']==ident)
            state = '内容已就绪' if protection['status']=='CONTENT_READY' else '范围已保护，内容尚未就绪'
            self.app.show_detail(f'已接受Bridge · {state}\n范围 {protection["start_tick"]}–{protection["end_tick"]} tick\n'
                f'原保护计划 {protection["plan_id"]} v{protection["plan_version"]}\n'
                '后续算法不得覆盖；当前Bridge只读，不映射到底下的旧素材编辑。')
            return True
        return False

    def memory_overlay(self):
        info = self.view_memory_info if self.readonly else self.app.state_data['memory_info']
        if not info or (not self.readonly and not self.app.state_data['capabilities'].get('memory',False)) or info['state']!='BOUND':
            return None
        protections = self.bridge_preview['protections'] if self.bridge_preview is not None else self.project['protections']
        protection = next((p for p in protections if p['id']==info['protection_id']
                           and p['kind']=='memory' and p['placement_id']==info['placement_id']
                           and p['status']=='CONTENT_READY'),None)
        return info,protection

    def draw_bridges(self):
        colors = self.app.theme.colors
        if self.bridge_preview is None:
            for protection in self.project['protections']:
                if protection['kind']!='bridge' or protection['origin']!='manual':continue
                a,b = self.x(protection['start_tick']),self.x(protection['end_tick'])
                center = self.y(self.level((protection['start_tick']+protection['end_tick'])/2))
                box = (a,center-28,b,center+28)
                self.canvas.create_rectangle(*box,outline=colors['ink'],width=1,
                    dash=() if protection['status']=='CONTENT_READY' else (3,3),tags='manual-bridge-range')
                state = '音乐已就绪/保护' if protection['status']=='CONTENT_READY' else '范围已保护，音乐尚未就绪'
                detail = (f'手动Bridge · {state} · {protection["start_tick"]}–{protection["end_tick"]} tick\n'
                          '保护表示后续算法不得覆盖；用户仍可编辑。')
                if b-a>=70:
                    self.canvas.create_text(a+4,center-17,anchor='w',text='Bridge · 保护',
                        fill=EMOTION_INK,font=font(10,True),tags='manual-bridge-label')
                else:self.range_badge(box,'Bridge',colors['ink'],'manual-bridge-label',1,detail)
            return
        for overlay in self.bridge_preview['overlays']:
            region = overlay['range']
            a,b = self.x(region['start_tick']),self.x(region['end_tick'])
            center = self.y(self.level((region['start_tick']+region['end_tick'])/2))
            box = (a,center-28,b,center+28)
            self.bridge_boxes[overlay['id']] = box
            failed = overlay['result_status'] in ('FAILED','CANCELLED')
            ink = colors['error'] if failed else colors['ink']
            outline = colors['accent'] if overlay['id']==self.selected_bridge_id else ink
            # No fabricated placement/music: the rectangle is the backend's overlay range.
            self.canvas.create_rectangle(*box,fill=colors['selected'],
                outline=outline,width=1,dash=() if overlay['status']=='CONTENT_READY' else (3,3),tags='bridge-range')
            if b-a>=64:
                label = 'Bridge · '+('就绪/保护' if overlay['status']=='CONTENT_READY' else '范围保护')
                if failed:label += ' · '+('失败' if overlay['result_status']=='FAILED' else '取消')
                limit = max(3,int((b-a-8)/13))
                self.canvas.create_text(a+4,center-14,anchor='w',text=label[:limit]+('…' if len(label)>limit else ''),
                                        fill=ink,font=font(10,True),tags='bridge-label')
                material = overlay['material']
                if material:
                    self.canvas.create_text(a+4,center+10,anchor='w',text=material['label'][:limit],
                                            fill=colors['ink'],font=font(10),tags='bridge-label')
            else:self.range_badge(box,'Bridge',ink,'bridge-label',1,self.app.describe_bridge_overlay(overlay),
                ('bridge',overlay['id']))

    def hit_bridge(self, x, y):
        for ident,(a,t,b,d) in reversed(list(self.bridge_boxes.items())):
            pad = .5 if b-a<1 else 0
            if a-pad<=x<=b+pad and t<=y<=d:return ident
        return None

    def draw_connections(self):
        if self.connection_preview is None:return
        p = self.app.theme.colors
        for overlay in self.connection_preview['connection_overlays']:
            region = overlay['range']
            a,b = self.x(region['start_tick']),self.x(region['end_tick'])
            center = self.y(self.level((region['start_tick']+region['end_tick'])/2))
            box = (a,center-28,b,center+28)
            self.connection_boxes[overlay['id']] = box
            ready = overlay['status']=='CONTENT_READY'
            failed = overlay['result_status'] in ('FAILED','CANCELLED')
            ink = p['error'] if failed else p['ink']
            outline = p['accent'] if overlay['id']==self.selected_connection_id else ink
            self.canvas.create_rectangle(*box,fill=p['selected'],outline=outline,width=1,
                dash=() if ready else (4,3),tags='connection-range')
            if b-a>=72:
                label = '连接 · '+('就绪' if ready else '已分配')
                if failed:label += ' · '+('失败' if overlay['result_status']=='FAILED' else '取消')
                limit = max(3,int((b-a-8)/13))
                self.canvas.create_text(a+4,center-15,anchor='w',text=label[:limit]+('…' if len(label)>limit else ''),
                    fill=ink,font=font(10,True),tags='connection-label')
                if ready:
                    notes = overlay['notes']
                    low,high = min(n['pitch'] for n in notes),max(n['pitch'] for n in notes)
                    for note in notes:
                        y = center+20-(note['pitch']-low)/max(1,high-low)*22
                        self.canvas.create_line(self.x(note['start_tick']),y,
                            self.x(note['start_tick']+note['duration_tick']),y,fill=p['ink'],width=1,tags='connection-note')
            elif b-a>=18:
                self.canvas.create_text((a+b)/2,center,text='连',fill=ink,font=font(10),tags='connection-label')
            else:self.range_badge(box,'连',ink,'connection-label',2,self.app.describe_connection_overlay(overlay),
                ('connection',overlay['id']))

    def hit_connection(self, x, y):
        for ident,(a,t,b,d) in reversed(list(self.connection_boxes.items())):
            pad = .5 if b-a<1 else 0
            if a-pad<=x<=b+pad and t<=y<=d:return ident
        return None

    def draw_memory(self):
        overlay = self.memory_overlay()
        if not overlay:return
        info,protection = overlay
        region = protection or info['range']
        box = self.boxes.get(info['placement_id'])
        if not region or not box:return
        a,b = self.x(region['start_tick']),self.x(region['end_tick'])
        p = self.app.theme.colors
        self.canvas.create_rectangle(a,box[1]-3,b,box[3]+3,outline=p['ink'],width=1,
                                     dash=() if protection else (3,3),tags='memory-range')
        label = ('记忆' if protection else '记忆目标') if b-a>=70 else '忆'
        if b-a>=18:
            self.canvas.create_text(a+4,box[1]+3,anchor='nw',text=label,
                                    fill=EMOTION_INK,font=font(10,True),tags='memory-label')
        else:self.range_badge((a,box[1],b,box[3]),'忆',p['ink'],'memory-label',0,
            self.app.preview_memory_description() if self.readonly else self.app.memory_description())
        if protection:
            for note in protection['notes']:
                self.canvas.create_line(self.x(note['start_tick']),box[3]+7,
                                        self.x(note['start_tick']+note['duration_tick']),box[3]+7,
                                        fill=p['ink'],dash=(3,3),tags='memory-support')

    def range_badge(self, box, text, ink, tag, lane, detail, target=None):
        """Readable callout for a narrow exact range; never enlarge musical geometry."""
        c = self.canvas
        a,top,b,bottom = box
        left,right = c.canvasx(0),c.canvasx(c.winfo_width())
        if b<left or a>right:return
        x = max(left+4,min((a+b)/2+6,right-56))
        y = 44+lane*22
        label = c.create_text(x+3,y+2,anchor='nw',text=text,fill=ink,font=font(9,True),tags=tag)
        l,t,r,d = c.bbox(label)
        badge = (l-3,t-2,r+3,d+2)
        c.create_line((a+b)/2,top,(a+b)/2,y+8,x,y+8,fill=ink,width=1,tags=tag)
        surface = c.create_rectangle(*badge,fill=self.app.theme.colors['panel'],outline=ink,width=1,tags=tag)
        c.tag_raise(label,surface)
        self.range_badges.append((badge,detail))
        if target:self.range_badge_targets[badge] = target

    def badge_detail(self, x, y, select=False):
        for (a,t,b,d),detail in reversed(self.range_badges):
            if a<=x<=b and t<=y<=d:
                target = self.range_badge_targets.get((a,t,b,d))
                if select and target:
                    self.selected_bridge_id = target[1] if target[0]=='bridge' else None
                    self.selected_connection_id = target[1] if target[0]=='connection' else None
                self.app.show_detail(detail)
                return True
        return False

    def hover(self, event):
        if not self.project or self.drag or self.intensity_draft:return
        x,y = (self.canvas.canvasx(event.x_root-self.canvas.winfo_rootx()),
               self.canvas.canvasy(event.y_root-self.canvas.winfo_rooty()))
        if any(abs(x-a)<=10 and abs(y-b)<=10 for _,a,b in self.point_boxes):
            self.app.show_detail('候选强度只读。' if self.readonly else '切换到控制点模式可编辑强度。' if self.mode=='arrange' else '强度控制点 · tick 精确定位，端点时间固定；Esc 取消未提交操作。')
            return
        if self.badge_detail(x,y):return
        if self.final_detail(x,y):return
        bridge_id = self.hit_bridge(x,y)
        connection_id = self.hit_connection(x,y)
        if bridge_id:
            overlay = next(o for o in self.bridge_preview['overlays'] if o['id']==bridge_id)
            self.app.show_detail(self.app.describe_bridge_overlay(overlay))
        elif connection_id:
            overlay = next(o for o in self.connection_preview['connection_overlays'] if o['id']==connection_id)
            self.app.show_detail(self.app.describe_connection_overlay(overlay))
        elif any(abs(x-a)<=10 and abs(y-b)<=10 for _,a,b in self.point_boxes):
            self.app.show_detail('候选强度只读。' if self.readonly else '切换到控制点模式可编辑强度。' if self.mode=='arrange' else '强度控制点 · tick 精确定位，端点时间固定；Esc 取消未提交操作。')
        else:
            overlay = self.memory_overlay()
            if overlay and self.hit(x,y)==overlay[0]['placement_id']:
                region = overlay[1] or overlay[0]['range']
                if region and self.x(region['start_tick'])<=x<=self.x(region['end_tick']):
                    self.app.show_detail(self.app.preview_memory_description() if self.readonly else self.app.memory_description())

    def contains_root(self, x_root, y_root):
        c = self.canvas
        return c.winfo_rootx()<=x_root<c.winfo_rootx()+c.winfo_width() and c.winfo_rooty()<=y_root<c.winfo_rooty()+c.winfo_height()

    def root_tick(self, x_root, offset_px=0):
        return self.tick(self.canvas.canvasx(x_root-self.canvas.winfo_rootx())-offset_px)

    def hit(self, x, y):
        for ident,(a,t,b,d) in reversed(list(self.boxes.items())):
            # A subpixel block's 1px outline extends half a pixel on each side.
            # Match that visible stroke without enlarging its musical geometry.
            pad = .5 if b-a<1 else 0
            if a-pad<=x<=b+pad and t<=y<=d:
                return ident
        return None

    def hit_gap(self, x, y):
        for ident,(a,t,b,d) in reversed(list(self.gap_boxes.items())):
            pad = .5 if b-a<1 else 0
            if a-pad<=x<=b+pad and t<=y<=d:return ident
        return None

    def press(self, event):
        if self.app.material_drag:return
        self.cancel()
        self.canvas.focus_set()
        if not self.project:return
        x,y = (self.canvas.canvasx(event.x_root-self.canvas.winfo_rootx()),
               self.canvas.canvasy(event.y_root-self.canvas.winfo_rooty()))
        if self.readonly:
            if self.badge_detail(x,y,select=True):
                self.draw()
                return
            if self.final_detail(x,y):return
            bridge_id = self.hit_bridge(x,y)
            connection_id = self.hit_connection(x,y)
            if bridge_id:
                self.selected_bridge_id = bridge_id
                self.selected_connection_id = None
                overlay = next(o for o in self.bridge_preview['overlays'] if o['id']==bridge_id)
                self.app.show_detail(self.app.describe_bridge_overlay(overlay))
            elif connection_id:
                self.selected_bridge_id = None
                self.selected_connection_id = connection_id
                overlay = next(o for o in self.connection_preview['connection_overlays'] if o['id']==connection_id)
                self.app.show_detail(self.app.describe_connection_overlay(overlay))
            else:
                self.selected_bridge_id = None
                self.selected_connection_id = None
                ident = self.hit(x,y)
                if ident:
                    self.selected_id = ident
                    placement = next(p for p in self.project['placements'] if p['id']==ident)
                    self.app.show_detail(self.app.completion.describe_placement(placement)+' · 候选只读')
            self.draw()
            return
        point_index = next((i for i,a,b in self.point_boxes if abs(x-a)<=10 and abs(y-b)<=10),None)
        if self.app.can_edit('intensity_edit') and (self.mode=='trace' or (self.mode=='points' and point_index is not None)):
            self.begin_intensity(event,point_index if self.mode=='points' else None)
            return
        if self.badge_detail(x,y):return
        if self.final_detail(x,y):return
        ident = self.hit(x,y)
        if ident:self.selected_id = ident
        self.app.update_emotions()
        if ident:
            self.app.select_target('placement', ident)
            placement = next(p for p in self.project['placements'] if p['id']==ident)
            self.app.show_detail(placement['base_snapshot']['label']+' · 点击仅选择；拖动移动，'+ui_platform.DELETE_LABEL+' 删除')
            if self.app.editable:
                self.drag = dict(id=ident,start_root=(event.x_root,event.y_root),
                                 offset=x-self.x(placement['start_tick']),length=placement['length_ticks'],active=False)
        elif self.mode in ('arrange','gaps'):
            ident = self.hit_gap(x,y)
            if ident:self.app.completion.select_gap(ident)
        elif self.mode=='points' and self.app.can_edit('intensity_edit'):
            self.begin_intensity(event,None)
        self.draw()

    def begin_intensity(self, event, index):
        original = copy.deepcopy(self.project['intensity_points'])
        self.intensity_draft = dict(original=original,points=original,index=index,trace=[],
                                    start_root=(event.x_root,event.y_root),active=False,
                                    start_canvas=(self.canvas.canvasx(event.x_root-self.canvas.winfo_rootx()),
                                                  self.canvas.canvasy(event.y_root-self.canvas.winfo_rooty())))
        self.canvas.grab_set()
        if index is None:self.preview_intensity(event)
        self.draw()

    def preview_intensity(self, event):
        draft = self.intensity_draft
        point = self.root_point(event.x_root,event.y_root)
        if self.mode=='trace':
            draft['trace'].append(point)
            sampled = {p['tick']:p for p in draft['trace']}
            lo,hi = min(sampled),max(sampled)
            outside = [p for p in draft['original'] if p['tick']<lo or p['tick']>hi]
            draft['points'] = sorted(outside+list(sampled.values()),key=lambda p:p['tick'])
        elif draft['index'] is not None:
            index = draft['index']
            points = copy.deepcopy(draft['original'])
            x = self.canvas.canvasx(event.x_root-self.canvas.winfo_rootx())
            y = self.canvas.canvasy(event.y_root-self.canvas.winfo_rooty())
            point = dict(tick=math.floor(points[index]['tick']+(x-draft['start_canvas'][0])/self.scale+.5),
                         level=min(1.,max(0.,points[index]['level']-(y-draft['start_canvas'][1])/max(1,self.canvas.winfo_height()-80))))
            if index in (0,len(points)-1):point['tick'] = points[index]['tick']
            else:point['tick'] = max(points[index-1]['tick']+1,min(points[index+1]['tick']-1,point['tick']))
            points[index] = point
            draft['points'] = points
        else:
            draft['points'] = sorted([p for p in draft['original'] if p['tick']!=point['tick']]+[point],key=lambda p:p['tick'])

    def motion(self, event):
        if self.intensity_draft:
            draft = self.intensity_draft
            if max(abs(event.x_root-draft['start_root'][0]),abs(event.y_root-draft['start_root'][1]))>=5:
                draft['active'] = True
            if draft['active']:
                self.preview_intensity(event)
                self.edge_scroll(event.x_root,event.y_root)
                self.draw()
            return
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
        if self.intensity_draft:
            draft = self.intensity_draft
            inside = self.contains_root(event.x_root,event.y_root)
            if inside and (draft['active'] or draft['index'] is None):self.preview_intensity(event)
            points = copy.deepcopy(draft['points'])
            self.cancel()
            if not inside or not self.app.can_edit('intensity_edit') or (self.mode=='trace' and not draft['active']):return
            if self.mode=='trace':
                try:
                    normalized = _normalize_trace(points,self.project['total_ticks'])
                    lo,hi = min(p['tick'] for p in draft['trace']),max(p['tick'] for p in draft['trace'])
                    # Keep every original point outside the locally drawn interval.
                    local = {p['tick']:p for p in normalized if lo<=p['tick']<=hi}
                    local[lo] = next(p for p in points if p['tick']==lo)
                    local[hi] = next(p for p in points if p['tick']==hi)
                    points = sorted([p for p in draft['original'] if p['tick']<lo or p['tick']>hi]
                                    +list(local.values()),key=lambda p:p['tick'])
                except Exception as exc:
                    self.app.tell('手绘规范化失败：'+str(exc),True)
                    return
            if points!=draft['original']:self.app.edit('set_intensity',points=points)
            return
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
            elif self.intensity_draft and self.intensity_draft['active']:
                self.preview_intensity(SimpleNamespace(x_root=x,y_root=y))
            self.draw()
            self.edge_timer = self.after(60,self._edge_step)

    def cancel(self, event=None):
        if self.edge_timer is not None:
            self.after_cancel(self.edge_timer)
            self.edge_timer = None
        self.drag = None
        self.intensity_draft = None
        self.preview = None
        if self.canvas.grab_current()==self.canvas:
            self.canvas.grab_release()
        self.draw()
        if event is not None and self.readonly:self.app.exit_private_preview()
        return 'break' if event else None

    def delete_selected(self, event=None):
        if not self.readonly and self.selected_id and self.app.editable and not self.app.covered_by_accepted_bridge(self.selected_id):
            self.app.edit('delete',placement_id=self.selected_id)
        return 'break'

    def destroyed(self, event):
        if event.widget==self and self.edge_timer is not None:
            self.after_cancel(self.edge_timer)
            self.edge_timer = None
