"""Shared assembly cards, draft combinations and one-scale canvas interaction."""
import copy
import math
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk, simpledialog
import assembly
import intensity_curve
import block_audition
from block_timeline import BlockTimeline
from block_actions import BlockActions
from block_visuals import brick,BlockMotion
from ui_hints import Tooltip,rounded,elide
from ui_theme import color
from ui_scale import font
import ui_scale
import ui_platform

COLORS=dict(calm='#8fcddd',hope='#ebd18c',sad='#a6a6df',suspense='#c8a6df',crisis='#e99c98',resolve='#97d9ba')


class AssemblyUI:
    def is_assembly(self):return assembly.is_project(self.project)

    def draw_material_cards(self):
        for child in self.source_cards.winfo_children():child.destroy()
        self.card_play_buttons={};self.card_role_buttons={};self.card_delete_buttons={}
        bank=self.project['library'];width=max(240,getattr(self,'source_card_width',600))
        columns=max(1,min(3,int(width//(165*ui_scale.factor))));pages=max(1,math.ceil(len(bank)/columns))
        self.source_page=max(0,min(self.source_page,pages-1));self.source_page_label.set(f'{self.source_page+1}/{pages}')
        for arrow in (self.source_prev,self.source_next):
            if pages>1:arrow.pack(side='left',padx=(0,3))
            else:arrow.pack_forget()
        self.material_card_columns=columns
        for asset in bank[self.source_page*columns:(self.source_page+1)*columns]:
            w=width/columns-6;c=tk.Canvas(self.source_cards,width=w,height=round(94*ui_scale.factor),highlightthickness=0,bg=color('panel'),takefocus=True,cursor='hand2')
            c.pack(side='left',fill='both',expand=True,padx=(0,4))
            selected=asset['id']==getattr(self,'selected_material_id',None)
            rounded(c,1,1,w-1,93,color('inset'),color('accent') if selected else color('line'),radius=12)
            title=('组合 · ' if asset['kind']=='combination' else '')+asset['name']
            c.create_text(10,15,text=elide(c,title,w-20,font(('Microsoft YaHei UI',10))),anchor='w',fill=color('ink'),font=font(('Microsoft YaHei UI',10)))
            hint=assembly.composition(asset)
            c.create_text(10,34,text=elide(c,hint,w-20,font(('Microsoft YaHei UI',8))),anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
            c.create_text(10,77,text=f'{asset["ticks"]/480:g} 拍'+(' · 休止' if not asset['notes'] else ''),anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
            low=min((n['pitch'] for n in asset['notes']),default=60);high=max((n['pitch'] for n in asset['notes']),default=60)
            for n in asset['notes']:
                a=10+(w-20)*n['start']/asset['ticks'];b=10+(w-20)*(n['start']+n['duration'])/asset['ticks'];y=61-13*(n['pitch']-low)/max(1,high-low)
                c.create_rectangle(a,y,max(a+1,b-1),y+3,fill=color('accent'),outline='')
            button=ttk.Button(c,text='▶',width=3,style='Compact.TButton',command=lambda ident=asset['id']:self.host.safe(lambda:self.audition_material(assembly.material(self.project,ident))))
            c.create_window(w-24,77,window=button,width=32,height=26);c.scale('all',0,0,1,ui_scale.factor)
            self.card_play_buttons[asset['id']]=button
            if self.host.busy:button.state(['disabled'])
            c.bind('<Button-1>',lambda e,ident=asset['id']:self.begin_material_drag(e,ident))
            c.bind('<B1-Motion>',self.material_drag_motion);c.bind('<ButtonRelease-1>',self.material_drag_release)
            c.bind('<Escape>',self.cancel_drag);c.bind('<Return>',lambda _,ident=asset['id']:self.select_material(ident))
            for event in ui_platform.CONTEXT_EVENTS:c.bind(event,lambda e,m=asset:self.material_menu(e,m))
            Tooltip(c,title+'\n'+hint+'\n单击选择；拖入积木条；▶ 试听；右键查看完整来源。')

    def select_material(self,ident):
        if self.host.busy:return
        self.selected_material_id=ident
        asset=assembly.material(self.project,ident);leaf=assembly.leaves(asset)[0]
        sid=leaf['origin']['source_id']
        if self.sources.exists(sid):self.sources.selection_set(sid);self.refresh_source_blocks()
        self.draw_source_cards()

    def material_menu(self,event,asset):
        if self.host.busy:return
        menu=tk.Menu(self.root if hasattr(self,'root') else self.host.root,tearoff=False)
        menu.add_command(label='查看组成与来源',command=lambda:self.show_material_info(asset))
        menu.add_command(label='加入组合草稿',command=lambda:self.host.safe(lambda:self.open_combination([asset])))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def show_material_info(self,asset):
        win=tk.Toplevel(self);win.title('素材组成与来源');win.geometry('620x320')
        text=f'{asset["name"]} · {asset["ticks"]/480:g} 拍\n'+assembly.composition(asset)+'\n\n'
        for i,leaf in enumerate(assembly.leaves(asset)):
            origin=leaf['origin'];text+=f'{i+1}. {leaf["name"]} · {origin["source_name"]} 第 {origin["block_index"]+1} 块 · {leaf["ticks"]/480:g} 拍\n'
            path=origin.get('source',{}).get('path')
            if path:text+=str(path)+(' · 原文件缺失，使用音符快照' if not Path(path).is_file() else '')+'\n'
        box=tk.Text(win,wrap='word');bar=ttk.Scrollbar(win,command=box.yview);bar.pack(side='right',fill='y');box.configure(yscrollcommand=bar.set)
        ttk.Button(win,text='关闭',command=win.destroy).pack(side='bottom',pady=8);box.pack(fill='both',expand=True);box.insert('1.0',text);box.configure(state='disabled')

    def audition_material(self,asset):
        if self.host.busy:return
        asset=copy.deepcopy(asset);bpm=self.project['bpm']
        self.host.stop_playback();self.source_audio=None;self.source_block_playing=None
        def done(result):
            path,rows=result
            # A combined card auditions its complete composition, not just its first four beats.
            row=dict(name=asset['name'],start_seconds=0.,end_seconds=asset['ticks']/(bpm*480/60),emotion='calm')
            self.material_audio=dict(id=asset['id'],path=path,name=asset['name'])
            self.host.play_segment(path,[row],0,'source:'+str(path),'素材 '+asset['name'])
        self.host.job('准备分块素材试听…',lambda:block_audition.render_source(asset,bpm,self.host.progress_message),done,on_error=self.source_audio_failed)

    def open_combination(self,initial=None):
        if self.host.busy:return
        win=tk.Toplevel(self);win.title('组合素材草稿');win.geometry('640x430');win.transient(self.host.root)
        win.items=copy.deepcopy(initial or []);self.combination_window=win
        self.combination_windows=[w for w in getattr(self,'combination_windows',[]) if w.winfo_exists()]+[win]
        choices=copy.deepcopy(self.project['library'])
        header=ttk.Frame(win,padding=8);header.pack(fill='x')
        ttk.Label(header,text='分块 / 组合').pack(side='left')
        picker=ttk.Combobox(header,values=[m['name']+' · '+f'{m["ticks"]/480:g} 拍' for m in choices],state='readonly');picker.pack(side='left',fill='x',expand=True,padx=6)
        if choices:picker.current(0)
        def change(action):
            if self.host.busy:return
            index=listing.curselection()[0] if listing.curselection() else None
            if action=='add' and picker.current()>=0:win.items.append(copy.deepcopy(choices[picker.current()]))
            elif index is not None:
                if action=='remove':win.items.pop(index)
                else:
                    target=max(0,min(len(win.items)-1,index+action));win.items.insert(target,win.items.pop(index));index=target
            redraw(index)
        ttk.Button(header,text='加入',command=lambda:change('add')).pack(side='right')
        listing=tk.Listbox(win,exportselection=False);scroll=ttk.Scrollbar(win,command=listing.yview);scroll.pack(side='right',fill='y');listing.configure(yscrollcommand=scroll.set);listing.pack(fill='both',expand=True,padx=8)
        def redraw(index=None):
            listing.delete(0,'end')
            for i,m in enumerate(win.items):listing.insert('end',f'{i+1}. {m["name"]} · {m["ticks"]/480:g} 拍 · '+assembly.composition(m))
            if win.items:listing.selection_set(min(index or 0,len(win.items)-1))
        tools=ttk.Frame(win,padding=8);tools.pack(fill='x')
        for label,action in (('上移',-1),('下移',1),('移除','remove')):ttk.Button(tools,text=label,command=lambda a=action:change(a)).pack(side='left',padx=2)
        ttk.Button(tools,text='试听草稿',command=lambda:self.host.safe(lambda:self.audition_material(assembly.combine(self.project,win.items,'组合草稿')))).pack(side='left',padx=5)
        stop=ttk.Button(tools,text='停止',command=self.host.stop_playback);stop.available_while_busy=True;stop.pack(side='left')
        footer=ttk.Frame(win,padding=8);footer.pack(fill='x')
        ttk.Label(footer,text='名称').pack(side='left');name=tk.StringVar(value='组合素材 C');ttk.Entry(footer,textvariable=name).pack(side='left',fill='x',expand=True,padx=6)
        def save():
            if self.host.busy:return
            if self.host.safe(lambda:self.save_combination(win.items,name.get())):win.destroy()
        ttk.Button(footer,text='保存素材',command=save).pack(side='right')
        ttk.Button(footer,text='取消',command=win.destroy).pack(side='right',padx=6)
        win.bind('<Escape>',lambda _:win.destroy());redraw()

    def discard_combination_drafts(self):
        for win in getattr(self,'combination_windows',[]):
            if win.winfo_exists():win.destroy()
        self.combination_windows=[]

    def save_combination(self,items,name):
        if self.host.busy:return False
        result=assembly.save_combination(self.snapshot(),items,name)
        if self.commit(result,'保存组合素材'):
            self.selected_material_id=result['library'][-1]['id'];self.source_page=math.ceil(len(result['library'])/max(1,getattr(self,'material_card_columns',3)))-1
            self.draw_source_cards();return True
        return False

    def save_selected_combination(self):
        indexes=sorted(getattr(self,'assembly_selection',set()))
        if len(indexes)<2 or indexes!=list(range(indexes[0],indexes[-1]+1)):raise ValueError('请使用 Shift 选择连续的多个积木。')
        self.open_combination([self.project['uses'][i]['material'] for i in indexes])

    def insert_material(self,ident,index=None):
        if self.host.busy:return False
        return self.commit(assembly.insert(self.snapshot(),ident,index),'放入旋律积木')

    def delete_uses(self):
        if self.host.busy:return
        selected=getattr(self,'assembly_selection',set())
        if selected:self.commit(assembly.delete(self.snapshot(),selected),'删除旋律积木')

    def begin_material_drag(self,event,ident):
        if self.host.busy:return
        self.selected_material_id=ident;event.widget.focus_set()
        asset=assembly.material(self.project,ident);sid=assembly.leaves(asset)[0]['origin']['source_id']
        if self.sources.exists(sid):self.sources.selection_set(sid)
        self.library_drag=dict(id=ident,x=event.x_root,y=event.y_root,moved=False)
        self._drag_widget=event.widget;event.widget.grab_set()

    def material_drag_motion(self,event):
        state=getattr(self,'library_drag',None)
        if not state or self.host.busy:return
        state['moved']=state['moved'] or abs(event.x_root-state['x'])+abs(event.y_root-state['y'])>6
        local=SimpleNamespace(x=event.x_root-self.line.winfo_rootx(),y=(event.y_root-self.line.winfo_rooty())/max(.1,self.timeline_scale))
        self.pointer=(local.x,local.y);self.drop_index=self.insertion_at(local.x)
        self.drop_valid=0<=local.x<=self.line.winfo_width() and 24<=local.y<=100
        self.draw();self.schedule_assembly_scroll()

    def material_drag_release(self,event):
        state=getattr(self,'library_drag',None)
        if not state:return
        self.material_drag_motion(event);valid=self.drop_valid and state['moved'];index=getattr(self,'drop_index',len(self.project['uses']))
        ident=state['id'];self.cancel_drag()
        if valid:self.host.safe(lambda:self.insert_material(ident,index))
        else:self.draw_source_cards()

    def insertion_at(self,x):
        at=self.line.canvasx(x)
        for i,v in enumerate(self.project['curve']):
            if at<(self.px(v['start'])+self.px(v['end']))/2:return i
        return len(self.project['uses'])

    def schedule_assembly_scroll(self):
        if self.scroll_timer is None and (self.pointer[0]<28 or self.pointer[0]>self.line.winfo_width()-28):self.scroll_timer=self.line.after(70,self.assembly_scroll)

    def assembly_scroll(self):
        self.scroll_timer=None
        if self.host.busy or not (self.drag or getattr(self,'library_drag',None)):return
        x,y=self.pointer;direction=-1 if x<28 else 1 if x>self.line.winfo_width()-28 else 0
        if direction:
            self.line.xview_scroll(24*direction,'units');self.drop_index=self.insertion_at(x);self.draw();self.schedule_assembly_scroll()

    def draw(self):
        if not self.is_assembly():return BlockTimeline.draw(self)
        c=self.line;c.delete('all');c.configure(bg=color('panel'))
        total=self.project['duration'];self.timeline_width=max(100,c.winfo_width()-24,sum(u['material']['ticks']/480 for u in self.project['uses'])*30*ui_scale.factor)
        self.timeline_scale=max(.1,c.winfo_height()/310) if c.winfo_height()>1 else 1.
        c.configure(scrollregion=(0,0,self.timeline_width+24,max(1,c.winfo_height())))
        self.grid_info.set(f'{len(self.project["uses"])} 积木 · {sum(u["material"]["ticks"] for u in self.project["uses"])/480:g} 拍 · {self.project["bpm"]:g} BPM')
        self.regions=[];self.origin_boxes=[];self.preview_boxes=[];self.intensity_handles=[]
        if hasattr(self.host,'status_duration'):self.host.status_duration.configure(text=f'{total:g} 秒')
        if not total:
            shape=rounded(c,12,28,self.timeline_width+12,106,color('inset'),color('muted'),2,radius=18);c.itemconfigure(shape,dash=(5,4))
            c.create_text(self.timeline_width/2,54,text='拖入旋律分块，搭建你的情绪积木',fill=color('ink'),font=font(('Microsoft YaHei UI',11)))
            c.create_text(self.timeline_width/2,82,text='自由排列顺序，再为每块添加情绪与强度',fill=color('muted'),font=font(('Microsoft YaHei UI',9)))
            c.create_text(self.timeline_width/2,200,text='强度线与二维预览将在放入素材后出现',fill=color('muted'),font=font(('Microsoft YaHei UI',9)))
        else:
            if not hasattr(self,'block_motion'):self.block_motion=BlockMotion(c,self.draw)
            targets={u['id']:(self.px(v['start']),self.px(v['end'])) for u,v in zip(self.project['uses'],self.project['curve'])}
            boxes=self.block_motion.boxes(targets,getattr(self,'assembly_settling',False))
            if self.block_motion.timer is None:self.assembly_settling=False
            selected=getattr(self,'assembly_selection',set())
            for i,(v,u) in enumerate(zip(self.project['curve'],self.project['uses'])):
                a,b=boxes[u['id']];shade=COLORS[u['emotion']]
                brick(c,a,34,b,96,shade,i in selected)
                text=f'{i+1} · {u["material"]["name"]}'
                c.create_text((a+b)/2,55,text=elide(c,text,max(5,b-a-8),font(('Microsoft YaHei UI',9))),fill=color('ink'),font=font(('Microsoft YaHei UI',9)))
                c.create_text((a+b)/2,80,text=elide(c,f'{u["material"]["ticks"]/480:g} 拍 · '+block_audition.engine.music.EMOTIONS[u['emotion']].split('／')[0],max(5,b-a-8),font(('Microsoft YaHei UI',8))),fill=color('ink'),font=font(('Microsoft YaHei UI',8)))
                self.regions.append((i,self.px(v['start']),self.px(v['end'])))
            points=self.curve_preview if self.drag and self.drag[0]=='assembly-intensity' else intensity_curve.controls(self.project)
            self.intensity_handles=[]
            c.create_text(14,117,text='强度线 · 双击添点',anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
            for level in (0,.5,1):
                y=206-62*level;c.create_line(12,y,self.timeline_width+12,y,fill=color('line'))
                c.create_text(self.timeline_width+12,y,text=f'{level*100:g}%',anchor='e',fill=color('muted'),font=font(('Segoe UI',8)))
            coordinates=[]
            for i in range(min(1200,int(self.timeline_width))+1):
                t=total*i/min(1200,int(self.timeline_width));coordinates.extend((self.px(t),206-62*intensity_curve.evaluate(points,t)))
            c.create_line(*coordinates,fill=color('memory'),width=2)
            for i,p in enumerate(points):
                x=self.px(p['time']);y=206-62*p['level'];self.intensity_handles.append((i,x,y))
                c.create_oval(x-5,y-5,x+5,y+5,fill=color('memory'),outline=color('ink'))
            c.create_line(12,222,self.timeline_width+12,222,fill=color('line'))
            c.create_text(14,232,text='二维预览 · 0–100% · 每个外框对应一个用户积木',anchor='w',fill=color('muted'),font=font(('Microsoft YaHei UI',8)))
            # Full continuous curve in the 2D view; frames remain horizontal.
            coords=[]
            for i in range(min(1200,int(self.timeline_width))+1):
                t=total*i/min(1200,int(self.timeline_width));coords.extend((self.px(t),296-48*intensity_curve.evaluate(points,t)))
            c.create_line(*coords,fill=color('memory'),width=2)
            for i,(v,u) in enumerate(zip(self.project['curve'],self.project['uses'])):
                a=self.px(v['start']);b=self.px(v['end']);mid=(v['start']+v['end'])/2;center=296-48*intensity_curve.evaluate(points,mid)
                brick(c,a,center-8,b,center+8,COLORS[u['emotion']],i in selected)
                self.preview_boxes.append((i,a,center-8,b,center+8,mid))
                c.create_text((a+b)/2,center,text=str(i+1),fill=color('ink'),font=font(('Segoe UI',8)))
                if u['material']['kind']=='combination':c.create_line(a+6,center+5,b-6,center+5,fill=color('ink'),dash=(2,3))
            auto=self.planned.get('anchors',[]) if self.planned else []
            for anchor in auto:
                c.create_text(self.px(anchor['actual']),128,text='◆',fill=color('memory'),font=font(('Segoe UI',10)))
        if getattr(self,'drop_valid',False):
            index=self.drop_index;time=self.project['curve'][index]['start'] if index<len(self.project['curve']) else total
            x=self.px(time) if total else 16;c.create_line(x,25,x,106,fill=color('accent'),width=3)
        c.scale('all',0,0,1,self.timeline_scale)

    def px(self,time):
        if self.is_assembly() and not self.project['duration']:return 12
        return BlockTimeline.px(self,time)

    def press(self,event):
        if not self.is_assembly():return BlockTimeline.press(self,event)
        if self.host.busy:return
        self.cancel_drag();self.line.focus_set();x=self.line.canvasx(event.x)
        if 116<=event.y<=214:
            index=next((i for i,a,b in self.intensity_handles if abs(x-a)<=12 and abs(event.y-b)<=12),None)
            if index is not None:
                self.drag=('assembly-intensity',index);self.curve_preview=copy.deepcopy(self.project['intensity_points'])
                self.drag_start=(event.x,event.y);self.intensity_origin=self.curve_preview[index]['level'];self.line.grab_set()
            return
        index=next((i for i,a,b in self.regions if a<=x<b),None) if 24<=event.y<=106 else None
        if index is None:return
        if getattr(event,'state',0)&1 and getattr(self,'assembly_selection',set()):
            first=min(self.assembly_selection);self.assembly_selection=set(range(min(first,index),max(first,index)+1))
        else:self.assembly_selection={index}
        self.selected_region=('curve',index)
        self.drag=('assembly-paint' if self.paint_emotion else 'assembly-move',index)
        self.drag_start=(event.x,event.y);self.drop_index=index;self.drop_valid=True;self.pointer=(event.x,event.y);self.line.grab_set();self.draw();self.update_generation_controls()

    def motion(self,event):
        if not self.is_assembly():return BlockTimeline.motion(self,event)
        if not self.drag or self.host.busy:return
        self.pointer=(event.x,event.y)
        if self.drag[0]=='assembly-intensity':
            self.curve_preview[self.drag[1]]['level']=max(0,min(1,self.intensity_origin+(self.drag_start[1]-event.y)/62))
        elif self.drag[0]=='assembly-move':
            self.drop_index=self.insertion_at(event.x);self.drop_valid=0<=event.x<=self.line.winfo_width() and 24<=event.y<=106;self.schedule_assembly_scroll()
        else:
            x=self.line.canvasx(event.x);index=next((i for i,a,b in self.regions if a<=x<b),None)
            if index is not None:self.assembly_selection.add(index)
        self.draw()

    def release(self,event):
        if not self.is_assembly():return BlockTimeline.release(self,event)
        if not self.drag:return
        self.motion(event);kind,index=self.drag;points=copy.deepcopy(self.curve_preview)
        selection=set(getattr(self,'assembly_selection',set()));valid=self.drop_valid
        target=getattr(self,'drop_index',index)-(1 if getattr(self,'drop_index',index)>index else 0)
        moved=abs(event.x-self.drag_start[0])+abs(event.y-self.drag_start[1])>6 if kind!='assembly-intensity' else False
        self.cancel_drag()
        if self.host.busy:return
        if kind=='assembly-intensity':
            p=self.snapshot();p['intensity_points']=points;self.commit(p,'调整连续强度')
        elif kind=='assembly-paint':self.commit(assembly.paint(self.snapshot(),selection,self.paint_emotion),'整块涂色情绪')
        elif valid and moved:
            self.assembly_settling=True;self.commit(assembly.reorder(self.snapshot(),index,target),'移动旋律积木')
        self.assembly_selection=selection if kind in ('assembly-paint','assembly-intensity') or not moved else {target if valid else index};self.draw();self.update_generation_controls()

    def cancel_drag(self,event=None):
        widget=getattr(self,'_drag_widget',None)
        if widget:
            try:widget.grab_release()
            except tk.TclError:pass
        self.assembly_settling=False;self._drag_widget=None;self.library_drag=None;self.drop_valid=False
        return BlockTimeline.cancel_drag(self,event)

    def add_intensity_point(self,event):
        if not self.is_assembly() or self.host.busy or not self.project['duration']:return
        event=self.timeline_event(event)
        if not 116<=event.y<=214:return
        p=self.snapshot();time=self.seconds_at(self.line.canvasx(event.x))
        if any(abs(v['time']-time)<1e-6 for v in p['intensity_points']):return
        p['intensity_points'].append(dict(time=time,level=max(0,min(1,(206-event.y)/62))));p['intensity_points'].sort(key=lambda v:v['time'])
        self.commit(p,'添加强度控制点')

    def context_click(self,event):
        if not self.is_assembly():return BlockActions.context_click(self,event)
        if self.host.busy:return
        x=self.line.canvasx(event.x);index=next((i for i,a,b in self.regions if a<=x<b),None)
        if index is None or not (24<=event.y<=106 or event.y>=240):return
        if index not in getattr(self,'assembly_selection',set()):self.assembly_selection={index}
        menu=tk.Menu(self.line,tearoff=False);self.context_menu=menu
        menu.add_command(label='删除所选积木',command=lambda:self.host.safe(self.delete_uses))
        menu.add_command(label='另存为组合素材',command=lambda:self.host.safe(self.save_selected_combination),state='normal' if len(self.assembly_selection)>1 else 'disabled')
        menu.add_command(label='查看旋律组成',command=lambda:self.show_material_info(self.project['uses'][index]['material']))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def timeline_hint(self,event):
        if not self.is_assembly():return BlockTimeline.timeline_hint(self,event)
        x=self.line.canvasx(event.x);index=next((i for i,a,b in self.regions if a<=x<b),None)
        if index is None:return '拖入分块组装；Shift 连续选择；Delete 删除；Esc 取消拖动。'
        use=self.project['uses'][index]
        details=f'{index+1} · {use["material"]["name"]} · {use["material"]["ticks"]/480:g} 拍\n'+assembly.composition(use['material'])+' · '+block_audition.engine.music.EMOTIONS[use['emotion']]
        if self.planned:
            rows=[r for r in self.planned['blocks'] if r.get('use_id')==use['id']]
            details+='\n内部生成：'+', '.join(dict.fromkeys(r['kind'] for r in rows))
        return details+'\n移动素材与情绪；强度线保持在原时间。'

    def hover(self,event):
        if not self.is_assembly():return BlockTimeline.hover(self,event)

    def leave(self,event):
        if not self.is_assembly():return BlockTimeline.leave(self,event)
