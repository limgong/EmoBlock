"""Inline melody assembly studio: one window, transactional drop and drawing."""
import copy
import math
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import brick_model
import emotion_input
import story_engine as engine
from ui_hints import rounded,Tooltip
from ui_scale import font as font
from ui_theme import color

COLORS=dict(calm='#8fcddd',hope='#ebd18c',sad='#a6a6df',suspense='#c8a6df',crisis='#e99c98',resolve='#97d9ba')
LABELS=engine.music.EMOTIONS

class ComposerUI:
    def build_composer(self,source_body,editor_body):
        self.selected_brick=None;self.selected_placement=None;self.assembly_drag=None;self.stroke_samples=[]
        self.selection_anchor=0;self.tool_mode=tk.StringVar(value='edit');self.composer_status=tk.StringVar()
        self.brick_name=tk.StringVar();self.brick_emotion=tk.StringVar(value=LABELS['calm'])
        self.variant_choice=tk.StringVar(value='原旋律');self.edge_choice=tk.BooleanVar(value=True)
        toolbar=ttk.Frame(self.source_details);toolbar.pack(fill='x',pady=(4,0))
        self.selection_label=tk.StringVar(value='选择分块组合成积木')
        ttk.Label(toolbar,textvariable=self.selection_label,style='Muted.TLabel').pack(side='left')
        self.compose_button=ttk.Button(toolbar,text='＋ 组成积木',style='Accent.TButton',command=lambda:self.host.safe(self.compose_selection))
        self.compose_button.pack(side='right')
        ttk.Button(toolbar,text='清空选择',style='Quiet.TButton',command=self.clear_part_selection).pack(side='right',padx=6)
        tray_header=ttk.Frame(source_body);tray_header.pack(fill='x',pady=(4,2))
        ttk.Label(tray_header,text='我的旋律积木',font=font(('Microsoft YaHei UI',9,'bold'))).pack(side='left')
        ttk.Label(tray_header,text='拖入下方旋律轨 · 四拍吸附',style='Muted.TLabel').pack(side='right')
        self.brick_tray=tk.Canvas(source_body,height=58,bg=color('panel'),highlightthickness=0,xscrollincrement=80)
        self.brick_tray.pack(fill='x')
        self.brick_tray.scroll_canvas=self.brick_tray;self.brick_tray.scroll_axis='x'
        self.brick_tray_scroll=ttk.Scrollbar(source_body,orient='horizontal',command=self.brick_tray.xview)
        self.brick_tray.configure(xscrollcommand=self.brick_tray_scroll.set)
        self.brick_tray.bind('<Configure>',lambda _:self.draw_brick_tray())
        self.brick_tray.bind('<Button-1>',self.tray_press)
        self.brick_tray.bind('<B1-Motion>',self.assembly_motion)
        self.brick_tray.bind('<ButtonRelease-1>',self.assembly_release)
        self.brick_tray.bind('<Escape>',self.cancel_assembly)
        self.brick_tray.bind('<Return>',lambda _:self.host.safe(self.insert_selected_brick))
        tools=ttk.Frame(self.editor_heading);tools.pack(side='left',padx=8)
        for label,value in (('选择 / 拖动','edit'),('手绘情绪线','draw')):
            ttk.Radiobutton(tools,text=label,value=value,variable=self.tool_mode,command=self.change_composer_tool).pack(side='left',padx=(0,12))
        Tooltip(tools,'选择模式拖动积木或程度点；手绘模式只在曲线区绘制，松开后按四拍识别。')
        self.inspector=ttk.Frame(editor_body);self.inspector.pack(fill='x',before=self.line,pady=(0,5))
        self.inspector_title=tk.StringVar(value='选中一个旋律积木，可设置情绪、原旋律 / 简单变体')
        ttk.Label(self.inspector,textvariable=self.inspector_title,style='Muted.TLabel').pack(side='left',padx=(0,8))
        self.emotion_picker=ttk.Combobox(self.inspector,textvariable=self.brick_emotion,values=list(LABELS.values()),width=10,state='readonly')
        self.emotion_picker.pack(side='left');self.emotion_picker.bind('<<ComboboxSelected>>',lambda _:self.host.safe(self.update_selected_assembly))
        self.variant_picker=ttk.Combobox(self.inspector,textvariable=self.variant_choice,values=('原旋律','简单变体'),width=8,state='readonly')
        self.variant_picker.pack(side='left',padx=5);self.variant_picker.bind('<<ComboboxSelected>>',lambda _:self.host.safe(self.update_selected_assembly))
        self.edge_toggle=ttk.Checkbutton(self.inspector,text='首尾连接',variable=self.edge_choice,command=lambda:self.host.safe(self.update_selected_assembly))
        self.edge_toggle.pack(side='left')
        self.remove_assembly_button=ttk.Button(self.inspector,text='移除',width=5,command=lambda:self.host.safe(self.remove_selected_assembly))
        self.remove_assembly_button.pack(side='right')
        ttk.Label(self.footer,textvariable=self.composer_status,style='Muted.TLabel').pack(side='left',padx=8)
        Tooltip(self.edge_toggle,'至少 3 块长的积木允许首尾各一块参与连接，中间主旋律保留。关闭后整段主旋律保护，情绪配器仍变化。')
        Tooltip(self.emotion_picker,'指定的是主旋律，不是固定音频。音色、和声、伴奏和力度仍按情绪变化；颜色确定情绪种类，程度跟随手绘曲线。库颜色作为下一次拖入的默认情绪。')
        Tooltip(self.variant_picker,'原旋律保留主旋律的音高与节奏；简单变体允许少量调内邻音变化。两者都会进行情绪配器，不是原样播放。')
        Tooltip(self.brick_tray,'单击选中，在下面设置情绪；拖到旋律轨吸附。回车可放到第一个空位。每个积木可以重复使用。')
        self.line.bind('<Delete>',lambda _:self.host.safe(self.remove_selected_assembly))
        self.line.bind('<Escape>',self.composer_escape)

    def composer_escape(self,event=None):
        if self.assembly_drag:return self.cancel_assembly(event)
        return self.cancel_drag(event)

    def change_composer_tool(self):
        self.cancel_assembly();self.cancel_drag()
        self.host.tell('按住左键在程度曲线区手绘；先选情绪颜色，松开自动识别' if self.tool_mode.get()=='draw' else '拖动积木编排；圆点调整程度，框选情绪区涂色')

    def clear_part_selection(self):
        self.input_blocks.selection_remove(*self.input_blocks.selection());self.draw_block_cards();self.selection_changed()

    def selection_changed(self):
        if not hasattr(self,'selection_label'):return
        indices=sorted(int(i) for i in self.input_blocks.selection())
        self.selection_label.set('已选 '+str(len(indices))+' 块 · '+(', '.join(str(i+1) for i in indices) if indices else '点击多选，Shift 连选'))
        self.compose_button.configure(state='normal' if indices else 'disabled')

    def select_part(self,index,event=None):
        selected=set(self.input_blocks.selection());ident=str(index)
        if event is not None and event.state&1:
            selected.update(str(i) for i in range(min(self.selection_anchor,index),max(self.selection_anchor,index)+1))
        elif ident in selected:selected.remove(ident);self.selection_anchor=index
        else:selected.add(ident);self.selection_anchor=index
        self.input_blocks.selection_set(*sorted(selected,key=int));self.draw_source_notes();self.draw_block_cards();self.selection_changed()

    def compose_selection(self):
        if self.host.busy:return
        source=self.selected_source();indices=sorted(int(i) for i in self.input_blocks.selection())
        if not indices:raise ValueError('先点击选择要拼接的旋律分块。')
        name='M'+str(self.project['sources'].index(source)+1)+' · '+','.join(str(i+1) for i in indices)
        emotion=next(k for k,v in LABELS.items() if v==self.brick_emotion.get())
        project,ident=brick_model.create(self.snapshot(),source['id'],indices,name,emotion)
        self.selected_brick=ident;self.selected_placement=None;self.commit(project)
        self.host.tell('积木已创建 · 选择颜色后拖到下方旋律轨；也可按回车放入空位')

    def panel_height(self):
        desired=236+(114 if getattr(self,'source_details_open',False) else 0)
        # Reserve usable curve/arrangement space; the source panel scrolls on small screens.
        return min(desired,max(170,self.host.root.winfo_height()-520))

    def refresh_composer(self):
        if not hasattr(self,'brick_tray'):return
        self.source_panel.configure(height=self.panel_height())
        self.selection_changed();self.draw_brick_tray();self.sync_inspector()
        s=brick_model.summary(self.project)
        self.composer_status.set(f'主旋律 {s["fixed"]} 块 · 补齐 {s["empty"]} 块')

    def draw_brick_tray(self):
        if not hasattr(self,'brick_tray'):return
        c=self.brick_tray;c.delete('all');self.tray_boxes=[];values=self.project.get('melody_bricks',[])
        for i,b in enumerate(values):
            x=i*162+2;w=152;self.tray_boxes.append((x,x+w,b['id']))
            selected=b['id']==self.selected_brick;shade=COLORS[b.get('emotion','calm')]
            rounded(c,x,3,x+w,55,color('selected') if selected else color('inset'),color('accent') if selected else color('line'),2 if selected else 1,radius=12)
            c.create_rectangle(x+9,12,x+13,47,fill=shade,outline='')
            c.create_text(x+22,20,text=b['name'][:17],anchor='w',fill=color('ink'),font=font(('Microsoft YaHei UI',9,'bold')))
            c.create_text(x+22,40,text=f'{b["ticks"]//1920} 块 · {LABELS[b["emotion"]].split("／")[0]}  ↗',anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
        if not values:
            rounded(c,2,3,max(100,c.winfo_width()-2),55,color('inset'),color('line'),radius=12)
            c.create_text(18,24,text='从上面的旋律分块开始',anchor='w',fill=color('ink'),font=font(('Microsoft YaHei UI',9,'bold')))
            c.create_text(18,42,text='展开分块 → 多选 → 组成积木 → 拖入时间线',anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
        width=max(c.winfo_width(),len(values)*162);c.configure(scrollregion=(0,0,width,58))
        if width>c.winfo_width()+2:
            if not self.brick_tray_scroll.winfo_manager():self.brick_tray_scroll.pack(fill='x',after=c)
        else:self.brick_tray_scroll.pack_forget()

    def sync_inspector(self):
        p=next((p for p in self.project.get('brick_placements',[]) if p['id']==self.selected_placement),None)
        b=next((b for b in self.project.get('melody_bricks',[]) if b['id']==(p['brick_id'] if p else self.selected_brick)),None)
        if b:
            if not self.inspector.winfo_manager():self.inspector.pack(fill='x',before=self.line,pady=(0,5))
            self.selected_brick=b['id'];self.brick_emotion.set(LABELS[p['emotion'] if p else b['emotion']])
            self.inspector_title.set(('第 '+str(p['start_bar']+1)+' 格 · ' if p else '积木库 · ')+b['name'][:13])
        else:
            self.inspector_title.set('选中积木设置颜色，拖入下方旋律轨');self.inspector.pack_forget()
        self.emotion_picker.configure(state='readonly' if b else 'disabled')
        self.variant_picker.configure(state='readonly' if p else 'disabled')
        self.edge_toggle.configure(state='normal' if p and b['ticks']>=3*1920 else 'disabled')
        self.remove_assembly_button.configure(state='normal' if b else 'disabled')
        self.variant_choice.set('简单变体' if p and p.get('variant')=='simple' else '原旋律')
        self.edge_choice.set(p.get('edge_connect',True) if p else True)

    def update_selected_assembly(self):
        if self.host.busy:return
        emotion=next(k for k,v in LABELS.items() if v==self.brick_emotion.get());project=self.snapshot()
        p=next((p for p in project.get('brick_placements',[]) if p['id']==self.selected_placement),None)
        if p:
            p.update(emotion=emotion,variant='simple' if self.variant_choice.get()=='简单变体' else 'original',edge_connect=self.edge_choice.get())
        elif self.selected_brick:brick_model.brick(project,self.selected_brick)['emotion']=emotion
        else:return
        self.commit(project)

    def remove_selected_assembly(self):
        if self.host.busy:return
        ident=self.selected_placement or self.selected_brick
        if ident is None:return
        project=brick_model.remove(self.snapshot(),ident,library=self.selected_placement is None)
        if self.selected_placement:self.selected_placement=None
        else:self.selected_brick=None
        self.commit(project);self.host.tell('已移除，原位置将按情绪线自动补齐 · Ctrl+Z 撤销')

    def insert_selected_brick(self):
        if not self.selected_brick:return
        project,ident=brick_model.place(self.snapshot(),self.selected_brick,brick_model.first_gap(self.project,self.selected_brick))
        self.selected_placement=ident;self.commit(project)

    def tray_press(self,event):
        if self.host.busy:return
        x=self.brick_tray.canvasx(event.x);ident=next((i for a,b,i in self.tray_boxes if a<=x<=b),None)
        if ident:
            self.selected_brick=ident;self.selected_placement=None;self.sync_inspector();self.draw_brick_tray()
            self.start_assembly(event,ident)

    def start_assembly(self,event,brick_id,placement=None):
        self.cancel_drag();event.widget.focus_set();event.widget.grab_set()
        self.assembly_drag=dict(widget=event.widget,brick_id=brick_id,placement=copy.deepcopy(placement),
            origin=(event.x_root,event.y_root),moved=False,target=None,error='',preview=None,
            grab_bar=(self.seconds_at(self.line.canvasx(event.x))/(240/self.project['bpm'])-placement['start_bar']) if placement else 0)

    def assembly_motion(self,event):
        d=self.assembly_drag
        if not d:return
        if abs(event.x_root-d['origin'][0])+abs(event.y_root-d['origin'][1])<6 and not d['moved']:return
        d['moved']=True;d['target']=None;d['preview']=None;d['error']=''
        x=event.x_root-self.line.winfo_rootx();y=(event.y_root-self.line.winfo_rooty())/max(.1,getattr(self,'timeline_scale',1))
        if 0<=x<=self.line.winfo_width() and 24<=y<=305:
            time=self.seconds_at(self.line.canvasx(x));index=math.floor(time/(240/self.project['bpm'])-d['grab_bar']+.5)
            d['target']=index
            p=d['placement'];b=brick_model.brick(self.project,d['brick_id'])
            try:
                d['preview'],_=brick_model.place(self.project,b['id'],index,emotion=p['emotion'] if p else b['emotion'],
                    placement_id=p['id'] if p else None,variant=p.get('variant','original') if p else 'original',edge_connect=p.get('edge_connect',True) if p else True)
            except ValueError as exc:d['error']=str(exc)
            if x<24:self.line.xview_scroll(-1,'units')
            elif x>self.line.winfo_width()-24:self.line.xview_scroll(1,'units')
        self.draw()

    def assembly_release(self,event):
        if not self.assembly_drag:return
        self.assembly_motion(event);d=self.assembly_drag;self.cancel_assembly()
        if d['moved'] and d['preview'] is not None:
            old_ids={p['id'] for p in self.project.get('brick_placements',[])}
            self.selected_placement=d['placement']['id'] if d['placement'] else next(p['id'] for p in d['preview']['brick_placements'] if p['id'] not in old_ids)
            self.host.safe(lambda:self.commit(d['preview']));self.host.tell('主旋律已指定 · 情绪编配仍变化，空位自动填充 · Ctrl+Z 撤销')
        elif d['moved']:self.host.tell(d['error'] or '拖入下方时间线后松开',True)

    def cancel_assembly(self,event=None):
        d=getattr(self,'assembly_drag',None)
        if d and d['widget'].grab_current()==d['widget']:d['widget'].grab_release()
        self.assembly_drag=None
        if hasattr(self,'line'):self.draw()
        return 'break'

    def draw_composer_overlay(self):
        if not hasattr(self,'tool_mode'):return
        c=self.line;bar=240/self.project['bpm'];f=font(('Microsoft YaHei UI',8))
        if not self.project.get('brick_placements'):
            c.create_text(self.timeline_width/2+12,299,text='拖入积木指定主旋律 · 情绪编配仍变化 · 空位自动编排',fill=color('muted'),font=f)
        for start,end,p,b in brick_model.spans(self.project):
            a=self.px(start)+2;z=self.px(end)-2;shade=COLORS[p['emotion']];selected=p['id']==self.selected_placement
            rounded(c,a,244,z,294,color('selected') if selected else color('panel'),shade,3 if selected else 2,radius=7)
            c.create_rectangle(a+5,250,a+8,286,fill=shade,outline='')
            c.create_text(a+13,257,text=b['name'][:max(2,int((z-a-20)/8))],anchor='w',fill=color('ink'),font=font(('Microsoft YaHei UI',8,'bold')))
            c.create_text(a+13,280,text='主旋律 · '+('简单变体' if p.get('variant')=='simple' else '原旋律'),anchor='w',fill=color('muted'),font=f)
            if p.get('edge_connect',True) and b['ticks']>=3*1920:
                c.create_line(a+3,291,self.px(start+bar)-2,291,fill=shade,dash=(2,2),width=2)
                c.create_line(self.px(end-bar)+2,291,z-3,291,fill=shade,dash=(2,2),width=2)
        if self.stroke_samples:
            coordinates=[]
            for time,level in self.stroke_samples:coordinates.extend((self.px(time),206-62*level))
            if len(coordinates)>=4:c.create_line(*coordinates,fill=color('accent'),width=3,smooth=True)
        d=self.assembly_drag
        if d and d['target'] is not None:
            b=brick_model.brick(self.project,d['brick_id']);a=self.px(d['target']*bar);z=self.px((d['target']+b['ticks']/1920)*bar)
            shade=color('#f28e89') if d['error'] else color('accent')
            rounded(c,a+2,240,z-2,298,'',shade,3,radius=8)
            c.create_text((a+z)/2,230,text=d['error'][:27] if d['error'] else f'吸附第 {d["target"]+1} 格 · 松开放置',fill=shade,font=f)

    def press(self,event):
        if self.host.busy:return
        if self.tool_mode.get()=='draw' and 116<=event.y<=214:
            self.cancel_drag();self.drag=('sketch',self.line.canvasx(event.x));self.stroke_samples=[]
            self.line.grab_set();self.motion(event);return
        if 244<=event.y<=305:
            found=brick_model.placement_at(self.project,self.seconds_at(self.line.canvasx(event.x)))
            if found:
                p,b=found;self.selected_placement=p['id'];self.selected_brick=b['id'];self.sync_inspector();self.draw_brick_tray()
                self.start_assembly(SimpleNamespace(widget=self.line,x=event.x,x_root=self.line.winfo_rootx()+event.x,
                    y_root=self.line.winfo_rooty()+event.y*getattr(self,'timeline_scale',1)),b['id'],p)
                self.draw();return
        super().press(event)

    def motion(self,event):
        if self.assembly_drag:
            self.assembly_motion(SimpleNamespace(x_root=self.line.winfo_rootx()+event.x,y_root=self.line.winfo_rooty()+event.y*getattr(self,'timeline_scale',1)));return
        if self.drag and self.drag[0]=='sketch':
            time=self.seconds_at(self.line.canvasx(event.x));level=max(0,min(1,(206-event.y)/62))
            if not self.stroke_samples or abs(time-self.stroke_samples[-1][0])>.01:self.stroke_samples.append((time,level))
            else:self.stroke_samples[-1]=(time,level)
            self.line.configure(cursor='crosshair');self.draw();return
        super().motion(event)

    def release(self,event):
        if self.assembly_drag:
            self.assembly_release(SimpleNamespace(x_root=self.line.winfo_rootx()+event.x,y_root=self.line.winfo_rooty()+event.y*getattr(self,'timeline_scale',1)));return
        if self.drag and self.drag[0]=='sketch':
            self.motion(event);samples=list(self.stroke_samples);self.stroke_samples=[];self.cancel_drag()
            emotion=self.paint_emotion or next(k for k,v in LABELS.items() if v==self.emotion.get())
            self.host.safe(lambda:self.commit(brick_model.draw_emotion(self.snapshot(),samples,emotion)))
            self.host.tell('手绘已识别为四拍情绪段和连续程度曲线 · Ctrl+Z 撤销');return
        super().release(event)
