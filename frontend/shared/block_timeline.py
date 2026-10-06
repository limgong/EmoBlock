from ui_scale import font as scaled_font
from ui_theme import color as theme_color
"""Canvas interaction for the block-based emotion timeline."""
from types import SimpleNamespace
import emotion_input
import intensity_curve
import block_editor
import block_labels
import story_engine as engine
from ui_hints import rounded
from block_visuals import brick, BlockMotion

COLORS=dict(calm='#8fcddd',hope='#ebd18c',sad='#a6a6df',suspense='#c8a6df',crisis='#e99c98',resolve='#97d9ba')
LABELS=engine.music.EMOTIONS
DRAG_LABELS=dict(move='移动情绪段',boundary='调整段落边界',paint='情绪涂色',intensity='调整强度')


class BlockTimeline:
    def px(self,time):return 12+self.timeline_width*time/self.project['duration']

    def draw(self):
        c=self.line;c.delete('all')
        project=self.drag_preview or self.project;total=project['duration'];grid=emotion_input.grid_seconds(project)
        self.timeline_width=max(100,c.winfo_width()-24,(len(grid)-1)*40)
        c.configure(scrollregion=(0,0,self.timeline_width+24,310))
        self.grid_info.set(f'{len(grid)-1} 块 · {project["bpm"]:g} BPM')
        if hasattr(self.host,'status_duration'):self.host.status_duration.configure(text=f'{total:.1f} 秒 · {len(grid)-1} 块')
        self.regions=[];self.origin_boxes=[]
        font=scaled_font(('Microsoft YaHei UI',9))
        def text(x,y,value,space,color=theme_color('#14212a'),bold=False):
            usefont=scaled_font(('Microsoft YaHei UI',9,'bold')) if bold else font
            if int(c.tk.call('font','measure',usefont,value))<=space:
                c.create_text(x,y,text=value,fill=color,font=usefont)
        for n,t in enumerate(grid[:-1]):
            x=self.px(t)
            c.create_text((x+self.px(grid[n+1]))/2,16,text=str(n+1),fill=theme_color('#8ea4b8'),font=scaled_font(('Segoe UI',8)))
            c.create_line(x,132,x,212,fill=theme_color('#1c2b38'))
        if not hasattr(self,'block_motion'):self.block_motion=BlockMotion(c,self.draw)
        targets={};counts={};keys=[]
        for v in project['curve']:
            signature=(v['emotion'],round(v['end']-v['start'],5),v.get('source_id'))
            count=counts.get(signature,0);counts[signature]=count+1;key=(signature,count);keys.append(key)
            targets[key]=(self.px(v['start'])+3,self.px(v['end'])-3)
        moving=bool(self.drag and self.drag[0]=='move' and self.drag_preview)
        boxes=self.block_motion.boxes(targets,moving or getattr(self,'settling',False))
        if self.block_motion.timer is None:self.settling=False
        for i,v in enumerate(project['curve']):
            a=self.px(v['start'])+3;b=self.px(v['end'])-3;color=COLORS[v['emotion']]
            hit_a,hit_b=a,b;a,b=boxes[keys[i]]
            selected=self.selected_region==('curve',i) and not self.drag_preview
            border=theme_color('#ffffff') if selected or self.hover_region==i else color
            placeholder=moving and getattr(self,'drag_slot',None) and abs(v['start']-self.drag_slot[0])<1e-6
            if placeholder:
                shape=rounded(c,hit_a,36,hit_b,106,theme_color('inset'),color,2)
                c.itemconfigure(shape,dash=(4,4))
            else:brick(c,a,36,b,106,color,selected or self.hover_region==i)
            # One central stud per draggable emotion segment matches the preview.
            slots=[(start,end) for start,end in zip(grid,grid[1:]) if v['start']<=start<v['end']]
            label=LABELS[v['emotion']].split('／')[0]
            if not placeholder:
                text((a+b)/2,58,label,b-a-8,bold=True)
                text((a+b)/2,87,f'{len(slots)} 块',b-a-8)
            self.regions.append((i,hit_a-3,hit_b+3))
        controls=getattr(self,'curve_preview',None) or intensity_curve.controls(project)
        c.create_text(16,128,text='强度',anchor='w',fill=theme_color('#8ea4b8'),font=font)
        c.create_line(12,115,self.timeline_width+12,115,fill=theme_color('line'))
        c.create_text(self.timeline_width+12,128,text='◆ 记忆点',anchor='e',fill=theme_color('memory'),font=font)
        coordinates=[]
        for i in range(min(1200,int(self.timeline_width))+1):
            t=total*i/min(1200,int(self.timeline_width))
            coordinates.extend((self.px(t),206-62*intensity_curve.evaluate(controls,t)))
        c.create_line(*coordinates,fill=theme_color('#f1df9a'),width=2)
        self.intensity_handles=[]
        for i,p in enumerate(controls):
            x=self.px(p['time']);y=206-62*p['level'];self.intensity_handles.append((i,x,y))
            active=self.drag and self.drag[0]=='intensity' and self.drag[2]==i
            radius=7 if active else 5
            c.create_oval(x-radius,y-radius,x+radius,y+radius,fill=theme_color('#f1df9a'),outline=theme_color('#ffffff'),width=2 if active else 1)
            if active:c.create_text(x,y-18,text=f'{p["level"]:.0%}',fill=theme_color('#f1df9a'),font=font)
        for i,a in enumerate(project['anchors']):
            x=self.px(a['time']);c.create_line(x,26,x,211,fill=theme_color('#eff6fa'),dash=(3,4))
            c.create_line(x,121,self.px(a['time']+a.get('hold',2.)),121,fill=COLORS[a['emotion']],width=3)
            c.create_polygon(x,111,x-6,119,x,127,x+6,119,fill=COLORS[a['emotion']],outline='white')
        automatic=engine.automatic_peak_anchor(dict(project,intensity_points=controls))
        if automatic:
            x=self.px(automatic.get('memory_time',automatic['time']))
            c.create_line(x,140,x,211,fill=theme_color('memory'),dash=(3,4))
            c.create_polygon(x,135,x-4,139,x,143,x+4,139,fill=theme_color('memory'),outline='')
        status=getattr(self,'preview_status','')
        c.create_line(12,217,self.timeline_width+12,217,fill=theme_color('line'))
        c.create_text(16,229,text='拼接预览',anchor='w',fill=theme_color('muted'),font=font)
        c.create_text(self.timeline_width+12,229,text=status or '已更新',anchor='e',fill=theme_color('muted'),font=font)
        if self.planned and not self.drag_preview:
            selected=self.blocks.selection()
            for n,r in enumerate(self.planned['blocks']):
                a=self.px(r['start_seconds'])+2;b=self.px(r['end_seconds'])-2
                color=COLORS[r['emotion']];connection=r['kind']!='content'
                self.origin_boxes.append((a,b,r['id']))
                origin=block_labels.labels(self.planned,r)['short'].split('\n')[0]
                shape=rounded(c,a,247,b,286,theme_color('selected') if r['id'] in selected else theme_color('inset'),color,2.5 if r['id'] in selected else 1.5,radius=6)
                if connection:c.itemconfigure(shape,dash=(3,3))
                spans=r.get('source_spans',[])
                source_ids=[s['id'] for s in project['sources']]
                if spans and spans[0]['source_id'] in source_ids:
                    label=f'M{source_ids.index(spans[0]["source_id"])+1}·{spans[0]["start"]//1920+1}'
                else:label=str(n+1)
                if connection:label='↔'
                if int(c.tk.call('font','measure',font,label))>b-a-6:label=str(n+1)
                text((a+b)/2,266,label,b-a-6,color=theme_color('memory') if connection else theme_color('muted'))
        else:
            for n,(start,end) in enumerate(zip(grid,grid[1:])):
                a=self.px(start)+3;b=self.px(end)-3
                rounded(c,a,246,b,296,theme_color('#15212c'),theme_color('#2a3d4c'))
                text((a+b)/2,271,str(n+1),b-a-4,color=theme_color('#637e92'))
        if self.drag and self.drag[0] in ('move','boundary','paint'):
            if getattr(self,'drag_slot',None):
                start,end=self.drag_slot;a=self.px(start);b=self.px(end)
                color=theme_color('#f28e89') if self.drag_error else theme_color('#ffffff')
                if b-a>8:rounded(c,a+2,31,b-2,108,'',color,3)
                else:c.create_line(a,30,a,109,fill=color,width=3)
                c.create_polygon(a-5,24,a+5,24,a,31,fill=color)
                value='不能放置' if self.drag_error else f'{start:g}–{end:g}s'
                c.create_text((a+b)/2,16,text=value,fill=color,font=font)

        if self.drag and self.drag[0]=='move' and getattr(self,'pointer',None) and self.drag_preview:
            v=self.project['curve'][self.drag[2]];shift=c.canvasx(self.pointer[0])-self.drag[1]
            a=self.px(v['start'])+3+shift;b=self.px(v['end'])-3+shift
            brick(c,a,36,b,106,COLORS[v['emotion']],True,lift=7,tags='drag-ghost')
            text((a+b)/2,53,LABELS[v['emotion']].split('／')[0],b-a-8,bold=True)
            text((a+b)/2,80,'松开拼接',b-a-8)
        self.timeline_scale=max(.1,c.winfo_height()/310) if c.winfo_height()>1 else 1.
        c.scale('all',0,0,1,self.timeline_scale)
        c.configure(scrollregion=(0,0,self.timeline_width+24,max(1,c.winfo_height())))

    def timeline_hint(self,event):
        if self.drag:return ''
        x=self.line.canvasx(event.x)
        if 244<=event.y<=305 and self.planned:
            ident=next((ident for a,b,ident in self.origin_boxes if a<=x<=b),None)
            if ident:
                block=next(r for r in self.planned['blocks'] if r['id']==ident)
                overridden=any(v['start']<block['end_seconds'] and v['end']>block['start_seconds'] for v in self.project['overrides'])
                hint='\n此处有旧局部修改，优先于涂色和强度；右键可清除。' if overridden else ''
                return block_labels.labels(self.planned,block)['full']+hint+'\n试听使用右侧已生成的历史版本。'
        if 116<=event.y<=214:
            return '上下拖动圆点调整强度。记忆点自动跟随最高点；同高时取最早一处。'
        region=next((i for i,a,b in self.regions if a<=x<=b and 30<=event.y<=108),None)
        if region is not None:
            v=self.project['curve'][region]
            action='左键涂色；再次点击选中的情绪颜色结束涂色。' if self.paint_emotion else '拖动情绪段换顺序，拖动接缝改长度。'
            return f'{LABELS[v["emotion"]]} · {v["start"]:g}–{v["end"]:g}s\n'+action+'\n右键指定旋律来源或移除此情绪段；移除后邻段填补原时间。'
        return '每块四拍。拖到左右边缘可自动滚动。'

    def hover(self,event):
        if self.drag:return
        x=self.line.canvasx(event.x)
        region=next((i for i,a,b in self.regions if a<=x<=b and 30<=event.y<=108),None)
        edge=any(abs(x-self.px(v['end']))<7 for v in self.project['curve'][:-1]) and 40<=event.y<=104
        point=116<=event.y<=214 and any(abs(x-a)<=12 and abs(event.y-b)<=12 for _,a,b in self.intensity_handles)
        cursor='sb_v_double_arrow' if point else 'crosshair' if region is not None and self.paint_emotion else 'sb_h_double_arrow' if edge else 'hand2' if region is not None else ''
        self.line.configure(cursor=cursor)
        if region!=self.hover_region:self.hover_region=region;self.draw()

    def leave(self,event):
        if not self.drag:self.hover_region=None;self.draw()

    def press(self,event):
        if self.host.busy:return
        self.line_hint.hide();self.cancel_drag();self.line.focus_set();x=self.line.canvasx(event.x)
        if event.y>=244 and self.planned:
            selected=next((ident for a,b,ident in self.origin_boxes if a<=x<=b),None)
            if selected:self.blocks.selection_set(selected);self.select_block();self.draw()
            return
        if 116<=event.y<=214:
            hit=next((i for i,a,b in self.intensity_handles if abs(x-a)<=12 and abs(event.y-b)<=12),None)
            if hit is not None:self.drag=('intensity',x,hit);self.curve_preview=intensity_curve.controls(self.project);self.intensity_origin=event.y;self.intensity_moved=False
        elif self.paint_emotion is not None:
            if 30<=event.y<=108:self.drag=('paint',x)
        else:
            edge=next((i for i,v in enumerate(self.project['curve'][:-1]) if abs(x-self.px(v['end']))<=7 and 40<=event.y<=104),None)
            region=next((i for i,a,b in self.regions if a<=x<=b and 30<=event.y<=108),None)
            if edge is not None:self.drag=('boundary',x,edge)
            else:
                self.selected_region=('curve',region) if region is not None else None
                if self.selected_region:
                    key,i=self.selected_region;v=self.project[key][i]
                    self.emotion.set(LABELS[v['emotion']]);self.strength.set(max(v['level'],v.get('end_level',v['level']))*100)
                    self.trend.set('平稳' if v['level']==v.get('end_level',v['level']) else '渐强' if v['level']<v['end_level'] else '渐弱')
                    self.brush_changed();self.level.set(str(v['level']*100));self.end_level.set(str(v.get('end_level',v['level'])*100))
                    if key=='curve':self.drag=('move',x,i)
        if self.drag:self.line.grab_set()
        self.draw()



    def motion(self,event):
        if not self.drag or self.host.busy:return
        self.pointer=(event.x,event.y);x=self.line.canvasx(event.x);kind,left=self.drag[:2]
        if kind!='intensity' and abs(x-left)<4 and self.drag_preview is None:return
        self.drag_error='';self.drag_preview=None;self.drag_slot=None
        try:
            if kind=='intensity':
                # Offset from the pressed level, so returning to the start pixel restores it exactly;
                # the dead zone keeps a plain click from nudging the dot.
                self.intensity_moved=self.intensity_moved or abs(event.y-self.intensity_origin)>=3
                if self.intensity_moved:
                    base=intensity_curve.controls(self.project)[self.drag[2]]['level']
                    self.curve_preview[self.drag[2]]['level']=max(0.,min(1.,base+(self.intensity_origin-event.y)/62))
            elif kind=='paint':
                start,end=emotion_input.snapped_range(self.project,self.seconds_at(left),self.seconds_at(x))
                v=self.values();self.drag_preview=emotion_input.paint_blocks(self.project,start,end,self.paint_emotion,v['level'],v['end_level']);self.drag_slot=(start,end)
            elif kind=='boundary':
                self.drag_preview=emotion_input.resize_boundary(self.project,self.drag[2],self.seconds_at(x))
                edge=self.drag_preview['curve'][min(self.drag[2],len(self.drag_preview['curve'])-1)]['end'];self.drag_slot=(edge,edge)
            else:
                index=self.drag[2];target=block_editor.insertion_index(self.project,index,self.seconds_at(x))
                old=self.project['curve'][index];remaining=[r for i,r in enumerate(self.project['curve']) if i!=index]
                start=sum(r['end']-r['start'] for r in remaining[:target])
                self.drag_slot=(start,start+old['end']-old['start'])
                self.drag_preview=block_editor.reorder(self.project,index,target)
        except ValueError as exc:self.drag_error=str(exc)
        self.line.configure(cursor='fleur' if kind=='move' else 'sb_h_double_arrow' if kind=='boundary' else 'sb_v_double_arrow' if kind=='intensity' else 'crosshair')
        self.draw()
        if kind!='intensity' and (event.x<28 or event.x>self.line.winfo_width()-28) and self.scroll_timer is None:
            self.scroll_timer=self.line.after(70,self.autoscroll)

    def autoscroll(self):
        self.scroll_timer=None
        if not self.drag:return
        x,y=self.pointer;direction=-1 if x<28 else 1 if x>self.line.winfo_width()-28 else 0
        if direction:
            self.line.xview_scroll(24*direction,'units');self.motion(SimpleNamespace(x=x,y=y))

    def cancel_drag(self,event=None):
        if hasattr(self,'block_motion'):self.block_motion.cancel()
        self.settling=False
        if self.scroll_timer:self.line.after_cancel(self.scroll_timer);self.scroll_timer=None
        if self.line.grab_current()==self.line:self.line.grab_release()
        self.drag=None;self.drag_preview=None;self.drag_slot=None;self.curve_preview=None;self.drag_error=''
        self.line.configure(cursor='');self.draw()
        return 'break'

    def release(self,event):
        if not self.drag:return
        kind=self.drag[0];start=self.drag[1]
        self.motion(event)
        preview=self.drag_preview;error=self.drag_error
        if kind=='intensity':
            preview=self.snapshot();preview['intensity_points']=self.curve_preview
        elif kind=='paint' and abs(self.line.canvasx(event.x)-start)<4:
            grid=emotion_input.grid_seconds(self.project);time=self.seconds_at(start)
            index=min(len(grid)-2,next((i for i in range(len(grid)-1) if grid[i]<=time<grid[i+1]),len(grid)-2))
            v=self.values();preview=emotion_input.paint_blocks(self.project,grid[index],grid[index+1],self.paint_emotion,v['level'],v['end_level'])
        drop=None
        if kind=='move' and preview is not None and not error:
            v=self.project['curve'][self.drag[2]];shift=self.line.canvasx(self.pointer[0])-start
            signature=(v['emotion'],round(v['end']-v['start'],5),v.get('source_id'))
            drop=(signature,(self.px(v['start'])+3+shift,self.px(v['end'])-3+shift))
        self.cancel_drag()
        if self.host.busy:return
        if error:self.host.tell(error,True)
        elif preview is not None and preview!=self.project:
            if drop:
                self.settling=True;self.block_motion.positions[(drop[0],0)]=drop[1]
            label=DRAG_LABELS[kind]
            if self.host.safe(lambda:self.commit(preview,label)):self.host.tell('已'+label+' · '+self.undo_hint())
