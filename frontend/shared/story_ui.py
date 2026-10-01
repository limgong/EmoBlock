from ui_scale import font as scaled_font
from ui_theme import color as theme_color
"""Single-window simplified workflow; legacy editors remain available."""
import copy
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import story_engine as engine
import emotion_input
import default_melody
import block_labels
import block_audition
import intensity_curve
import block_editor
from ui_hints import Tooltip, rounded
from block_timeline import BlockTimeline
from block_actions import BlockActions
from auto_preview import PreviewPlanner
from window_ui import RoundedPanel
import ui_scale

LABELS=engine.music.EMOTIONS
ROLE_LABELS={'auto':'自动判断','main':'主基调','secondary':'副旋律','climax':'爆点','ending':'结尾'}
COLORS=dict(calm='#8fcddd',hope='#ebd18c',sad='#a6a6df',suspense='#c8a6df',crisis='#e99c98',resolve='#97d9ba')


class StoryPage(BlockActions,BlockTimeline,ttk.Frame):
    def __init__(self,parent,host):
        super().__init__(parent);self.host=host;self.project=emotion_input.default_story();self.planned=None;self.history=[];self.drag=None;self.source=None;self.path=None
        self.project['sources']=[default_melody.source()]
        self.project['continuous_intensity']=True
        self.project=engine.automatic_memory_project(emotion_input.normalize(self.project))
        self.duration=tk.StringVar(value=str(self.project['duration']));self.bpm=tk.StringVar(value='120')
        self.melody_only=tk.BooleanVar(value=False)
        self.track=tk.StringVar();self.role=tk.StringVar(value='自动判断');self.policy=tk.StringVar(value='同时起音取高音')
        self.level=tk.StringVar(value='25');self.end_level=tk.StringVar(value='45')
        self.emotion=tk.StringVar(value=LABELS['calm'])
        self.paint_emotion=None;self.strength=tk.DoubleVar(value=35);self.trend=tk.StringVar(value='平稳')
        self.brush_text=tk.StringVar();self.selected_region=None
        self.message=tk.StringVar(value='')
        self.drag_preview=None;self.drag_error='';self.scroll_timer=None;self.hover_region=None
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        self.source_panel=RoundedPanel(self,padding=10,height=176)
        self.source_panel.grid(row=0,column=0,sticky='ew',pady=(8,10))
        self.editor_panel=RoundedPanel(self,padding=10)
        self.editor_panel.grid(row=1,column=0,sticky='nsew')
        self.canvas=tk.Canvas(self,highlightthickness=0,bg=theme_color('bg'))  # legacy scroll adapter, not displayed
        body=self.source_panel.body
        self.source_page=0;self.source_card_columns=1
        row=self.row(body)
        ttk.Label(row,text='旋律素材',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(side='left',padx=(0,16))
        source_import=self.btn(row,'＋ 导入',self.choose,'选择或拖入 MIDI / MMP。默认同时起音取高音，多音轨选择较高声部。')
        source_import.configure(style='PanelQuiet.TButton',width=6)
        source_header=row
        self.tracks=ttk.Combobox(row,textvariable=self.track,state='readonly',width=28)
        self.sources=ttk.Treeview(body,columns=('role','beats'),show='tree headings',height=3)
        self.sources.heading('#0',text='输入旋律（保存音符快照，不依赖原文件）');self.sources.heading('role',text='用途');self.sources.heading('beats',text='拍数')
        self.sources.column('#0',width=390);self.sources.column('role',width=90);self.sources.column('beats',width=60)
        self.source_cards=ttk.Frame(body);self.source_cards.pack(fill='x',pady=(2,0))
        self.source_cards.bind('<Configure>',self.resize_source_cards)
        self.source_detail_button=self.btn(source_header,'分块试听 ▸',self.toggle_source_details,'展开四拍分块、旋律音符和输入试听。卡片上的播放按钮也可直接试听。')
        self.source_detail_button.configure(style='PanelQuiet.TButton')
        source_import.pack_forget();self.source_detail_button.pack_forget()
        self.source_detail_button.pack(side='right');source_import.pack(side='right',padx=6)
        self.source_page_label=tk.StringVar()
        self.source_prev=self.btn(source_header,'‹',lambda:self.page_sources(-1),'上一页素材')
        self.source_next=self.btn(source_header,'›',lambda:self.page_sources(1),'下一页素材')
        ttk.Label(source_header,textvariable=self.source_page_label,style='Muted.TLabel').pack(side='right')
        self.source_details=tk.Toplevel(self);self.source_details.withdraw();self.source_details.title('旋律分块试听')
        self.source_details.geometry('760x460');self.source_details.transient(self.host.root)
        self.source_details.protocol('WM_DELETE_WINDOW',self.source_details.withdraw)
        source_body=ttk.Frame(self.source_details,padding=12);source_body.pack(fill='both',expand=True)
        self.source_audio=None;self.source_seek=False
        row=self.row(source_body)
        self.source_play_button=ttk.Button(row,text='▶ 播放 / 暂停',command=lambda:self.host.safe(self.toggle_source_play))
        self.source_time=tk.StringVar(value='选择一张旋律卡片');ttk.Label(row,textvariable=self.source_time).pack(side='left',padx=6)
        self.source_slider=ttk.Scale(source_body,from_=0,to=100,orient='horizontal',cursor='hand2');self.source_slider.pack(fill='x')
        for event,phase in [('<ButtonPress-1>','start'),('<B1-Motion>','move'),('<ButtonRelease-1>','end')]:
            self.source_slider.bind(event,lambda e,p=phase:self.source_seek_event(e,p))
        self.source_settings=ttk.Frame(body);self.selected_role=tk.StringVar(value='自动判断')
        ttk.Label(self.source_settings,text='选中素材用途').pack(side='left')
        ttk.Combobox(self.source_settings,textvariable=self.selected_role,values=list(ROLE_LABELS.values()),state='readonly',width=12).pack(side='left',padx=5)
        self.btn(self.source_settings,'应用用途',self.apply_source_role)
        self.sources.bind('<<TreeviewSelect>>',lambda _:self.refresh_source_blocks())
        self.input_blocks=ttk.Treeview(body,columns=('beats','seconds','notes'),show='tree headings',height=3)
        for col,label in [('#0','所选输入旋律 · 四拍分块'),('beats','拍范围'),('seconds','秒范围'),('notes','音符数')]:
            self.input_blocks.heading(col,text=label);self.input_blocks.column(col,width=125)
        self.input_blocks.column('#0',width=220)
        self.block_cards=ttk.Frame(source_body);self.block_cards.pack(fill='x',pady=4)
        self.block_cards.bind('<Configure>',self.resize_block_cards)
        self.input_blocks.bind('<<TreeviewSelect>>',lambda _:self.draw_source_notes())
        self.input_blocks.bind('<Double-1>',lambda _:self.host.safe(self.play_source_block))
        self.source_notes=tk.Canvas(source_body,height=75,bg=theme_color('#0c131c'),highlightthickness=0);self.source_notes.pack(fill='x')
        self.source_notes.bind('<Configure>',lambda _:self.draw_source_notes())
        row=self.row(source_body);self.btn(row,'▶ 这一块',self.play_source_block);self.btn(row,'下一块',self.next_source_block);self.btn(row,'■ 停止',self.host.stop_playback)
        body=self.editor_panel.body
        row=self.row(body);self.editor_heading=row
        ttk.Label(row,text='情绪积木',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(side='left',padx=(0,16))
        self.grid_info=tk.StringVar();ttk.Label(row,textvariable=self.grid_info,style='Muted.TLabel').pack(side='right')
        row=self.row(body);self.emotion_buttons={};self.emotion_swatches=[]
        for key,label in LABELS.items():
            swatch=tk.PhotoImage(master=self,width=9,height=9);swatch.put(COLORS[key],to=(0,0,9,9));self.emotion_swatches.append(swatch)
            b=tk.Button(row,image=swatch,compound='left',text=label.split('／')[0],command=lambda k=key:self.host.safe(lambda:self.select_palette(k)),
                        bg=theme_color('panel'),fg=theme_color('ink'),activebackground=theme_color('hover'),activeforeground=theme_color('ink'),
                        relief='flat',bd=0,padx=6,pady=5,cursor='hand2',highlightthickness=2,
                        highlightbackground=theme_color('panel'),font=scaled_font(('Microsoft YaHei UI',9)))
            b.pack(side='left',padx=2);self.emotion_buttons[key]=b
            Tooltip(b,label+'：点击后在积木区左键涂色，再点一次此颜色退出涂色。强度圆点始终可直接拖动。')
        tools=ttk.Frame(row);tools.pack(side='right')
        for text,command,hint in [('−',lambda:self.resize_timeline(-1),'缩短四拍'),('＋',lambda:self.resize_timeline(1),'增加四拍'),('↶',self.undo,'撤销 · Ctrl+Z')]:
            b=ttk.Button(tools,text=text,width=2,style='Compact.TButton',command=lambda fn=command:self.host.safe(fn));b.pack(side='left',padx=2)
            Tooltip(b,hint)
        self.line=tk.Canvas(body,height=310,bg=theme_color('panel'),highlightthickness=0,takefocus=True,xscrollincrement=24);self.line.pack(fill='both',expand=True,pady=(4,0))
        timeline_scroll=ttk.Scrollbar(body,orient='horizontal',command=self.line.xview);timeline_scroll.pack(fill='x',pady=(0,2))
        def scroll_state(first,last):
            timeline_scroll.set(first,last)
            if float(first)<=.00001 and float(last)>=.99999:timeline_scroll.pack_forget()
            elif not timeline_scroll.winfo_manager():timeline_scroll.pack(fill='x',after=self.line,pady=(0,2))
        self.line.configure(xscrollcommand=scroll_state)
        self.source_legend=tk.StringVar()
        self.line.bind('<Configure>',lambda e:self.draw());self.line.bind('<Button-1>',lambda e:self.press(self.timeline_event(e)));self.line.bind('<B1-Motion>',lambda e:self.motion(self.timeline_event(e)));self.line.bind('<ButtonRelease-1>',lambda e:self.release(self.timeline_event(e)))
        self.line.bind('<Motion>',lambda e:self.hover(self.timeline_event(e)));self.line.bind('<Leave>',self.leave)
        import ui_platform
        for event in ui_platform.CONTEXT_EVENTS:self.line.bind(event,lambda e:self.host.safe(lambda:self.context_click(self.timeline_event(e))))
        self.line.bind('<Escape>',self.cancel_drag);self.line.bind('<Control-z>',lambda e:self.host.safe(self.undo))
        self.line_hint=Tooltip(self.line,lambda e:self.timeline_hint(self.timeline_event(e)))
        self.footer=ttk.Frame(body);self.footer.pack(side='bottom',fill='x',before=self.line,pady=(4,0))
        self.generate_button=ttk.Button(self.footer,text='生成连续成品',style='Accent.TButton',command=lambda:self.host.safe(self.generate))
        self.generate_button.pack(side='right')
        melody_toggle=ttk.Checkbutton(self.footer,text='仅主旋律',variable=self.melody_only,command=lambda:self.host.safe(lambda:self.commit(self.snapshot())))
        melody_toggle.pack(side='left')
        Tooltip(melody_toggle,'统一乐器和力度，关闭伴奏与情绪配器；保留积木排布和连接。')
        self.blocks=ttk.Treeview(body,columns=('time','type','emotion'),show='tree headings',height=6)
        for key,label in [('#0','生成块'),('time','时间（秒）'),('type','类型'),('emotion','情绪')]:self.blocks.heading(key,text=label);self.blocks.column(key,width=150)
        self.blocks.bind('<<TreeviewSelect>>',self.select_block)
        self.blocks.configure(style='SourceBlocks.Treeview')
        ttk.Style(self).configure('SourceBlocks.Treeview',rowheight=56)
        self.blocks.column('#0',width=290,minwidth=180)
        self.plan_warning_text=''
        note=ttk.Label(body,textvariable=self.message,wraplength=740,justify='left',style='Muted.TLabel');Tooltip(self.generate_button,lambda _:self.plan_warning_text or '按当前积木顺序与情绪重新生成整曲。')
        Tooltip(note,lambda _:self.plan_warning_text or self.message.get())
        self.preview_status=''
        self.preview_planner=PreviewPlanner(self.after,self.after_cancel,engine.plan,self.accept_preview,self.preview_failed)
        self.bind('<Destroy>',lambda event:self.preview_planner.close() if event.widget is self else None,add='+')
        self.refresh()
        self.trend.trace_add('write',lambda *args:self.brush_changed())
        self.pick_emotion('calm')
        for var in (self.duration,self.bpm,self.melody_only):var.trace_add('write',lambda *args:setattr(self.host,'dirty',True))
        try:
            import file_drop
            self.file_drop=file_drop.FileDrop(self.host.root,lambda paths:self.host.safe(lambda:self.drop_sources(paths)))
        except (OSError,AttributeError) as exc:
            self.message.set('拖入文件不可用，可用“选择旋律文件”：'+str(exc))

    def timeline_event(self,event):
        from types import SimpleNamespace
        values=dict(vars(event));values['y']=event.y/max(.1,getattr(self,'timeline_scale',1.))
        return SimpleNamespace(**values)

    def row(self,parent):
        row=ttk.Frame(parent);row.pack(fill='x',pady=2);return row

    def selected_source(self):
        ids=self.sources.selection()
        source=next((s for s in self.project['sources'] if ids and s['id']==ids[0]),None)
        if source is None:raise ValueError('请先选择旋律卡片。')
        return source

    def resize_source_cards(self,event):
        width=max(200,event.width)
        if width!=getattr(self,'source_card_width',0):
            self.source_card_width=width;self.draw_source_cards()

    def draw_source_cards(self):
        for child in self.source_cards.winfo_children():child.destroy()
        self.card_play_buttons={};self.card_role_buttons={};self.card_delete_buttons={}
        count=max(1,len(self.project['sources']));self.source_page=min(self.source_page,count-1)
        self.source_page_label.set(f'{self.source_page+1} / {count}' if count>1 else '')
        for arrow in (self.source_prev,self.source_next):
            if count>1:arrow.pack(side='left',padx=(0,5))
            else:arrow.pack_forget()
        if not self.project['sources']:return
        i=self.source_page;s=self.project['sources'][i];width=max(240,getattr(self,'source_card_width',600))
        card=tk.Canvas(self.source_cards,width=width,height=round(94*ui_scale.factor),bg=theme_color('panel'),highlightthickness=0,takefocus=True,cursor='hand2')
        card.pack(fill='x')
        shape=rounded(card,1,1,width-2,93,theme_color('inset'),theme_color('line'),radius=14)
        card.create_text(27,40,text='♫',fill=theme_color('accent'),font=scaled_font(('Segoe UI',22)))
        title=s['name'].replace('默认 · ','')
        if s.get('builtin_default'):title='欢乐颂 · 主题旋律'
        card.create_text(55,20,text=title,anchor='w',width=max(140,width-130),fill=theme_color('ink'),font=scaled_font(('Microsoft YaHei UI',10)))
        metadata=card.create_text(55,42,text=f'M{i+1:02}     {s["ticks"]/480:g} 拍',anchor='w',fill=theme_color('muted'),font=scaled_font(('Microsoft YaHei UI',8)))
        role_button=ttk.Menubutton(card,text=ROLE_LABELS[s['role']]+' ▾',width=8,style='Card.TMenubutton')
        role_button.configure(style='SourceRole.TMenubutton')
        ttk.Style(card).configure('SourceRole.TMenubutton',font=scaled_font(('Microsoft YaHei UI',9)),padding=(6,3))
        menu=tk.Menu(role_button,tearoff=False,font=scaled_font(('Microsoft YaHei UI',10)))
        for key,label in ROLE_LABELS.items():
            menu.add_command(label=label,command=lambda sid=s['id'],role=key:self.host.safe(lambda:self.set_card_role(sid,role)))
        menu.add_separator();menu.add_command(label='删除此素材',command=lambda sid=s['id']:self.host.safe(lambda:self.card_action(sid,'delete')))
        role_button.configure(menu=menu)
        role_x=card.bbox(metadata)[2]+round(16*ui_scale.factor)
        role_item=card.create_window(role_x,42,window=role_button,anchor='w')
        self.card_role_buttons[s['id']]=role_button
        notes=s['notes'];low=min(n['pitch'] for n in notes);high=max(n['pitch'] for n in notes)
        strip=min(230,width-130)
        for n in notes:
            x=55+strip*n['start']/s['ticks'];end=55+strip*(n['start']+n['duration'])/s['ticks']
            y=78-14*(n['pitch']-low)/max(1,high-low)
            card.create_rectangle(x,y,max(x+1,end-2),y+3,fill=theme_color('accent'),outline='')
        play_button=ttk.Button(card,text='▶',width=3,style='Compact.TButton',command=lambda sid=s['id']:self.host.safe(lambda:self.card_action(sid,'play')))
        card.create_window(width-28,44,window=play_button,height=30,width=32)
        self.card_play_buttons[s['id']]=play_button
        card.scale('all',0,0,1,ui_scale.factor)
        # Set embedded-widget dimensions after Canvas scaling to avoid scaling twice.
        card.itemconfigure(role_item,width=round(98*ui_scale.factor),height=round(26*ui_scale.factor))
        Tooltip(card,s['name']+'\n点击试听；用途菜单可更改用途或删除素材。')
        card.bind('<Button-1>',lambda event,sid=s['id']:self.host.safe(lambda:self.select_source_card(sid)))
        card.bind('<Return>',lambda event,sid=s['id']:self.host.safe(lambda:self.select_source_card(sid)))
        card.bind('<Delete>',lambda event:self.host.safe(lambda:self.card_action(s['id'],'delete')))

    def card_action(self,sid,action):
        self.sources.selection_set(sid)
        if action=='delete':self.remove_source();return
        self.refresh_source_blocks();self.draw_source_cards();self.toggle_source_play()

    def set_card_role(self,sid,role):
        if role not in ROLE_LABELS:raise ValueError('无效素材用途。')
        project=self.snapshot();source=next(s for s in project['sources'] if s['id']==sid)
        source['role']=role;self.sources.selection_set(sid);self.commit(project)

    def select_source_card(self,sid):
        self.sources.selection_set(sid);self.refresh_source_blocks();self.draw_source_cards()
        self.source_settings.pack_forget();self.source_seek=False;self.source_slider['value']=0
        self.start_source_audio()

    def start_source_audio(self,fraction=0.):
        self.source_block_playing=None
        source=copy.deepcopy(self.selected_source());bpm=self.project['bpm']
        self.host.stop_playback();self.source_time.set('准备试听…')
        def done(result):
            path,rows=result
            self.source_audio=dict(id=source['id'],path=path,rows=rows,bpm=bpm)
            self.host.stop_playback();self.host.play_blocks=rows
            start=min(rows[-1]['end_seconds']-.01,max(0.,fraction)*rows[-1]['end_seconds'])
            self.host.play_duration=self.host.player.play(path,start=start,end=rows[-1]['end_seconds'])
            self.host.segment_end=rows[-1]['end_seconds'];self.host.segment_label='输入旋律试听'
            self.host.load_waveform_path(path)
            self.host.playing_path='source:'+str(path);self.host.update_playback();self.sync_source_player()
        self.host.job('准备旋律试听…',lambda:block_audition.render_source(source,bpm,self.host.progress_message),done)

    def source_is_playing(self):
        ids=self.sources.selection();audio=self.source_audio
        return bool(audio and ids and audio['id']==ids[0] and audio['bpm']==self.project['bpm'] and self.host.playing_path=='source:'+str(audio['path']))

    def toggle_source_play(self):
        if self.source_is_playing():
            _,mode=self.host.player.status()
            if mode=='paused':self.host.player.resume()
            else:self.host.player.pause()
            self.sync_source_player()
        else:self.start_source_audio()

    def sync_source_player(self):
        audio=self.source_audio
        mode=self.host.player.status()[1] if audio and self.host.playing_path=='source:'+str(audio['path']) else 'stopped'
        for sid,button in getattr(self,'card_play_buttons',{}).items():
            text='Ⅱ' if audio and sid==audio['id'] and mode=='playing' else '▶'
            button.configure(text=text)
        selected=self.sources.selection()
        for index,button in getattr(self,'block_play_buttons',{}).items():
            active=selected and getattr(self,'source_block_playing',None)==(selected[0],index) and audio and audio['id']==selected[0]
            button.configure(text=('▶' if mode=='paused' else 'Ⅱ') if active and mode in ('playing','paused') else '▶')
        if self.source_seek:return
        if self.source_is_playing():
            pos,mode=self.host.player.status();duration=self.source_audio['rows'][-1]['end_seconds']
            self.source_slider['value']=min(100,pos/duration*100)
            self.source_time.set(f'{pos:.1f} / {duration:.1f} 秒'+(' · 已暂停' if mode=='paused' else ''))
            self.source_play_button.configure(text='▶ 继续' if mode=='paused' else 'Ⅱ 暂停')
        else:
            self.source_play_button.configure(text='▶ 播放')
            if not self.host.busy:
                ids=self.sources.selection();audio=self.source_audio
                if audio and ids and audio['id']==ids[0]:
                    duration=audio['rows'][-1]['end_seconds']
                    pos=min(duration,self.host.play_position) if self.host.play_blocks is audio['rows'] else 0.
                    self.source_slider['value']=100*pos/max(.001,duration)
                    self.source_time.set(f'{pos:.1f} / {duration:.1f} 秒 · 已停止')

    def source_seek_event(self,event,phase):
        self.host.safe(lambda:self.seek_source(event.x,phase));return 'break'

    def seek_source(self,x,phase):
        source=self.selected_source();duration=source['ticks']/(self.project['bpm']*480/60)
        if phase=='start':
            self.source_seek=True
            if self.source_is_playing():self.host.player.pause()
        if not self.source_seek:return
        fraction=max(0.,min(1.,(x-8)/max(1,self.source_slider.winfo_width()-16)))
        self.source_slider['value']=fraction*100;self.source_time.set(f'{duration*fraction:.1f} / {duration:.1f} 秒')
        if phase=='end':self.source_seek=False;self.start_source_audio(fraction)

    def show_source_settings(self):
        self.selected_role.set(ROLE_LABELS[self.selected_source()['role']])
        if self.source_settings.winfo_manager():self.source_settings.pack_forget()
        else:self.source_settings.pack(fill='x',before=self.block_cards,pady=4)

    def apply_source_role(self):
        sid=self.selected_source()['id'];project=self.snapshot()
        source=next(s for s in project['sources'] if s['id']==sid)
        source['role']=next(k for k,v in ROLE_LABELS.items() if v==self.selected_role.get())
        self.commit(project);self.source_settings.pack_forget()

    def drop_sources(self,paths):
        if self.host.modes.select()!=str(self):raise ValueError('请切换到快速成品后拖入旋律。')
        paths=[str(Path(p)) for p in paths]
        if not paths or any(Path(p).suffix.lower() not in ('.mid','.midi','.mmp') for p in paths):raise ValueError('请拖入 MIDI 或 MMP 旋律文件。')
        loaded=[(p,engine.music.load_source(p)) for p in paths]
        materials=[]
        for path,source in loaded:
            candidates=[(i,t) for i,t in enumerate(source.tracks) if t.notes]
            if not candidates:raise ValueError(Path(path).name+' 没有可用音符。')
            index,track=max(candidates,key=lambda item:sum(n.pitch*n.duration for n in item[1].notes)/sum(n.duration for n in item[1].notes))
            material=engine.import_source(path,index,'auto','upper')
            if len(candidates)>1:material['warnings'].append('默认选取平均音高较高的音轨：'+track.name+'；此为规则选择，不保证是主旋律。')
            materials.append(material)
        project=self.snapshot();default=emotion_input.is_default_story(project)
        if len(project['sources'])==1 and project['sources'][0].get('builtin_default'):project['sources']=[]
        empty=not project['sources'];project['sources'].extend(materials)
        if empty:
            project['bpm']=materials[0]['bpm']
            if default:project=emotion_input.default_story(project)
        self.commit(project);self.message.set(f'已自动加入 {len(materials)} 段旋律，默认取高声部。'+ '\n'.join(w for m in materials for w in m['warnings']))

    def btn(self,parent,text,command,hint=None):
        button=ttk.Button(parent,text=text,command=lambda:self.host.safe(command))
        if text in ('−','＋','‹','›'):button.configure(width=3)
        button.pack(side='left',padx=(0,5))
        if hint:Tooltip(button,hint)
        return button

    def toggle_source_details(self):
        if self.source_details.state()=='withdrawn':
            self.source_details.deiconify();self.source_details.lift()
        else:self.source_details.withdraw()

    def page_sources(self,delta):
        count=max(1,(len(self.project['sources'])+getattr(self,'source_card_columns',3)-1)//getattr(self,'source_card_columns',3))
        self.source_page=(self.source_page+delta)%count;self.draw_source_cards()

    def select_palette(self,key):
        if self.drag:self.cancel_drag()
        self.paint_emotion=None if self.paint_emotion==key else key
        self.pick_emotion(key)
        self.host.tell('拖动积木可调整顺序' if self.paint_emotion is None else LABELS[key].split('／')[0]+'涂色中 · 再次点击此颜色结束')
        self.draw()

    def refresh_source_blocks(self):
        ids=self.sources.selection()
        source=next((s for s in self.project['sources'] if ids and s['id']==ids[0]),None)
        old=self.input_blocks.selection();self.input_blocks.delete(*self.input_blocks.get_children())
        self.source_block_rows=block_audition.source_blocks(source,self.project['bpm']) if source else []
        for i,r in enumerate(self.source_block_rows):
            self.input_blocks.insert('','end',iid=str(i),text=f'第{i+1}块'+('（尾部不足4拍）' if r['end_tick']-r['start_tick']<1920 else ''),
                                     values=(f'{r["start_tick"]/480:g}–{r["end_tick"]/480:g}',f'{r["start_seconds"]:.2f}–{r["end_seconds"]:.2f}',len(r['notes'])))
        if self.source_block_rows:self.input_blocks.selection_set(old[0] if old and self.input_blocks.exists(old[0]) else '0')
        self.draw_source_notes()
        self.draw_block_cards()

    def resize_block_cards(self,event):
        columns=max(1,event.width//115)
        if columns!=getattr(self,'block_card_columns',6):
            self.block_card_columns=columns;self.draw_block_cards()

    def draw_block_cards(self):
        for child in self.block_cards.winfo_children():child.destroy()
        self.block_play_buttons={};columns=getattr(self,'block_card_columns',6)
        selected=self.input_blocks.selection()
        for i,row in enumerate(getattr(self,'source_block_rows',[])):
            active=bool(selected and selected[0]==str(i));color=theme_color('#80d9b4') if active else theme_color('#354659')
            card=tk.Canvas(self.block_cards,width=107,height=77,bg=theme_color('#101721'),highlightthickness=0,cursor='hand2',takefocus=True)
            card.grid(row=i//columns,column=i%columns,padx=4,pady=4,sticky='nw')
            shape=card.create_polygon(11,2,96,2,105,2,105,11,105,66,105,75,96,75,11,75,2,75,2,66,2,11,2,2,
                                      smooth=True,splinesteps=20,fill=theme_color('#203c35') if active else theme_color('#192532'),outline=color,width=2)
            card.create_text(9,13,text=f'第 {i+1} 块',anchor='w',fill=theme_color('#ecf3f8'),font=scaled_font(('Microsoft YaHei UI',8,'bold')))
            beats=(row['end_tick']-row['start_tick'])/480
            card.create_text(98,13,text=f'{beats:g}拍',anchor='e',fill=theme_color('#9db7c8'),font=scaled_font(('Microsoft YaHei UI',7)))
            notes=row['notes'];length=row['end_tick']-row['start_tick']
            if notes:
                low=min(n['pitch'] for n in notes);high=max(n['pitch'] for n in notes)
                for n in notes:
                    x=9+89*n['start']/length;end=9+89*(n['start']+n['duration'])/length
                    y=42-16*(n['pitch']-low)/max(1,high-low)
                    card.create_rectangle(x,y,max(x+1,end-1),y+2,fill=theme_color('#eab970') if n.get('continuation') else theme_color('#86dcba'),outline='')
            else:card.create_text(53,35,text='休止',fill=theme_color('#9db7c8'),font=scaled_font(('Microsoft YaHei UI',8)))
            card.create_text(9,61,text=f'{row["start_seconds"]:.1f}–{row["end_seconds"]:.1f}s',anchor='w',fill=theme_color('#a3b8c7'),font=scaled_font(('Segoe UI',7)))
            button=ttk.Button(card,text='▶',width=2,style='Compact.TButton',command=lambda index=i:self.host.safe(lambda:self.toggle_block_card(index)))
            card.create_window(90,61,window=button,width=25,height=22);self.block_play_buttons[i]=button
            card.bind('<Button-1>',lambda event,index=i:self.host.safe(lambda:self.select_block_card(index)))
            card.bind('<Return>',lambda event,index=i:self.host.safe(lambda:self.select_block_card(index)))
            card.bind('<Enter>',lambda event,c=card,item=shape:c.itemconfigure(item,outline=theme_color('#a7edd1')))
            card.bind('<Leave>',lambda event,c=card,item=shape,border=color:c.itemconfigure(item,outline=border))

    def select_block_card(self,index):
        self.input_blocks.selection_set(str(index));self.draw_source_notes();self.draw_block_cards();self.play_source_block()

    def toggle_block_card(self,index):
        sid=self.selected_source()['id']
        if getattr(self,'source_block_playing',None)==(sid,index) and self.source_is_playing():
            self.toggle_source_play()
        else:self.select_block_card(index)

    def draw_source_notes(self):
        c=self.source_notes;c.delete('all');ids=self.input_blocks.selection()
        if not ids or not getattr(self,'source_block_rows',[]):return
        row=self.source_block_rows[int(ids[0])];notes=row['notes'];width=max(100,c.winfo_width())-20;length=row['end_tick']-row['start_tick']
        for t in range(0,length+1,480):
            x=10+width*t/length;c.create_line(x,5,x,60,fill=theme_color('#354659'));c.create_text(x,68,text=str(t//480+1),fill=theme_color('#a4b5c6'))
        if not notes:c.create_text(width/2,30,text='本块为休止',fill=theme_color('#a4b5c6'));return
        low=min(n['pitch'] for n in notes);high=max(n['pitch'] for n in notes)
        for n in notes:
            a=10+width*n['start']/length;b=10+width*(n['start']+n['duration'])/length;y=48-(n['pitch']-low)/max(1,high-low)*33
            c.create_rectangle(a,y,b,y+6,fill=theme_color('#eab970') if n['continuation'] else theme_color('#80d9b4'),outline='')

    def play_source_block(self):
        ids=self.sources.selection();blocks=self.input_blocks.selection()
        if not ids or not blocks:raise ValueError('请先选择输入旋律和它的一个块。')
        source=copy.deepcopy(next(s for s in self.project['sources'] if s['id']==ids[0]));index=int(blocks[0]);bpm=self.project['bpm']
        self.host.stop_playback()
        def done(result):
            path,rows=result
            self.source_audio=dict(id=source['id'],path=path,rows=rows,bpm=bpm)
            self.source_block_playing=(source['id'],index)
            self.host.play_segment(path,rows,index,'source:'+str(path),'输入旋律分块试听')
            self.sync_source_player()
        self.host.job('准备输入旋律试听…',lambda:block_audition.render_source(source,bpm,self.host.progress_message),done)

    def next_source_block(self):
        selected=self.input_blocks.selection();index=int(selected[0])+1 if selected else 0
        if not self.input_blocks.exists(str(index)):raise ValueError('已到输入旋律最后一块。')
        self.select_block_card(index)

    def pick_emotion(self,key):
        self.emotion.set(LABELS[key]);self.strength.set(dict(calm=25,hope=55,sad=30,suspense=50,crisis=90,resolve=85)[key])
        self.brush_changed()

    def brush_changed(self):
        if self.host.busy:return
        value=round(self.strength.get());a=b=value
        if self.trend.get()=='渐强':a=max(0,value-30)
        elif self.trend.get()=='渐弱':b=max(0,value-30)
        self.level.set(str(a));self.end_level.set(str(b))
        self.brush_text.set(self.emotion.get().split('／')[0]+' · '+str(a)+(' → '+str(b) if a!=b else '')+'%')
        for key,button in self.emotion_buttons.items():
            selected=key==self.paint_emotion
            button.configure(highlightbackground=theme_color('#ffffff') if selected else theme_color('panel'),
                             text=('✓ ' if selected else '')+LABELS[key].split('／')[0])

    def seconds_at(self,x):
        return max(0,min(self.project['duration'],(x-12)/max(1,self.timeline_width)*self.project['duration']))

    def snapshot(self):
        # Include uncommitted duration edits in save, rejecting invalid input rather than losing it.
        result=copy.deepcopy(self.project);result['duration']=float(self.duration.get());result['bpm']=float(self.bpm.get())
        result=engine.automatic_memory_project(result)
        result['continuous_intensity']=True
        result['melody_only']=self.melody_only.get()
        if (emotion_input.is_default_story(self.project) and abs(result['duration']-self.project['duration'])<1e-6
                and result['bpm']!=self.project['bpm']):
            updated=emotion_input.default_story(result)
            updated['auto_peak_memory']=result['auto_peak_memory']
            return updated
        return emotion_input.resize_duration(result,result['duration'])

    def restore(self,project):
        self.paint_emotion=None
        project=engine.automatic_memory_project(project)
        project['continuous_intensity']=True
        if not project['sources'] and not project['curve'] and not project['anchors'] and not project['overrides']:
            project=emotion_input.default_story(project);project['sources']=[default_melody.source()]
        engine.validate(project,require_source=False);self.project=engine.automatic_memory_project(emotion_input.normalize(project));self.history=[];self.planned=None
        self.melody_only.set(bool(project.get('melody_only',False)))
        self.selected_region=None
        self.duration.set(str(project['duration']));self.bpm.set(str(project['bpm']));self.refresh()
        self.brush_changed()

    def commit(self,project):
        project=engine.automatic_memory_project(emotion_input.normalize(project));self.history.append(copy.deepcopy(self.project));self.history=self.history[-30:]
        self.selected_region=None
        self.project=project;self.planned=None;self.host.dirty=True;self.refresh()
        self.duration.set(str(project['duration']));self.bpm.set(str(project['bpm']))

    def apply_settings(self):self.commit(self.snapshot())

    def resize_timeline(self,delta):
        self.commit(emotion_input.resize_blocks(self.snapshot(),delta))
        self.message.set('情绪线已%s：%.2f 秒，每块 4 拍；已有成品不变，请重新生成。'%('加长' if delta>0 else '缩短',self.project['duration']))

    def apply_default(self):self.commit(emotion_input.default_story(self.snapshot()))

    def choose(self):
        paths=filedialog.askopenfilenames(parent=self.host.root,filetypes=[('旋律 MIDI / LMMS','*.mid *.midi *.mmp')])
        if paths:self.drop_sources(paths)

    def add_source(self):
        if self.source is None:raise ValueError('请先选择文件。')
        role=next(k for k,v in ROLE_LABELS.items() if v==self.role.get())
        policy={'单旋律（冲突时报错）':'reject','同时起音取高音':'upper','同时起音取低音':'lower'}[self.policy.get()]
        material=engine.import_source(self.path,self.tracks.current(),role,policy)
        project=self.snapshot();default=emotion_input.is_default_story(project)
        if len(project['sources'])==1 and project['sources'][0].get('builtin_default'):project['sources']=[]
        project['sources'].append(material)
        if len(project['sources'])==1:
            project['bpm']=material['bpm'];self.bpm.set(str(material['bpm']))
            if default:project=emotion_input.default_story(project)
        self.commit(project);self.message.set('已加入音符快照。'+ ' '.join(material['warnings']))

    def remove_source(self):
        ids=self.sources.selection()
        if not ids:raise ValueError('请选中素材。')
        project=self.snapshot();project['sources']=[s for s in project['sources'] if s['id'] not in ids]
        for key in ('curve','anchors','overrides'):
            for value in project[key]:
                if value.get('source_id') in ids:value.pop('source_id')
        if self.source_audio and self.source_audio['id'] in ids:
            if self.host.playing_path=='source:'+str(self.source_audio['path']):self.host.stop_playback()
            self.source_audio=None
        self.source_seek=False;self.source_slider['value']=0;self.source_time.set('已移除素材')
        self.commit(project)

    def values(self):
        emotion=next(k for k,v in LABELS.items() if v==self.emotion.get())
        return dict(emotion=emotion,level=float(self.level.get())/100,end_level=float(self.end_level.get())/100,source_id=None)

    def undo(self):
        if self.drag:self.cancel_drag();return
        if not self.history:raise ValueError('没有可撤销的操作。')
        self.selected_region=None;self.project=self.history.pop();self.duration.set(str(self.project['duration']));self.bpm.set(str(self.project['bpm']));self.planned=None;self.host.dirty=True;self.refresh()
        self.melody_only.set(bool(self.project.get('melody_only',False)))

    def preview(self):
        if not self.project['sources']:
            self.preview_planner.invalidate();self.preview_status='导入旋律后显示来源';return
        self.preview_status='更新中';self.preview_planner.request(self.project)

    def accept_preview(self,planned):
        self.planned=planned;self.preview_status='';self.refresh()

    def preview_failed(self,error):
        self.planned=None;self.preview_status='暂不可用'
        self.message.set('排布未更新：'+str(error));self.draw()

    def generate(self):
        project=self.snapshot();engine.validate(project)
        self.preview_planner.invalidate()
        def done(result):
            self.project=project;self.planned,report=result;self.preview_status='';self.host.dirty=True;self.refresh();self.host.add_result(report,'快速成品')
        self.host.job('生成情绪故事…',lambda:engine.generate(project,self.host.progress_message),done)

    def select_block(self,event=None):
        ids=self.blocks.selection()
        if not self.planned or not ids:return
        self.draw()

    def refresh(self):
        old_source=self.sources.selection()
        self.sources.delete(*self.sources.get_children())
        for s in self.project['sources']:self.sources.insert('','end',iid=s['id'],text=s['name'],values=(ROLE_LABELS[s['role']],round(s['ticks']/480,2)))
        if self.project['sources']:
            self.sources.selection_set(old_source[0] if old_source and self.sources.exists(old_source[0]) else self.project['sources'][0]['id'])
        self.refresh_source_blocks()
        self.draw_source_cards()
        self.blocks.delete(*self.blocks.get_children())
        if self.planned:
            for r in self.planned['blocks']:
                origin=block_labels.labels(self.planned,r)
                self.blocks.insert('','end',iid=r['id'],text=r['name']+'\n'+origin['short'].replace('\n',' · '),values=('%.2f–%.2f'%(r['start_seconds'],r['end_seconds']),('固定 · ' if r['pinned'] else '')+r['kind'],LABELS[r['emotion']]))
            warnings=self.planned['warnings'];self.plan_warning_text='\n'.join(warnings)
            self.message.set(f'{len(warnings)} 项排布提示 · 悬停查看' if warnings else '')
            self.host.summary.configure(text='快速成品\n%d 段输入 · %d 个短块\n%.1f 秒 · %d 个自动记忆点'%(len(self.project['sources']),len(self.planned['blocks']),self.project['duration'],len(self.planned['anchors'])))
        else:
            self.plan_warning_text=''
            self.host.summary.configure(text='%d 段旋律 · %d 块 · %.1f 秒'%(len(self.project['sources']),len(emotion_input.grid_seconds(self.project))-1,self.project['duration']))
            self.preview()
        self.draw()
