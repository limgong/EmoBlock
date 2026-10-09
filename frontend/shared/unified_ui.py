from ui_scale import font as scaled_font
from ui_theme import color as theme_color
"""One-window studio: quick melody-to-piece and detailed material workflow."""
import copy
import json
import queue
import random
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
import legacy_audio as winsound
import ui_platform
from audio_player import WavePlayer
import audio_import
import studio_model as model
import local_engine
import story_ui
from ui_hints import Tooltip
from window_ui import IconButton, RoundedPanel, FixedRail, WindowChrome
from preview_ui import Navigation, PreviewAudio

flow=model.flow;structure=model.structure;materials=model.materials
ROOT=structure.ROOT
COLORS=dict(calm='#8fcddd',hope='#ebd18c',sad='#a6a6df',suspense='#c8a6df',crisis='#e99c98',resolve='#97d9ba')
BG=theme_color('#101721');CARD=theme_color('#192330');INK=theme_color('#edf2f7');MUTED=theme_color('#a4b5c6');ACCENT=theme_color('#80d9b4')

ui_platform.prepare_process()


class ScrollPage(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.footer=ttk.Frame(self,padding=(12,4,14,4));self.footer.pack(side='bottom',fill='x')
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body=ttk.Frame(self.canvas,padding=(12,10,14,14))
        self.item=self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.item,width=e.width))


def button(parent,text,command,accent=False):
    widget=ttk.Button(parent,text=text,command=command,style='Accent.TButton' if accent else 'TButton')
    widget.pack(side='left',padx=(0,7),pady=3);return widget


class CurveEditor(ttk.Frame):
    def __init__(self,parent,commit,busy):
        super().__init__(parent);self.commit=commit;self.busy=busy;self.rows=[];self.drag=None
        self.canvas=tk.Canvas(self,height=145,bg=theme_color('#0c131c'),highlightthickness=0,cursor='hand2')
        self.canvas.pack(fill='x',pady=(4,10));self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        row=ttk.Frame(self);row.pack(fill='x',pady=3)
        ttk.Label(row,text='从').pack(side='left')
        self.first=ttk.Combobox(row,state='readonly',width=16);self.first.pack(side='left',padx=5)
        ttk.Label(row,text='到').pack(side='left')
        self.last=ttk.Combobox(row,state='readonly',width=16);self.last.pack(side='left',padx=5)
        self.emotion=ttk.Combobox(row,state='readonly',values=list(flow.music.EMOTIONS.values()),width=15)
        self.emotion.current(0);self.emotion.pack(side='left',padx=5)
        self.first.bind('<<ComboboxSelected>>',lambda e:self.pick(self.first.current()))
        row=ttk.Frame(self);row.pack(fill='x',pady=3)
        self.start=tk.StringVar(value='30');self.end=tk.StringVar(value='60')
        for label,var in [('起始强度',self.start),('结束强度',self.end)]:
            ttk.Label(row,text=label).pack(side='left',padx=(0,5))
            ttk.Entry(row,textvariable=var,width=5).pack(side='left');ttk.Label(row,text='%').pack(side='left',padx=(2,12))
        button(row,'应用到区间',self.apply,True)
        ttk.Label(self,text='拖动圆点调整强度；点击色块选段。颜色表示情绪，折线表示目标强度。',style='Muted.TLabel').pack(anchor='w',pady=5)

    def set_rows(self,rows):
        self.rows=copy.deepcopy(rows)
        selected=self.first.current()
        names=[f'{i+1} · {r["name"]}' for i,r in enumerate(rows)]
        self.first.configure(values=names);self.last.configure(values=names)
        if rows:self.pick(max(0,min(selected,len(rows)-1)))
        self.draw()

    def pick(self,index):
        if not 0<=index<len(self.rows):return
        self.first.current(index);self.last.current(index);r=self.rows[index]
        self.emotion.set(flow.music.EMOTIONS[r['emotion']]);self.start.set(str(round(r['start']*100)));self.end.set(str(round(r['end']*100)))
        self.draw()

    def points(self):
        total=sum(r['bars'] for r in self.rows) or 1;cursor=0;width=max(300,self.canvas.winfo_width())
        for i,r in enumerate(self.rows):
            x=38+(width-58)*cursor/total;cursor+=r['bars'];end=38+(width-58)*cursor/total
            yield i,x,end,117-r['start']*75,117-r['end']*75

    def draw(self):
        c=self.canvas;c.delete('all');self.handles=[]
        for v in (0,.5,1):
            y=117-v*75;c.create_line(38,y,max(300,c.winfo_width())-20,y,fill=theme_color('#253345'));c.create_text(18,y,text=str(round(v*100)),fill=MUTED,font=scaled_font(('Segoe UI',9)))
        prev=None
        for i,x,end,y1,y2 in self.points():
            row=self.rows[i];color=COLORS[row['emotion']]
            c.create_rectangle(x,9,end-2,29,fill=color,outline='')
            c.create_text((x+end)/2,19,text=row['name'],fill=BG,font=scaled_font(('Microsoft YaHei UI',9)))
            if prev is not None:c.create_line(x,prev,x,y1,fill=MUTED,dash=(3,3))
            c.create_line(x,y1,end,y2,fill=color,width=3)
            settings=row.get('bar_settings')
            if row.get('beat_nodes'):
                c.create_rectangle(x,32,end,124,fill=theme_color('#0c131c'),outline='')
                nodes=row['beat_nodes']
                for a,b in zip(nodes,nodes[1:]):
                    left=x+(end-x)*a['beat']/(row['bars']*4);right=x+(end-x)*b['beat']/(row['bars']*4)
                    shade=COLORS[a['emotion']]
                    c.create_rectangle(left,32,right,38,fill=shade,outline='')
                    c.create_line(left,117-a['intensity']*75,right,117-b['intensity']*75,fill=shade,width=3)
            if settings:
                c.create_rectangle(x,32,end,124,fill=theme_color('#0c131c'),outline='')
                for j,value in enumerate(settings):
                    a=x+(end-x)*j/len(settings);b=x+(end-x)*(j+1)/len(settings);shade=COLORS[value['emotion']]
                    c.create_rectangle(a,32,b,38,fill=shade,outline='')
                    c.create_line(a,117-value['start']*75,b,117-value['end']*75,fill=shade,width=3)
            for side,px,py in [('start',x,y1),('end',end,y2)]:
                c.create_oval(px-5,py-5,px+5,py+5,fill=color,outline=BG,width=2);self.handles.append((i,side,px,py))
            if i==self.first.current():c.create_line(x,134,end,134,fill=ACCENT,width=2)
            prev=y2

    def press(self,event):
        if self.busy() or not self.rows:return
        handle=min(self.handles,key=lambda h:(event.x-h[2])**2+(event.y-h[3])**2)
        if (event.x-handle[2])**2+(event.y-handle[3])**2<225:
            self.pick(handle[0]);self.drag=(handle[0],handle[1]);return
        for i,x,end,_,_ in self.points():
            if x<=event.x<=end:self.pick(i);break

    def motion(self,event):
        if self.drag and not self.busy():
            i,side=self.drag;self.rows[i][side]=max(0,min(1,(117-event.y)/75))
            self.start.set(str(round(self.rows[i]['start']*100)));self.end.set(str(round(self.rows[i]['end']*100)));self.draw()

    def release(self,event):
        if self.drag:
            self.drag=None;self.apply()

    def apply(self):
        if not self.busy():self.commit(self.first.current(),self.last.current(),self.emotion.get(),self.start.get(),self.end.get())


class UnifiedApp(PreviewAudio):
    def __init__(self,root):
        import ui_theme
        import ui_scale
        ui_scale.factor=1.
        global BG,CARD,INK,MUTED,ACCENT
        ui_theme.current='light'
        BG=theme_color('bg');CARD=theme_color('panel');INK=theme_color('ink');MUTED=theme_color('muted');ACCENT=theme_color('accent')
        self.root=root;self.pool=materials.new_pool();self.doc=None;self.results=[];self.source=None;self.source_path=None
        self.busy=False;self.dirty=False;self.undo_stack=[];self.messages=queue.Queue();self.disabled=[];self.preview_cache={}
        self.input_themes=[];self.player=WavePlayer();self.playing_path=None;self.play_blocks=[];self.play_duration=0.;self.play_position=0.
        self.curve=[dict(emotion='calm',start=.2,end=.4),dict(emotion='suspense',start=.4,end=.55),dict(emotion='crisis',start=.55,end=.9),dict(emotion='resolve',start=.7,end=.95)]
        root.title('EmoBlocks · 音乐积木工作室')
        ui_platform.configure_scaling(root)
        root.geometry(f'{min(1360,root.winfo_screenwidth()-70)}x{min(950,root.winfo_screenheight()-90)}+30+30');root.minsize(1020,700);root.configure(bg=BG)
        self.style()
        import ui_theme
        ui_theme.apply(root,'light')
        self.track_var=tk.StringVar();self.start_bar=tk.StringVar(value='1');self.bars=tk.StringVar(value='8');self.name=tk.StringVar(value='A')
        self.policy=tk.StringVar(value='遇到同时起音时停止');self.trim=tk.BooleanVar(value=True);self.key=tk.StringVar(value='自动 / 沿用素材池')
        self.source_text=tk.StringVar(value='尚未载入旋律 · 支持音频 / MIDI / MMP，单段 4–8 小节')
        self.track_boxes=[];self.count=tk.StringVar(value='4');self.connections=tk.BooleanVar(value=True);self.seed=tk.StringVar(value='31')
        outer=ttk.Frame(root,padding=(14,8,14,8));outer.pack(fill='both',expand=True)
        header=ttk.Frame(outer);header.pack(fill='x',pady=(0,8))
        self.logo=IconButton(header,'blocks',lambda:None,size=38)
        self.logo.pack(side='left',padx=(0,8))
        brand=ttk.Label(header,text='EmoBlocks',font=scaled_font(('Segoe UI',16,'bold')),foreground=INK);brand.pack(side='left')
        caption=ttk.Label(header,text='  音乐积木工作室',style='Muted.TLabel');caption.pack(side='left',padx=10)
        self.chrome=WindowChrome(root,header,self.close)
        self.chrome.bind_drag(brand);self.chrome.bind_drag(self.logo);self.chrome.bind_drag(caption)
        right=ttk.Frame(header);right.pack(side='right',padx=(0,12))
        self.theme_choice=tk.StringVar(value='B · 浅色')
        self.theme_button=IconButton(right,'moon',lambda:self.set_theme('dark' if ui_theme.current=='light' else 'light'),
                                     lambda _: '切换为深色模式' if ui_theme.current=='light' else '切换为浅色模式')
        self.theme_button.pack(side='left',padx=(0,8))
        button(right,'＋ 新建',lambda:self.safe(self.new_project)).configure(style='Quiet.TButton')
        button(right,'▱ 打开',lambda:self.safe(self.open_project)).configure(style='Quiet.TButton')
        button(right,'保存',lambda:self.safe(self.save_project))
        workspace=ttk.Frame(outer);workspace.pack(fill='both',expand=True)
        workspace.columnconfigure(0,weight=1);workspace.columnconfigure(1,minsize=300);workspace.rowconfigure(0,weight=1)
        main=ttk.Frame(workspace);main.grid(row=0,column=0,sticky='nsew',padx=(0,12))
        self.rail_page=FixedRail(workspace);self.rail_page.grid(row=0,column=1,sticky='nsew',pady=(44,0))
        rail=self.rail_page.body
        self.modes=ttk.Notebook(main,style='Workspace.TNotebook')
        self.navigation=Navigation(main,self.modes);self.navigation.pack(fill='x')
        self.modes.pack(fill='both',expand=True)
        quick=ScrollPage(self.modes);detail=ttk.Frame(self.modes)
        self.modes.add(quick,text='  快速成品  ');self.modes.add(detail,text='  精细创作  ')
        self.quick_page=quick
        body=quick.body
        self.heading(body,'旋律 + 情绪线 → 一段完整作品','自动发展关联素材、编配与衔接。结果可直接进入精细模式继续修改。')
        self.source_controls(body,compact=True)
        self.build_inputs(body)
        card=self.card(body,'02  设计情绪发展')
        row=ttk.Frame(card);row.pack(fill='x',pady=3)
        ttk.Label(row,text='段数').pack(side='left',padx=(0,5))
        segments=ttk.Combobox(row,textvariable=self.count,values=['1','2','3','4','5','6'],state='readonly',width=5);segments.pack(side='left',padx=(0,10));segments.bind('<<ComboboxSelected>>',lambda e:self.safe(self.resize_curve))
        ttk.Label(row,text='生成种子').pack(side='left');ttk.Entry(row,textvariable=self.seed,width=8).pack(side='left',padx=6)
        button(row,'换一组候选',lambda:self.seed.set(str(random.randint(1,999999))))
        self.duration=tk.StringVar();ttk.Label(card,textvariable=self.duration,style='Muted.TLabel').pack(anchor='w')
        self.quick_curve=CurveEditor(card,lambda *args:self.safe(lambda:self.apply_curve(False,*args)),lambda:self.busy);self.quick_curve.pack(fill='x')
        row=ttk.Frame(quick.footer);row.pack(fill='x',pady=3)
        self.quick_generate_button=button(row,'一键生成成品',lambda:self.safe(self.quick_generate),True)
        button(row,'转到精细调整 →',lambda:self.modes.select(1))
        self.quick_note=ttk.Label(quick.footer,text='自动展开原主题与关联回答句，原文件不覆盖。',style='Muted.TLabel',wraplength=720)
        self.quick_note.pack(anchor='w',pady=2)
        self.detail_tabs=ttk.Notebook(detail);self.detail_tabs.pack(fill='both',expand=True,pady=(8,0))
        pages=[]
        for title in ('① 素材','② 结构','③ 情绪与连接'):
            page=ScrollPage(self.detail_tabs);pages.append(page);self.detail_tabs.add(page,text=title)
        self.build_materials(pages[0].body);self.build_structure(pages[1].body);self.build_emotion(pages[2].body)
        self.detail_pages=pages
        ttk.Label(rail,text='试听',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(anchor='w')
        self.summary=ttk.Label(rail,text='尚无结构\n先导入旋律或打开工程。',wraplength=235,justify='left')
        self.result_list=tk.Listbox(rail,height=3,bg=CARD,fg=INK,selectbackground=theme_color('#355b60'),relief='flat',highlightthickness=0,font=scaled_font(('Microsoft YaHei UI',10)),width=27,exportselection=False)
        self.result_list.bind('<<ListboxSelect>>',lambda e:self.show_result())
        self.play_label=ttk.Label(rail,text='尚未播放',wraplength=245)
        self.seek_drag=None;self.transport_running=False
        self.play_progress=ttk.Scale(rail,from_=0,to=100,orient='horizontal')
        self.result_block=ttk.Combobox(rail,state='readonly',width=26)
        self.build_preview_audio(rail)
        ttk.Label(self.rail_page.footer,text='导出成品',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(anchor='w',pady=(0,4))
        ttk.Label(self.rail_page.footer,text='当前试听版本',style='Muted.TLabel').pack(anchor='w',pady=(0,5))
        row=ttk.Frame(self.rail_page.footer);row.pack(fill='x')
        for i,(ext,label) in enumerate([('wav','WAV'),('mid','MIDI'),('mmp','MMP')]):
            row.columnconfigure(i,weight=1,uniform='exports')
            ttk.Button(row,text=label,width=1,command=lambda kind=ext:self.safe(lambda:self.export_result(kind))).grid(row=0,column=i,sticky='ew',padx=(0,5 if i<2 else 0))
        self.result_info=tk.Text(rail,height=2,width=27,bg=CARD,fg=MUTED,relief='flat',wrap='word',font=scaled_font(('Microsoft YaHei UI',10)))
        Tooltip(self.play_label,lambda _:self.result_info.get('1.0','end').strip())
        rail.bind('<Configure>',lambda e:[label.configure(wraplength=max(150,e.width-12)) for label in (self.summary,self.play_label)],add='+')
        self.set_info('生成后可试听与导出。')
        Tooltip(self.result_list,lambda _:self.summary.cget('text')+'\n选择一个历史版本试听；后续编辑不会改变已生成的音频。')
        Tooltip(self.result_block,'选择成品中的一个四拍块，即可试听。')
        self.progress=ttk.Progressbar(outer,mode='indeterminate')
        statusbar=ttk.Frame(outer);statusbar.pack(side='bottom',fill='x',before=workspace,pady=(8,0))
        ttk.Label(statusbar,text='●',foreground=ACCENT).pack(side='left',padx=(0,6))
        self.notice=ttk.Label(statusbar,text='就绪',wraplength=750,style='Muted.TLabel');self.notice.pack(side='left')
        self.status_duration=ttk.Label(statusbar,text='',style='Muted.TLabel');self.status_duration.pack(side='right')
        self.progress.configure(style='Slim.Horizontal.TProgressbar')
        self.timer=root.after(100,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)
        self.bars.trace_add('write',lambda *args:self.refresh_quick())
        for var in (self.connections,self.seed,self.start_bar,self.bars,self.policy,self.trim,self.key,self.track_var):
            var.trace_add('write',lambda *args:setattr(self,'dirty',True))
        self.refresh()
        self.story_page=story_ui.StoryPage(self.modes,self)
        # Keep legacy widgets alive for saved-project/detail-editor compatibility,
        # but replace their public tab with the current story workflow.
        self.modes.forget(self.quick_page)
        self.modes.insert(0,self.story_page,text='  快速成品  ')
        self.modes.select(self.story_page)
        root.bind_all('<MouseWheel>',self.wheel,add='+')
        ui_platform.setup_window(root,self)
        root.after_idle(self.refresh_surfaces)
        from ui_scale import ResponsiveLayout
        self.responsive=ResponsiveLayout(self,workspace)

    def set_theme(self,name):
        import ui_theme
        global BG,CARD,INK,MUTED,ACCENT
        ui_theme.apply(self.root,name)
        BG=theme_color('bg');CARD=theme_color('panel');INK=theme_color('ink');MUTED=theme_color('muted');ACCENT=theme_color('accent')
        self.theme_choice.set('B · 浅色' if name=='light' else 'A · 深色')
        self.theme_button.icon='moon' if name=='light' else 'sun'
        self.refresh_surfaces()
        if hasattr(self,'story_page'):
            page=self.story_page
            page.draw_source_cards();page.draw_block_cards();page.draw_source_notes();page.brush_changed();page.draw()
            page.refresh_composer()
            for button in page.emotion_buttons.values():
                button.configure(foreground=theme_color('ink'),activeforeground=theme_color('ink'),background=theme_color('panel'),activebackground=theme_color('hover'))

    def refresh_surfaces(self):
        def walk(widget):
            if isinstance(widget,(RoundedPanel,IconButton,Navigation)):widget.refresh_theme()
            for child in widget.winfo_children():walk(child)
        walk(self.root)
        self.draw_history();self.draw_playback()

    def style(self):
        s=ttk.Style(self.root);s.theme_use('clam')
        s.configure('.',font=scaled_font(('Microsoft YaHei UI',10)),background=BG,foreground=INK)
        s.configure('TFrame',background=BG);s.configure('TLabel',background=BG)
        s.configure('Muted.TLabel',foreground=MUTED)
        s.configure('TLabelframe',background=BG,bordercolor=theme_color('#334457'));s.configure('TLabelframe.Label',foreground=ACCENT)
        s.configure('TButton',padding=(10,7),background=theme_color('#273648'),borderwidth=0)
        s.map('TButton',background=[('active',theme_color('#3b5268'))],foreground=[('disabled',theme_color('#718293'))])
        s.configure('Accent.TButton',background=theme_color('#25644f'),foreground=theme_color('#eefff7'))
        s.configure('TNotebook',background=BG,borderwidth=0);s.configure('TNotebook.Tab',padding=(14,10),background=CARD)
        s.map('TNotebook.Tab',background=[('selected',theme_color('#294438'))],foreground=[('selected',ACCENT)])
        s.configure('Treeview',background=CARD,fieldbackground=CARD,foreground=INK,rowheight=29)
        s.configure('Treeview.Heading',background=theme_color('#243344'),font=scaled_font(('Microsoft YaHei UI',10,'bold')))
        s.configure('TCombobox',fieldbackground=theme_color('#edf2f7'),foreground=theme_color('#192330'),padding=4)
        s.map('TCombobox',fieldbackground=[('readonly',theme_color('#edf2f7'))],foreground=[('readonly',theme_color('#192330'))])
        import card_style
        card_style.install(self.root,s)

    def heading(self,parent,title,subtitle):
        ttk.Label(parent,text=title,font=scaled_font(('Microsoft YaHei UI',16,'bold'))).pack(anchor='w',pady=(2,5))
        if subtitle:ttk.Label(parent,text=subtitle,style='Muted.TLabel',wraplength=730).pack(anchor='w',pady=(0,10))

    def card(self,parent,title):
        box=ttk.LabelFrame(parent,text=title,padding=12);box.pack(fill='x',pady=(0,12));return box

    def source_controls(self,parent,compact=False):
        card=self.card(parent,'01  参考旋律')
        from runtime_config import ASSETS
        row=ttk.Frame(card);row.pack(fill='x');button(row,'导入音频 → MIDI',lambda:self.safe(self.browse_audio_source));button(row,'导入 MIDI / MMP',lambda:self.safe(self.browse_source));button(row,'使用你的平静版',lambda:self.safe(lambda:self.load_source(ASSETS/'EmoBlocks-Calm.mmp')))
        ttk.Label(card,textvariable=self.source_text,wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=7)
        advanced=ttk.Frame(card)
        if compact:
            def toggle():
                if self.busy:return
                if advanced.winfo_manager():advanced.pack_forget()
                else:advanced.pack(fill='x',pady=3)
            row=ttk.Frame(card);row.pack(fill='x')
            button(row,'输入选项：旋律轨、小节范围、同时起音、调性 ▾',toggle)
        else:advanced.pack(fill='x')
        row=ttk.Frame(advanced);row.pack(fill='x',pady=3)
        box=ttk.Combobox(row,textvariable=self.track_var,state='readonly',width=27);box.pack(side='left',padx=(0,8));self.track_boxes.append(box)
        for title,var in [('起始小节',self.start_bar),('长度 4–8',self.bars)]:
            ttk.Label(row,text=title).pack(side='left',padx=4);ttk.Entry(row,textvariable=var,width=4).pack(side='left',padx=4)
        row=ttk.Frame(advanced);row.pack(fill='x',pady=4)
        ttk.Label(row,text='同时起音').pack(side='left',padx=(0,5))
        ttk.Combobox(row,textvariable=self.policy,state='readonly',values=['遇到同时起音时停止','保留低音（明确简化）','保留高音（明确简化）'],width=25).pack(side='left',padx=(0,10))
        ttk.Checkbutton(row,text='截短重叠尾音',variable=self.trim).pack(side='left')
        row=ttk.Frame(advanced);row.pack(fill='x',pady=4)
        ttk.Label(row,text='调性参考').pack(side='left',padx=(0,5))
        ttk.Combobox(row,textvariable=self.key,state='readonly',values=['自动 / 沿用素材池']+[f'{n} {mode}' for n in flow.music.NAMES for mode in ('major','minor')],width=25).pack(side='left')
        ttk.Label(advanced,text='多声部不会自动猜主旋律。对原文件只读，简化记录随工程保存。',style='Muted.TLabel').pack(anchor='w',pady=(5,0))

    def build_materials(self,parent):
        self.heading(parent,'素材池','导入主题，发展变体或回答句，再选择保留。')
        self.source_controls(parent)
        row=ttk.Frame(parent);row.pack(fill='x')
        ttk.Label(row,text='主题名称').pack(side='left');ttk.Entry(row,textvariable=self.name,width=10).pack(side='left',padx=6)
        button(row,'加入主题',lambda:self.safe(self.add_theme),True)
        self.library=ttk.Treeview(parent,columns=('kind','state'),show='tree headings',height=6,selectmode='browse')
        for col,label,w in [('#0','素材',240),('kind','类型',160),('state','选择状态',140)]:self.library.heading(col,text=label);self.library.column(col,width=w)
        self.library.pack(fill='x',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x')
        for text,fn in [('生成变体',lambda:self.candidates('variant')),('生成回答句',lambda:self.candidates('answer')),('保留候选',self.accept),('试听素材',self.preview_material)]:button(row,text,lambda action=fn:self.safe(action))
        self.material_note=ttk.Label(parent,text='选择素材后可查看来源。',wraplength=700,style='Muted.TLabel');self.material_note.pack(anchor='w',pady=8)
        self.library.bind('<<TreeviewSelect>>',lambda e:self.describe_material())

    def build_inputs(self,parent):
        box=self.card(parent,'多段输入（可选）')
        ttk.Label(box,text='逐段导入或选择同一文件的小节范围，加入列表。生成时使用全部主题，保持列表顺序。',style='Muted.TLabel',wraplength=700).pack(anchor='w')
        self.input_list=tk.Listbox(box,height=3,bg=CARD,fg=INK,selectbackground=theme_color('#355b60'),relief='flat',exportselection=False,font=scaled_font(('Microsoft YaHei UI',10)))
        self.input_list.pack(fill='x',pady=5)
        row=ttk.Frame(box);row.pack(fill='x')
        button(row,'将当前选区加入列表',lambda:self.safe(self.add_input))
        button(row,'↑',lambda:self.safe(lambda:self.move_input(-1)));button(row,'↓',lambda:self.safe(lambda:self.move_input(1)))
        button(row,'移除选中',lambda:self.safe(self.remove_input))
        self.input_hint=ttk.Label(box,text='列表为空：使用一段旋律，自动发展关联素材。',style='Muted.TLabel',wraplength=700);self.input_hint.pack(anchor='w',pady=3)

    def add_input(self):
        if len(self.input_themes)>=6:raise ValueError('快速多旋律输入最多 6 段；更多主题可使用精细模式。')
        used={t['name'] for t in self.input_themes};name=next(chr(n) for n in range(65,91) if chr(n) not in used)
        theme=self.import_reference(name,reference_key=(self.input_themes[0]['tonic'],self.input_themes[0]['mode']) if self.input_themes else None)
        check=materials.new_pool()
        for item in self.input_themes+[theme]:materials.add_item(check,item)
        self.input_themes.append(theme);self.update_input_curve();self.dirty=True
        self.tell('已加入 '+name+'。可换文件或更改小节范围，再加入下一段；最后按列表顺序生成。')

    def update_input_curve(self):
        if self.input_themes:
            n=len(self.input_themes)
            while len(self.curve)<n:self.curve.append(dict(emotion='calm',start=.35,end=.55))
            self.curve=self.curve[:n];self.count.set(str(n))
        self.refresh_inputs();self.refresh_quick()

    def refresh_inputs(self):
        self.input_list.delete(0,'end')
        for i,t in enumerate(self.input_themes):
            src=t.get('source',{});self.input_list.insert('end',f'{i+1}. {t["name"]} · {t["bars"]} 小节 · {Path(src.get("path","")).name} · 起始 {src.get("start_bar",1)}')
        self.input_hint.configure(text=f'多旋律模式：{len(self.input_themes)} 个主题按列表顺序使用，不自动补段或重排。' if self.input_themes else '列表为空：使用一段旋律，自动发展关联素材。')
        if hasattr(self,'quick_generate_button'):self.quick_generate_button.configure(text='按输入顺序生成成品' if self.input_themes else '一键生成成品')
        if hasattr(self,'quick_note'):self.quick_note.configure(text='按输入主题顺序编配与连接，不自动增加回答句；原文件不覆盖。' if self.input_themes else '自动展开原主题与关联回答句，原文件不覆盖。')

    def move_input(self,delta):
        selection=self.input_list.curselection()
        if not selection:return
        i=selection[0];j=i+delta
        if 0<=j<len(self.input_themes):
            self.input_themes[i],self.input_themes[j]=self.input_themes[j],self.input_themes[i]
            self.dirty=True;self.refresh_inputs();self.refresh_quick();self.input_list.selection_set(j)
            self.tell('输入顺序已调整；情绪按位置保留，请检查后再生成。')

    def remove_input(self):
        selection=self.input_list.curselection()
        if selection:self.input_themes.pop(selection[0]);self.dirty=True;self.update_input_curve()

    def build_structure(self,parent):
        self.heading(parent,'固定主题骨架','确认前检查顺序，确认后只允许原位替换和指定位置的插入。')
        self.draft=tk.Listbox(parent,height=5,exportselection=False,bg=CARD,fg=INK,selectbackground=theme_color('#355b60'),relief='flat',font=scaled_font(('Microsoft YaHei UI',11)));self.draft.pack(fill='x',pady=6)
        row=ttk.Frame(parent);row.pack(fill='x')
        button(row,'上移',lambda:self.safe(lambda:self.move_theme(-1)));button(row,'下移',lambda:self.safe(lambda:self.move_theme(1)));button(row,'确认固定顺序',lambda:self.safe(self.confirm_structure),True)
        self.route=ttk.Treeview(parent,columns=('role','bars'),show='tree headings',height=5,selectmode='browse')
        for col,label,w in [('#0','当前展开',270),('role','段落功能',180),('bars','小节',120)]:self.route.heading(col,text=label);self.route.column(col,width=w)
        self.route.pack(fill='x',pady=10)
        row=ttk.Frame(parent);row.pack(fill='x')
        self.slot=ttk.Combobox(row,state='readonly',width=23);self.slot.pack(side='left',padx=(0,7));self.slot.bind('<<ComboboxSelected>>',lambda e:self.structure_choices())
        self.role=ttk.Combobox(row,state='readonly',values=structure.ROLES,width=12);self.role.current(0);self.role.pack(side='left',padx=5)
        button(row,'设置角色',lambda:self.safe(lambda:self.edit_structure('role',slot_id=self.sid(),role=self.role.get())))
        row=ttk.Frame(parent);row.pack(fill='x',pady=6)
        self.replacement=ttk.Combobox(row,state='readonly',width=34);self.replacement.pack(side='left',padx=(0,7))
        button(row,'原位替换 / 还原',lambda:self.safe(self.replace))
        row=ttk.Frame(parent);row.pack(fill='x',pady=6)
        self.answer=ttk.Combobox(row,state='readonly',width=34);self.answer.pack(side='left',padx=(0,7))
        button(row,'插入此段之后',lambda:self.safe(self.insert));button(row,'授权此位置',lambda:self.safe(self.authorize))
        row=ttk.Frame(parent);row.pack(fill='x')
        button(row,'移除选中插入项',lambda:self.safe(self.remove_insert));button(row,'撤销上一步',lambda:self.safe(self.undo))
        row=ttk.Frame(parent);row.pack(fill='x',pady=6)
        ttk.Label(row,text='独立过门').pack(side='left')
        self.transition_bars=tk.StringVar(value='1')
        ttk.Combobox(row,textvariable=self.transition_bars,values=['1','2'],state='readonly',width=3).pack(side='left',padx=5)
        ttk.Label(row,text='小节').pack(side='left',padx=5)
        button(row,'在选中块后生成',lambda:self.safe(self.add_transition),True)
        button(row,'移除选中过门',lambda:self.safe(self.remove_transition))
        ttk.Label(parent,text='在上方“当前展开”选中前一块。过门新增时长，后续顺延；生成整曲后可试听并定位过门。',wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=4)
        ttk.Label(parent,text='原主题默认不可省略或重复。授权插入只表达你的结构选择，不代表音乐相容性已验证。',wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=8)

    def build_emotion(self,parent):
        self.heading(parent,'情绪线与连接','一个情绪区间可以覆盖多个内容块；顺序与主题音符保持。')
        self.detail_curve=CurveEditor(parent,lambda *args:self.safe(lambda:self.apply_curve(True,*args)),lambda:self.busy);self.detail_curve.pack(fill='x',pady=10)
        ttk.Checkbutton(parent,text='开启连接：低音导向、共同音延留、节奏交接',variable=self.connections).pack(anchor='w',pady=10)
        row=ttk.Frame(parent);row.pack(fill='x');button(row,'生成连续作品',lambda:self.safe(self.detail_generate),True);button(row,'撤销上一步',lambda:self.safe(self.undo))
        ttk.Label(parent,text='上方按钮完整重编。只改情绪并保留其他编配，请先在右侧选择基准结果，再使用下面的局部流程。',wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x')
        button(row,'① 预览局部影响',lambda:self.safe(self.preview_local))
        button(row,'② 生成局部修改',lambda:self.safe(self.generate_local),True)
        button(row,'撤回局部结果',lambda:self.safe(self.revert_local))
        self.local_preview=None
        self.local_info=ttk.Label(parent,text='先应用情绪修改，再预览；以右侧选中的成品为保留基准。',wraplength=700,style='Muted.TLabel')
        self.local_info.pack(anchor='w',pady=10)
        ttk.Label(parent,text='块内情绪：按小节设置（不拆块、不增加时长）',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(anchor='w',pady=(12,5))
        row=ttk.Frame(parent);row.pack(fill='x')
        self.inner_block=ttk.Combobox(row,state='readonly',width=24);self.inner_block.pack(side='left',padx=4)
        self.inner_block.bind('<<ComboboxSelected>>',lambda e:self.refresh_inner())
        self.inner_first=ttk.Combobox(row,state='readonly',width=4);self.inner_last=ttk.Combobox(row,state='readonly',width=4)
        ttk.Label(row,text='第').pack(side='left');self.inner_first.pack(side='left');ttk.Label(row,text='至').pack(side='left');self.inner_last.pack(side='left');ttk.Label(row,text='小节').pack(side='left')
        row=ttk.Frame(parent);row.pack(fill='x',pady=4)
        self.inner_emotion=ttk.Combobox(row,state='readonly',values=list(flow.music.EMOTIONS.values()),width=15);self.inner_emotion.current(0);self.inner_emotion.pack(side='left')
        self.inner_start=tk.StringVar(value='30');self.inner_end=tk.StringVar(value='70')
        for label,var in [('起始 %',self.inner_start),('结束 %',self.inner_end)]:
            ttk.Label(row,text=label).pack(side='left',padx=5);ttk.Entry(row,textvariable=var,width=5).pack(side='left')
        button(row,'应用块内变化',lambda:self.safe(self.apply_inner),True)
        self.inner_info=ttk.Label(parent,text='',wraplength=700,style='Muted.TLabel');self.inner_info.pack(anchor='w',pady=5)
        ttk.Label(parent,text='更细的情绪线：拍级节点（使用上方选择的块）',font=scaled_font(('Microsoft YaHei UI',11,'bold'))).pack(anchor='w',pady=(12,4))
        self.beat_canvas=tk.Canvas(parent,height=130,bg=theme_color('#0c131c'),highlightthickness=0)
        self.beat_canvas.pack(fill='x');self.beat_canvas.bind('<Configure>',lambda e:self.refresh_beats())
        self.beat_canvas.bind('<Button-1>',self.pick_beat_point)
        row=ttk.Frame(parent);row.pack(fill='x',pady=4)
        ttk.Label(row,text='块内第几拍').pack(side='left');self.beat_position=ttk.Combobox(row,width=5,state='readonly');self.beat_position.pack(side='left',padx=5)
        self.beat_emotion=ttk.Combobox(row,values=list(flow.music.EMOTIONS.values()),state='readonly',width=15);self.beat_emotion.current(0);self.beat_emotion.pack(side='left')
        self.beat_level=tk.StringVar(value='50');ttk.Entry(row,textvariable=self.beat_level,width=5).pack(side='left',padx=5)
        ttk.Label(row,text='%').pack(side='left')
        button(row,'添加 / 更新节点',lambda:self.safe(self.apply_beat),True)
        button(row,'删除节点',lambda:self.safe(lambda:self.apply_beat(True)))
        self.beat_info=ttk.Label(parent,text='',wraplength=700,style='Muted.TLabel');self.beat_info.pack(anchor='w',pady=4)
        ttk.Label(parent,text='点图选拍与强度，再点击添加。强度线性插值，情绪从节点起切换。最后一拍之后的编号是终点，只控制收尾强度。小节细分与拍级节点互斥，切换前需整块应用重置（可撤销）。',wraplength=700,style='Muted.TLabel').pack(anchor='w')
        ttk.Label(parent,text='可重复设置多个小节区间。上方整块应用或拖动会覆盖所选块的细分设置；局部生成仍按整块及必要边界计算影响。',wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=5)

    def safe(self,fn):
        if self.busy:return
        try:return fn()
        except Exception as exc:self.tell(str(exc),True)

    def tell(self,text,error=False):self.notice.configure(text=text,foreground=theme_color('#f4a59d') if error else ACCENT)

    def set_info(self,text):
        self.result_info.configure(state='normal');self.result_info.delete('1.0','end');self.result_info.insert('1.0',text);self.result_info.configure(state='disabled')

    def wheel(self,event):
        widget=self.root.winfo_containing(event.x_root,event.y_root)
        while widget:
            # Lists and text areas already handle their own wheel events.
            if isinstance(widget,(tk.Text,tk.Listbox,ttk.Treeview,ttk.Combobox)):return
            if hasattr(widget,'scroll_canvas'):
                action=widget.scroll_canvas.xview_scroll if getattr(widget,'scroll_axis','y')=='x' else widget.scroll_canvas.yview_scroll
                action(ui_platform.wheel_units(event.delta),'units');return 'break'
            if isinstance(widget,(ScrollPage,story_ui.StoryPage)):widget.canvas.yview_scroll(ui_platform.wheel_units(event.delta),'units');return
            widget=getattr(widget,'master',None)

    def browse_source(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('旋律','*.mid *.midi *.mmp')])
        if path:self.load_source(path)

    def browse_audio_source(self):
        path=filedialog.askopenfilename(
            parent=self.root,
            title='选择要转写的音频',
            filetypes=[('音频','*.wav *.mp3 *.ogg *.flac *.m4a'),('所有文件','*.*')],
        )
        if not path:return
        initial=round(self.source.bpm) if self.source else 120
        bpm=simpledialog.askfloat(
            '设置节拍',
            '请输入音频的 BPM（40–220）。\n转写最适合单一乐器、旋律清晰的音频。',
            parent=self.root,initialvalue=initial,minvalue=40,maxvalue=220,
        )
        if bpm is None:return
        def done(result):
            self.load_source(result['midi_path'])
            notes=result.get('note_count')
            detail=f" · {notes} 个音符" if notes is not None else ''
            self.source_text.set(f"{Path(result['audio_path']).name} → Basic Pitch MIDI · {bpm:g} BPM{detail}")
            self.tell('音频已在本机转为 MIDI。请选择旋律轨与 4–8 小节范围；原音频和转写信息已保留。')
        self.job(
            '正在用 Basic Pitch 在本机分析音频；较长文件可能需要几分钟…',
            lambda:audio_import.transcribe_audio(path,bpm),done,
        )

    def load_source(self,path):
        source=flow.music.load_source(path);self.source=source;self.source_path=str(path)
        names=[f'{i+1}. {t.name}' for i,t in enumerate(source.tracks)]
        for box in self.track_boxes:box.configure(values=names)
        self.track_var.set(names[0]);self.source_text.set(f'{Path(path).name} · {source.bpm:g} BPM')
        spans=max(n.start+n.duration for n in source.tracks[0].notes)/flow.BAR
        self.bars.set(str(min(8,max(4,int(__import__('math').ceil(spans))))));self.start_bar.set('1')
        self.refresh_quick();self.tell('已读取文件。请选择旋律轨与范围；同时起音处理需要你明确选择。')

    def import_reference(self,name='A',use_pool=False,reference_key=None):
        if not self.source_path:raise ValueError('请先导入旋律。')
        track=int(self.track_var.get().split('.')[0])-1
        key=reference_key
        if self.key.get()!='自动 / 沿用素材池':
            note,mode=self.key.get().split();key=(flow.music.NAMES.index(note),mode)
        elif use_pool and self.pool['items']:key=(self.pool['items'][0]['tonic'],self.pool['items'][0]['mode'])
        policy={'遇到同时起音时停止':'reject','保留低音（明确简化）':'lower','保留高音（明确简化）':'upper'}[self.policy.get()]
        return materials.import_theme(self.source_path,track,int(self.start_bar.get()),int(self.bars.get()),name,self.trim.get(),key,policy)

    def refresh_quick(self):
        if not hasattr(self,'quick_curve'):return
        try:bars=int(self.bars.get())
        except ValueError:bars=8
        self.quick_curve.set_rows([dict(p,name=self.input_themes[i]['name'] if self.input_themes else f'段 {i+1}',bars=self.input_themes[i]['bars'] if self.input_themes else max(1,bars)) for i,p in enumerate(self.curve)])
        if self.input_themes:
            total=sum(t['bars'] for t in self.input_themes);bpm=self.input_themes[0]['bpm']
            self.duration.set(f'{len(self.input_themes)} 个给定主题 · {total} 小节 · 约 {total*240/bpm:.0f} 秒主体（另加 1 秒尾音）');return
        bpm=self.source.bpm if self.source else 120
        self.duration.set(f'{len(self.curve)} 段 × {bars} 小节 · 约 {len(self.curve)*bars*240/bpm:.0f} 秒主体（另加 1 秒尾音）')

    def resize_curve(self):
        if self.input_themes:
            self.count.set(str(len(self.input_themes)));raise ValueError('多旋律模式的段数由输入列表决定；请添加或移除主题。')
        n=int(self.count.get())
        while len(self.curve)<n:self.curve.append(dict(emotion='resolve',start=.65,end=.85))
        self.curve=self.curve[:n];self.dirty=True;self.refresh_quick()

    def apply_curve(self,detail,first,last,emotion,start,end):
        key=next(k for k,v in flow.music.EMOTIONS.items() if v==emotion);a,b=float(start)/100,float(end)/100
        if detail:
            if not self.doc:raise ValueError('请先在结构页确认骨架。')
            new=flow.set_region(self.doc,first,last,key,a,b);self.undo_stack.append(copy.deepcopy(self.doc));self.doc=new
        else:
            if not 0<=first<=last<len(self.curve):raise ValueError('请选择有效的区间起止。')
            curve=copy.deepcopy(self.curve)
            lengths=[self.input_themes[i]['bars'] if self.input_themes else 1 for i in range(first,last+1)]
            total=sum(lengths);cursor=0
            for i,length in zip(range(first,last+1),lengths):
                curve[i]=dict(emotion=key,start=a+(b-a)*cursor/total,end=a+(b-a)*(cursor+length)/total);cursor+=length
            model.validate_curve(curve);self.curve=curve
        self.dirty=True;self.refresh();self.tell('情绪线已更新。已有试听保留，重新生成才会使用新设置。')

    def job(self,title,work,done):
        self.busy=True;self.tell(title);self.progress.place(relx=0,rely=1,anchor='sw',relwidth=1,height=3);self.progress.start(12);self.disabled=[]
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child,(ttk.Button,ttk.Entry,ttk.Combobox,ttk.Checkbutton,ttk.Scale,ttk.Radiobutton)):
                    if isinstance(child,ttk.Button) and child.cget('text')=='■ 停止':continue
                    self.disabled.append((child,child.state()));child.state(['disabled'])
                visit(child)
        visit(self.root)
        def worker():
            try:self.messages.put(('done',(done,work())))
            except Exception as exc:self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,payload=self.messages.get_nowait()
                if kind=='progress':self.tell(payload);continue
                self.busy=False;self.progress.stop();self.progress.place_forget()
                for widget,state in self.disabled:
                    if widget.winfo_exists():widget.state(['!disabled']);widget.state(state)
                self.disabled=[]
                if kind=='error':self.tell('未完成：'+payload+'；原项目与旧结果已保留。',True)
                else:
                    done,result=payload;self.safe(lambda:done(result))
        except queue.Empty:pass
        self.update_playback()
        if hasattr(self,'story_page'):
            self.story_page.preview_planner.poll()
            try:self.story_page.sync_source_player()
            except (ValueError,tk.TclError):pass
        self.timer=self.root.after(100,self.poll)

    def progress_message(self,text):self.messages.put(('progress',text))

    def quick_generate(self):
        themes=copy.deepcopy(self.input_themes)
        theme=None if themes else self.import_reference();curve=copy.deepcopy(self.curve);seed=int(self.seed.get());connection=self.connections.get()
        # Preserve the previous project before replacing it with a new quick draft.
        if self.pool['items'] or self.doc:self.save_project()
        def work():
            self.progress_message('发展关联素材并匹配情绪线…')
            doc=model.multi_document(themes,curve) if themes else model.quick_document(theme,curve,seed)
            return doc,flow.generate(doc,connection,self.progress_message)
        def done(result):
            self.doc,report=result;self.pool=copy.deepcopy(self.doc['pool']);self.undo_stack=[];self.dirty=True
            self.add_result(report,'快速成品');self.refresh();self.tell('成品已生成。右侧直接试听，或切换“精细创作”继续修改同一个项目。')
        self.job('开始生成成品…',work,done)

    def add_theme(self):
        if self.doc:raise ValueError('当前骨架已固定；如需建立新主题骨架，请新建项目。新建前会自动保存当前项目。')
        item=self.import_reference(self.name.get().strip() or 'A',True);materials.add_item(self.pool,item);self.dirty=True
        count=sum(i['kind']=='theme' for i in self.pool['items']);self.name.set(chr(65+count) if count<26 else f'Theme{count+1}')
        self.refresh(item['id']);self.tell('主题已加入。可继续导入 B/C/D，再到结构页确认顺序。')

    def selected_material(self):
        ids=self.library.selection()
        if not ids:raise ValueError('请选择一个素材。')
        return next(i for i in self.pool['items'] if i['id']==ids[0])

    def sync_pool(self):
        if self.doc:self.doc=model.merge_pool(self.doc,self.pool)

    def candidates(self,kind):
        parent=copy.deepcopy(self.selected_material());seed=int(self.seed.get())
        def done(items):
            pool=copy.deepcopy(self.pool);names={it['name'] for it in pool['items']}
            for item in items:
                choices=([chr(i) for i in range(69,91)]+[f'Answer{i}' for i in range(1,201)]) if kind=='answer' else [f'{parent["name"]}_c{i}' for i in range(1,201)]
                item['name']=next(name for name in choices if name not in names);names.add(item['name']);materials.add_item(pool,item)
            doc=model.merge_pool(self.doc,pool) if self.doc else None
            self.pool=pool;self.doc=doc;self.dirty=True;self.refresh(items[0]['id']);self.tell('候选已加入。先试听再保留；同一窗口内可到结构页选用。')
        self.job('正在发展旋律候选…',lambda:materials.generate_candidates(parent,kind,seed),done)

    def accept(self):
        item=self.selected_material();item['accepted']=True;self.sync_pool();self.dirty=True;self.refresh(item['id']);self.tell('候选已保留，结构页已同步。')

    def describe_material(self):
        try:
            item=self.selected_material();names={i['id']:i['name'] for i in self.pool['items']}
            report=item.get('import_report',{})
            import_text=(f'导入整理：截短 {report.get("shortened_overlaps",0)} 处尾音，裁切 {report.get("clipped_boundary_notes",0)} 处边界，按所选规则删减 {report.get("discarded_simultaneous_notes",0)} 个同时起音。' if report else '候选基于来源素材生成；保留表示选用，不是听感评分。')
            self.material_note.configure(text=f'{item["name"]} · {item["bars"]} 小节 · 来源：'+(' / '.join(names.get(p,p[:6]) for p in item['parents']) or '用户给定')+'\n'+('、'.join(item['methods']) or '原主题')+'\n'+import_text)
        except ValueError:pass

    def preview_material(self):
        item=copy.deepcopy(self.selected_material())
        self.stop_playback()
        if item['id'] in self.preview_cache:
            winsound.PlaySound(str(self.preview_cache[item['id']]),winsound.SND_FILENAME|winsound.SND_ASYNC);return
        def done(result):
            folder,_=result;path=folder/'preview.wav';self.preview_cache[item['id']]=path
            winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC);self.tell('正在试听素材：'+item['name'])
        self.job('正在准备中性音色试听…',lambda:materials.export_material(item),done)

    def move_theme(self,delta):
        if self.doc:raise ValueError('骨架已确认，不能重排。')
        selected=self.draft.curselection()
        if not selected:return
        themes=[i for i in self.pool['items'] if i['kind']=='theme'];i=selected[0];j=i+delta
        if not 0<=j<len(themes):return
        themes[i],themes[j]=themes[j],themes[i]
        self.pool['items']=themes+[it for it in self.pool['items'] if it['kind']!='theme'];self.dirty=True;self.refresh();self.draft.selection_set(j)

    def confirm_structure(self):
        if self.doc:raise ValueError('当前骨架已固定。')
        ids=[i['id'] for i in self.pool['items'] if i['kind']=='theme']
        self.doc=flow.prepare(structure.create(self.pool,ids));self.dirty=True;self.refresh();self.tell('骨架已按列表顺序固定。可原位替换变体、插入回答句，或设置情绪线。')

    def sid(self):
        if not self.doc or self.slot.current()<0:raise ValueError('请先确认骨架并选择位置。')
        return self.doc['backbone'][self.slot.current()]['id']

    def structure_choices(self):
        if not self.doc:return
        slot=next(s for s in self.doc['backbone'] if s['id']==self.sid());items={i['id']:i for i in self.pool['items']}
        self.replace_options=[i for i in items.values() if i['accepted'] and structure.family(items,i['id'])['id']==slot['theme_id']]
        self.answer_options=[i for i in items.values() if i['accepted'] and structure.family(items,i['id'])['kind']=='answer']
        self.replacement.configure(values=[i['name'] for i in self.replace_options]);self.replacement.set('')
        if self.replace_options:self.replacement.current(0)
        self.answer.configure(values=[i['name']+(' · 允许' if self.sid() in self.doc['permissions'].get(i['id'],[]) else ' · 需授权') for i in self.answer_options]);self.answer.set('')
        if self.answer_options:self.answer.current(0)
        self.role.set(slot['role'])

    def edit_structure(self,op,**args):
        if not self.doc:raise ValueError('请先确认骨架。')
        result=flow.prepare(structure.edit(self.doc,op,**args));self.undo_stack.append(copy.deepcopy(self.doc));self.doc=result;self.dirty=True;self.refresh();self.tell('结构已更新。请检查新插入块的情绪设置后重新生成。')

    def replace(self):
        if self.replacement.current()<0:raise ValueError('请选择可用原段或变体。')
        self.edit_structure('replace',slot_id=self.sid(),material_id=self.replace_options[self.replacement.current()]['id'])

    def answer_id(self):
        if self.answer.current()<0:raise ValueError('请先生成并保留回答句。')
        return self.answer_options[self.answer.current()]['id']

    def insert(self):self.edit_structure('insert',slot_id=self.sid(),material_id=self.answer_id())
    def authorize(self):self.edit_structure('authorize',slot_id=self.sid(),material_id=self.answer_id(),confirmed=True)

    def remove_insert(self):
        ids=self.route.selection()
        if not ids:raise ValueError('请选择展开列表中的插入项。')
        self.edit_structure('remove_insert',entry_id=ids[0])

    def add_transition(self):
        ids=self.route.selection()
        if not ids:raise ValueError('请在“当前展开”中选择过门前面的内容块。')
        bars=int(self.transition_bars.get())
        self.edit_structure('add_transition',entry_id=ids[0],bars=bars)
        self.tell(f'已生成 {bars} 小节独立过门，后续块顺延。请在情绪与连接页完整生成新基准；可撤销。')

    def remove_transition(self):
        ids=self.route.selection()
        if not ids:raise ValueError('请选择 T(前块 → 后块) 过门。')
        self.edit_structure('remove_transition',entry_id=ids[0])
        self.tell('过门已移除，后续块时间已回收。请完整生成；旧成品保留，可撤销。')

    def undo(self):
        if not self.undo_stack:raise ValueError('没有可撤销的结构或情绪编辑。')
        old=self.undo_stack.pop();self.doc=model.merge_pool(old,self.pool);self.dirty=True;self.refresh();self.tell('已撤销上一步，新增素材仍保留在素材池。')

    def detail_generate(self):
        if not self.doc:raise ValueError('请先在结构页确认骨架。')
        snapshot=copy.deepcopy(self.doc);connection=self.connections.get()
        self.job('正在生成连续作品…',lambda:flow.generate(snapshot,connection,self.progress_message),lambda report:self.add_result(report,'精细创作'))

    def preview_local(self):
        if not self.doc:raise ValueError('请先建立结构并生成一版作品。')
        report=copy.deepcopy(self.selected_report());snapshot=copy.deepcopy(self.doc)
        connection=self.connections.get()
        arrangement=local_engine.prepare_revision(snapshot,report,connection)
        self.local_preview=(snapshot,report,connection,arrangement)
        self.local_info.configure(text='基准：'+Path(report['output_directory']).name+'\n'+local_engine.summary(arrangement))
        self.tell('局部影响范围已显示。确认后点击“② 生成局部修改”。')

    def refresh_inner(self):
        if not hasattr(self,'inner_block'):return
        rows=structure.timeline(self.doc)['rows'] if self.doc else []
        index=self.inner_block.current();self.inner_block.configure(values=[r['name'] for r in rows])
        if not rows:
            self.inner_block.set('');self.inner_first.set('');self.inner_last.set('');self.inner_info.configure(text='先建立作品结构。');self.refresh_beats();return
        index=max(0,min(index,len(rows)-1));self.inner_block.current(index);row=rows[index]
        values=list(range(1,row['bars']+1));self.inner_first.configure(values=values);self.inner_last.configure(values=values)
        self.inner_first.set('1');self.inner_last.set(str(row['bars']))
        settings=flow.bar_settings(self.doc['expression'][row['id']],row['bars'])
        self.inner_info.configure(text='；'.join(f'{i+1}小节：{flow.music.EMOTIONS[v["emotion"]]} {v["start"]:.0%}→{v["end"]:.0%}' for i,v in enumerate(settings)))
        self.refresh_beats()

    def refresh_beats(self):
        if not hasattr(self,'beat_info'):return
        c=self.beat_canvas;c.delete('all');index=self.inner_block.current()
        if not self.doc or index<0:
            self.beat_info.configure(text='先选择音乐块。');self.beat_position.set('');return
        entry=self.doc['placements'][index];bars=structure.entry_material(self.doc,entry)['bars'];total=bars*4
        value=self.doc['expression'][entry['id']];nodes=value.get('beat_nodes',[
            dict(beat=0,intensity=value['start'],emotion=value['emotion']),dict(beat=total,intensity=value['end'],emotion=value['emotion'])])
        self.beat_position.configure(values=list(range(1,total+2)))
        if self.beat_position.get() not in [str(i) for i in range(1,total+2)]:self.beat_position.set('1')
        width=max(300,c.winfo_width());points=[]
        for n in nodes:
            x=25+(width-50)*n['beat']/total;y=105-80*n['intensity'];points.append((x,y))
        for i,(x,y) in enumerate(points):
            shade=COLORS[nodes[i]['emotion']]
            if i+1<len(points):c.create_line(x,y,*points[i+1],fill=shade,width=3)
            c.create_oval(x-4,y-4,x+4,y+4,fill=shade,outline='')
            c.create_text(x,119,text='终点' if nodes[i]['beat']==total else str(nodes[i]['beat']+1),fill=MUTED)
        self.beat_info.configure(text=('当前为小节细分，须先整块重置后启用拍级。' if 'bar_settings' in value else
            '；'.join(f'{"终点" if n["beat"]==total else str(n["beat"]+1)+"拍"}：{flow.music.EMOTIONS[n["emotion"]]} {n["intensity"]:.0%}' for n in nodes)))

    def pick_beat_point(self,event):
        if self.busy or not self.doc or self.inner_block.current()<0:return
        entry=self.doc['placements'][self.inner_block.current()];total=structure.entry_material(self.doc,entry)['bars']*4
        beat=max(0,min(total,round((event.x-25)/max(1,max(300,self.beat_canvas.winfo_width())-50)*total)))
        self.beat_position.set(str(beat+1));self.beat_level.set(str(round(max(0,min(1,(105-event.y)/80))*100)))

    def apply_beat(self,remove=False):
        index=self.inner_block.current()
        if not self.doc or index<0:raise ValueError('请先选择音乐块。')
        key=next(k for k,v in flow.music.EMOTIONS.items() if v==self.beat_emotion.get())
        new=flow.edit_beat_node(self.doc,self.doc['placements'][index]['id'],int(self.beat_position.get())-1,
            key,float(self.beat_level.get())/100,remove)
        self.undo_stack.append(copy.deepcopy(self.doc));self.doc=new;self.dirty=True;self.local_preview=None;self.refresh()
        self.tell('拍级情绪线已更新，未改变结构或时长。请生成新版本；旧音频保持。')

    def apply_inner(self):
        index=self.inner_block.current()
        if not self.doc or index<0:raise ValueError('请先选择要修改的音乐块。')
        entry=self.doc['placements'][index]
        emotion=next(k for k,v in flow.music.EMOTIONS.items() if v==self.inner_emotion.get())
        new=flow.set_block_region(self.doc,entry['id'],int(self.inner_first.get()),int(self.inner_last.get()),emotion,
                                 float(self.inner_start.get())/100,float(self.inner_end.get())/100)
        self.undo_stack.append(copy.deepcopy(self.doc));self.doc=new;self.dirty=True;self.local_preview=None;self.refresh()
        self.tell('块内情绪已应用，时长与顺序不变。可完整生成，或预览局部影响后生成；支持撤销。')

    def generate_local(self):
        if not self.local_preview:raise ValueError('请先点击“① 预览局部影响”。')
        snapshot,report,connection,arrangement=self.local_preview
        if self.doc!=snapshot or self.connections.get()!=connection or self.selected_report()['output_directory']!=report['output_directory']:
            self.local_preview=None
            raise ValueError('情绪、结构或基准已变化，请重新预览影响范围。')
        def work():
            verified=local_engine.prepare_revision(snapshot,report,connection)
            if verified!=arrangement:raise ValueError('基准或编配已变化，请重新预览。')
            return flow.generate(snapshot,connection,self.progress_message,arrangement=verified)
        def done(new_report):
            self.local_preview=None;self.add_result(new_report,'局部修改')
            self.local_info.configure(text=local_engine.summary(dict(report=new_report)))
            self.tell('局部版本已另存，范围外编配保持检查通过。旧版本仍可试听，可点击“撤回局部结果”。')
        self.job('保留范围外编配，生成局部版本…',work,done)

    def revert_local(self):
        report=self.selected_report();info=report.get('local_revision')
        if not info:raise ValueError('请在右侧选择一个局部修改结果。')
        base_folder=info['base_output_directory']
        base_doc,_=local_engine.load_baseline(dict(output_directory=base_folder))
        restored=model.merge_pool(base_doc,self.pool)
        self.stop_playback();self.undo_stack.append(copy.deepcopy(self.doc));self.doc=restored
        self.connections.set(report['connections_enabled']);self.local_preview=None;self.dirty=True;self.refresh()
        idx=next((i for i,r in enumerate(self.results) if r['report']['output_directory']==base_folder),None)
        if idx is None:
            base_report=json.loads((Path(base_folder)/'report.json').read_text(encoding='utf-8'))
            self.results.append(dict(mode='恢复基准',report=base_report));self.refresh_results();idx=len(self.results)-1
        self.result_list.selection_clear(0,'end');self.result_list.selection_set(idx);self.show_result()
        self.local_info.configure(text='已恢复基准的结构与情绪，并选中旧成品；局部结果保留在历史中，未删除文件。')
        self.tell('已撤回到局部修改前的基准；可再次编辑，或撤销这次恢复。')

    def add_result(self,report,mode):
        self.results.append(dict(mode=mode,report=report));self.dirty=True;self.refresh_results();self.tell('作品已另存。可在右侧试听、查看连接摘要并导出。')

    def refresh_results(self):
        self.result_list.delete(0,'end')
        self.audition_blocks=[];self.audition_page=0
        self.result_block.configure(values=[]);self.result_block.set('')
        for i,r in enumerate(self.results):self.result_list.insert('end',f'{i+1:02} · {r["mode"]} · {r["report"]["duration_seconds"]:.0f} 秒')
        if self.results:self.result_list.selection_set(len(self.results)-1);self.show_result()
        self.draw_history();self.draw_result_tiles()

    def selected_report(self):
        ids=self.result_list.curselection()
        if not ids:raise ValueError('请先生成或选择一个结果。')
        return self.results[ids[0]]['report']

    def show_result(self):
        try:
            report=self.selected_report();actions=[]
            self.load_waveform(report);self.draw_history()
            try:snapshot_blocks=model.playback_blocks(report)
            except (ValueError,OSError,KeyError):snapshot_blocks=[]
            self.audition_blocks=snapshot_blocks;self.audition_page=0
            old=self.result_block.current()
            self.result_block.configure(values=[f'{i+1:02} · '+b['name'].replace('默认 · ','').split(' / ')[0][:18] for i,b in enumerate(snapshot_blocks)])
            if snapshot_blocks:self.result_block.current(max(0,min(old,len(snapshot_blocks)-1)))
            self.draw_result_tiles()
            if self.playing_path!=report['output_directory']:
                self.stop_playback()
                try:self.play_blocks=model.playback_blocks(report)
                except (ValueError,OSError,KeyError):self.play_blocks=[]
                self.play_duration=report.get('audio',{}).get('seconds',report['duration_seconds']+1);self.draw_playback()
            for boundary in report.get('boundaries',[]):
                for action in boundary['actions']:
                    if action not in actions:actions.append(action)
            self.set_info(f'主体 {report["duration_seconds"]:.1f} 秒 + 1 秒尾音\n{report["bars"]} 小节 · {len(report.get("boundaries",[]))} 处边界\n连接：'+('开启' if report.get('connections_enabled') else '关闭')+'\n\n'+'\n'.join(actions)+'\n\n这是生成时的快照；后续编辑不改变此试听。\n\n位置：'+report['output_directory'])
            if report.get('local_revision'):
                self.set_info('局部修改版本\n'+local_engine.summary(dict(report=report))+'\n\n位置：'+report['output_directory'])
        except (ValueError,KeyError):pass

    def play(self):
        report=self.selected_report();path=Path(report['output_directory'])/'preview.wav'
        self.load_waveform(report)
        if not path.is_file():raise ValueError('试听文件已移动或缺失，请重新生成。')
        blocks=model.playback_blocks(report)
        self.stop_playback();self.play_blocks=blocks
        self.play_duration=self.player.play(path);self.playing_path=report['output_directory'];self.update_playback()

    def seek_event(self,event,phase):
        self.safe(lambda:self.seek_to_pointer(event.x,phase))
        return 'break'

    def seek_to_pointer(self,x,phase,width=None):
        if phase=='start':
            report=self.selected_report();path=Path(report['output_directory'])/'preview.wav'
            if not path.is_file():raise ValueError('试听文件已移动或缺失，请重新生成。')
            blocks=model.playback_blocks(report)
            # Read the actual WAV length, not an estimate from an old report.
            import wave
            with wave.open(str(path),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
            if duration<=.01:raise ValueError('试听音频过短。')
            self.stop_playback();self.play_blocks=blocks;self.play_duration=duration
            self.seek_drag=(path,report['output_directory'])
        if not self.seek_drag:return
        fraction=max(0.,min(1.,(x-8)/max(1,(width or self.play_progress.winfo_width())-16)))
        self.play_position=min(self.play_duration-.01,fraction*self.play_duration)
        self.play_progress['value']=100*self.play_position/self.play_duration
        self.play_label.configure(text=f'拖动定位：{self.play_position:.1f} / {self.play_duration:.1f} 秒\n松开后继续播放整曲')
        self.draw_playback()
        if phase=='end':
            path,identity=self.seek_drag;position=self.play_position;self.seek_drag=None
            try:
                self.play_duration=self.player.play(path,start=position)
                self.playing_path=identity;self.update_playback()
            except Exception:
                self.stop_playback();raise

    def play_segment(self,path,blocks,index,identity,label):
        if not 0<=index<len(blocks):raise ValueError('请先选择要试听的块。')
        self.load_waveform_path(path)
        block=blocks[index];self.stop_playback();self.play_blocks=blocks
        self.play_duration=self.player.play(path,block['start_seconds'],block['end_seconds'])
        self.segment_end=block['end_seconds'];self.segment_label=label
        self.playing_path=identity;self.update_playback()

    def play_result_block(self):
        report=self.selected_report();blocks=model.playback_blocks(report)
        self.play_segment(Path(report['output_directory'])/'preview.wav',blocks,self.result_block.current(),report['output_directory'],'成品分块试听')

    def next_result_block(self):
        values=self.result_block['values'];index=self.result_block.current()+1
        if not values or index>=len(values):raise ValueError('已到最后一块。')
        self.result_block.current(index);self.play_result_block()

    def stop_playback(self):
        self.seek_drag=None;self.transport_running=False
        try:self.player.close()
        except ValueError:pass
        winsound.PlaySound(None,0);self.playing_path=None;self.play_position=0.
        self.segment_end=None;self.segment_label=''
        if hasattr(self,'play_label'):
            self.play_label.configure(text='已停止');self.play_progress['value']=0;self.draw_playback()

    def update_playback(self):
        if not self.playing_path:return
        try:
            seconds,mode=self.player.status();self.play_position=seconds;self.transport_running=mode=='playing'
            self.play_progress['value']=min(100,seconds/max(.001,self.play_duration)*100)
            index=model.active_block(self.play_blocks,seconds)
            if mode=='stopped':
                end=self.segment_end if self.segment_end is not None else self.play_duration
                self.player.close();self.playing_path=None;self.play_position=end;self.play_progress['value']=end/max(.001,self.play_duration)*100
                self.play_label.configure(text=f'{self.segment_label or "整曲"}播放结束 · {end:.2f} 秒');self.draw_playback();return
            text=(f'正在播放：{self.play_blocks[index]["name"]}（第 {index+1}/{len(self.play_blocks)} 块）' if index is not None else ('尾音释放' if self.play_blocks else '播放中（旧结果无分块记录）'))
            if index is not None:
                current=model.playback_emotion(self.play_blocks[index],seconds)
                text+='\n'+(f'块内第 {current["bar"]} 小节 · ' if current['bar'] else '')+flow.music.EMOTIONS.get(current['emotion'],current['emotion'])
                if current.get('beat'):text+=f' · 第 {current["beat"]} 拍 · {current["intensity"]:.0%}'
                elif 'intensity' in current:text+=f' · {current["intensity"]:.0%}'
            self.play_label.configure(text=(self.segment_label+'\n' if self.segment_label else '')+text+f'\n{seconds:.1f} / {self.play_duration:.1f} 秒');self.draw_playback()
        except Exception as exc:self.stop_playback();self.tell(str(exc),True)


    def export_result(self,kind):
        folder=Path(self.selected_report()['output_directory']);source=folder/('preview.wav' if kind=='wav' else 'composition.'+kind)
        if not source.is_file():raise ValueError('原输出文件已移动或缺失。')
        target=filedialog.asksaveasfilename(parent=self.root,initialfile='EmoBlocks作品.'+kind,defaultextension='.'+kind,filetypes=[(kind.upper(),'*.'+kind)])
        if target:
            if Path(target).resolve()!=source.resolve():shutil.copyfile(source,target)
            self.tell('已导出：'+target)

    def refresh(self,selected=None):
        self.refresh_inner()
        self.refresh_quick()
        old=self.library.selection();selected=selected or (old[0] if old else None)
        self.library.delete(*self.library.get_children());self.draft.delete(0,'end')
        kinds=dict(theme='原主题',variant='内容变体',answer='关联回答句')
        for item in self.pool['items']:
            self.library.insert('','end',iid=item['id'],text=item['name'],values=(kinds[item['kind']],'已选用' if item['accepted'] else '候选'))
            if item['kind']=='theme':self.draft.insert('end',item['name'])
        if selected and self.library.exists(selected):self.library.selection_set(selected)
        self.route.delete(*self.route.get_children())
        if self.doc:
            info=structure.timeline(self.doc);rows=info['rows'];items={i['id']:i for i in self.pool['items']};slots={s['id']:s for s in self.doc['backbone']}
            for row in rows:self.route.insert('','end',iid=row['id'],text=row['name'],values=(slots[row['slot_id']]['role'] if row['kind']=='slot' else '独立过门' if row['kind']=='transition' else '关联插入',row['bars']))
            index=self.slot.current();self.slot.configure(values=[items[s['theme_id']]['name'] for s in self.doc['backbone']]);self.slot.current(max(0,min(index,len(slots)-1)));self.structure_choices()
            self.detail_curve.set_rows([dict(self.doc['expression'][r['id']],name=r['name'],bars=r['bars']) for r in rows])
            self.summary.configure(text=f'{len(self.pool["items"])} 个素材 · {len(rows)} 个内容块\n{info["bars"]} 小节 / {info["seconds"]:.0f} 秒主体\n\n'+' → '.join(r['name'] for r in rows))
        else:
            self.detail_curve.set_rows([]);self.slot.configure(values=[]);self.slot.set('');self.replacement.set('');self.answer.set('')
            self.summary.configure(text='等待生成')

    def save_project(self):
        settings=dict(connections=self.connections.get(),seed=self.seed.get(),source_path=self.source_path,track=self.track_var.get(),start_bar=self.start_bar.get(),bars=self.bars.get(),policy=self.policy.get(),trim=self.trim.get(),key=self.key.get(),input_themes=self.input_themes)
        settings['story']=self.story_page.snapshot()
        path=model.save_project(self.pool,self.doc,self.curve,self.results,settings);self.dirty=False;self.tell('已另存项目快照：'+str(path));return path

    def load_project(self,path):
        data=model.load_project(path)
        story=data.get('settings',{}).get('story',story_ui.engine.new_project())
        story_ui.engine.validate(story,require_source=False)
        if self.dirty:self.save_project()
        self.stop_playback()
        self.input_themes=copy.deepcopy(data.get('settings',{}).get('input_themes',[]))
        self.pool,self.doc,self.curve,self.results=data['pool'],data['doc'],data['curve'],data['results'];self.undo_stack=[];self.preview_cache={};self.dirty=False
        settings=data.get('settings',{});self.connections.set(settings.get('connections',True));self.seed.set(str(settings.get('seed',31)))
        self.source=None;self.source_path=None;self.track_var.set('');self.source_text.set('工程已恢复；如需再次快速创作，请导入参考旋律。')
        for box in self.track_boxes:box.configure(values=[])
        source_issue=''
        if settings.get('source_path'):
            try:
                self.load_source(settings['source_path'])
                if settings.get('track') in self.track_boxes[0]['values']:self.track_var.set(settings['track'])
            except Exception as exc:source_issue=' 原导入文件无法读取，但已保存素材仍可编辑：'+str(exc)
        for var,key in ((self.start_bar,'start_bar'),(self.bars,'bars'),(self.policy,'policy'),(self.trim,'trim'),(self.key,'key')):
            if key in settings:var.set(settings[key])
        self.count.set(str(len(self.curve)));self.refresh_inputs();self.refresh();self.refresh_results();self.modes.select(1)
        if self.doc:self.detail_tabs.select(2)
        self.story_page.restore(story)
        if story['sources']:self.modes.select(self.story_page)
        self.dirty=False;self.tell('工程已打开。结构、情绪和结果在同一窗口恢复。'+source_issue)

    def open_project(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('EmoBlocks 工程','*.json')])
        if path:self.load_project(path)

    def new_project(self):
        if self.dirty or self.pool['items']:self.save_project()
        self.stop_playback();self.input_themes=[];self.play_blocks=[];self.draw_playback();self.refresh_inputs()
        self.pool=materials.new_pool();self.doc=None;self.results=[];self.undo_stack=[];self.dirty=False;self.name.set('A');self.refresh();self.refresh_results();self.set_info('已新建项目。前一个项目已自动另存，不覆盖。');self.tell('新项目就绪。')
        self.story_page.restore(story_ui.engine.new_project())
        self.modes.select(self.story_page)

    def close(self):
        if self.busy:self.tell('正在生成，请完成后再关闭。',True);return
        try:
            if self.dirty:self.save_project()
        except Exception as exc:self.tell('自动保存失败，未关闭：'+str(exc),True);return
        self.story_page.preview_planner.close()
        if hasattr(self.story_page,'file_drop'):self.story_page.file_drop.close()
        self.stop_playback();self.root.after_cancel(self.timer);self.root.destroy()
