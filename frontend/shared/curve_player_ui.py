"""Bounded actual PCM waveform and immutable-object block navigation UI."""
import audioop
from collections import OrderedDict
import hashlib
import math
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
import wave
from curve_theme import font, hint
from curve_icons import IconButton
from curve_raster import pixels


def waveform(path, bins=1024):
    """Read every PCM frame in bounded chunks; no synthetic envelope."""
    with wave.open(str(path),'rb') as stream:
        width=stream.getsampwidth();frames=stream.getnframes();rate=stream.getframerate()
        chunk=max(1,math.ceil(frames/bins));values=[]
        for _ in range(bins):
            data=stream.readframes(chunk)
            if not data:break
            if width==1:data=audioop.bias(data,1,-128)
            values.append(audioop.rms(data,width)/float(2**(8*width-1)))
    return values,frames/rate


class Waveform(tk.Canvas):
    def __init__(self,parent,app):
        self.app=app;self.values=[];self.key=None;self.pending=None;self.error=None
        self.results=queue.Queue();self.cache=OrderedDict();self.alive=True
        super().__init__(parent,height=pixels(app.root,44),highlightthickness=0,takefocus=True)
        self.bind('<Configure>',self.draw)
        self.bind('<ButtonPress-1>',self.press);self.bind('<B1-Motion>',self.motion);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<Left>',lambda _:self.seek_offset(-1));self.bind('<Right>',lambda _:self.seek_offset(1))
        self.bind('<Destroy>',lambda e:self.dispose() if e.widget==self else None)
        hint(self,lambda:self.error or '实际 WAV 波形；拖动定位会重新核对当前播放资产。',app.show_detail)

    def dispose(self):self.alive=False;self.cache.clear();self.key=None

    def set_target(self,playing):
        asset=(playing or {}).get('asset',{})
        identity=json.dumps(dict(target=(playing or {}).get('target'),key=(playing or {}).get('context',{}).get('key'),
            ref=asset.get('score_ref'),id=asset.get('id'),version=asset.get('version'),profile=asset.get('renderer_version'),mode=asset.get('mode'),side=asset.get('kind')),sort_keys=True)
        key=(asset['wav_path'],playing['wav_digest'],identity) if asset.get('wav_path') and playing.get('wav_digest') else None
        if key==self.key:return
        self.key=key;self.pending=None;self.error=None;self.values=[]
        if key in self.cache:self.values=self.cache[key];self.cache.move_to_end(key)
        elif key:
            self.pending=key
            results=self.results
            def work():
                try:
                    values,_=waveform(key[0])
                    digest=hashlib.sha256()
                    with Path(key[0]).open('rb') as stream:
                        for data in iter(lambda:stream.read(65536),b''):digest.update(data)
                    digest=digest.hexdigest()
                    if digest!=key[1]:raise ValueError('音频文件已变化，波形不可用。')
                    results.put((key,values,None))
                except Exception as exc:results.put((key,[],str(exc)))
            try:threading.Thread(target=work,daemon=True).start()
            except Exception as exc:self.pending=None;self.error='波形读取失败：'+str(exc)
        self.draw()

    def drain(self):
        while True:
            try:key,values,error=self.results.get_nowait()
            except queue.Empty:break
            if not self.alive or key!=self.key:continue
            self.pending=None;self.error=error;self.values=values
            if not error:
                self.cache[key]=values
                while len(self.cache)>8:self.cache.popitem(last=False)
            self.draw()

    def draw(self,event=None):
        p=self.app.theme.colors;self.configure(bg=p['inset']);self.delete('all')
        w,h=self.winfo_width(),self.winfo_height()
        if not self.values:
            text=self.error or ('读取实际 WAV…' if self.pending else '尚未播放 · 无音频波形')
            self.create_text(8,h/2,anchor='w',text=text,fill=p['muted'],font=font(10),tags='wave-empty');return
        count=max(1,w-12)
        for x in range(count):
            a=x*len(self.values)//count;b=max(a+1,(x+1)*len(self.values)//count)
            level=max(self.values[a:b],default=0)
            amplitude=min(h/2-4,level*(h/2-4))
            self.create_line(x+6,h/2-amplitude,x+6,h/2+amplitude,fill=p['muted'],width=1,tags='pcm-wave')
        if self.app.play_duration:
            x=6+(w-12)*min(1,self.app.seek_value.get()/self.app.play_duration)
            self.create_line(x,3,x,h-3,fill=p['accent'],width=2,tags='wave-position')

    def motion(self,event):
        if not self.app.playing_target:return 'break'
        self.app.seek_value.set(max(0,min(1,(event.x-6)/max(1,self.winfo_width()-12)))*self.app.play_duration)
        self.draw();return 'break'

    def press(self,event):
        self.focus_set();self.app.seek_active=True;self.motion(event);return 'break'

    def release(self,event):
        self.motion(event);self.app.safe(self.app.seek_release);return 'break'

    def seek_offset(self,offset):
        if self.app.playing_target:
            self.app.seek_value.set(max(0,min(self.app.play_duration,self.app.seek_value.get()+offset)))
            self.app.safe(self.app.seek_release)
        return 'break'


def build_transport(app,footer):
    top=app.footer_top=ttk.Frame(footer,style='Curve.Panel.TFrame');top.pack(fill='x')
    top.columnconfigure(0,weight=1)
    app.transport_label=ttk.Label(top,text='尚未播放',style='Curve.Panel.TLabel',takefocus=True)
    app.transport_label.grid(row=0,column=0,sticky='ew')
    hint(app.transport_label,app.transport_description,app.show_detail)
    app.transport_label.bind('<Button-1>',lambda _:app.show_detail(app.transport_description()))
    app.player_version=tk.StringVar()
    app.version_selector=ttk.Combobox(top,textvariable=app.player_version,state='readonly',width=15,style='Curve.TCombobox',takefocus=True)
    app.version_selector.grid(row=0,column=1,sticky='e',ipady=pixels(app.root,7))
    app.version_selector.bind('<<ComboboxSelected>>',lambda _:select_version(app))
    hint(app.version_selector,'选择导出版本；不改变当前播放对象。完整名称见详情。',app.show_detail)
    app.version_ids=[]
    row=ttk.Frame(footer,style='Curve.Panel.TFrame');row.pack(fill='x')
    app.waveform=Waveform(row,app);app.waveform.pack(side='left',fill='x',expand=True)
    app.navigation=tk.StringVar(value='积木导航不可用')
    app.block_selector=ttk.Combobox(row,textvariable=app.navigation,width=12,state='disabled',style='Curve.TCombobox',takefocus=True)
    app.block_selector.pack(side='right',ipady=pixels(app.root,7))
    app.block_selector.bind('<<ComboboxSelected>>',lambda _:navigate(app,app.block_selector.current()))
    hint(app.block_selector,lambda:getattr(app,'navigation_reason','请明确播放有可信映射的对象。'),app.show_detail)
    row=ttk.Frame(footer,style='Curve.Panel.TFrame');row.pack(fill='x',pady=(2,0))
    app.previous_button=IconButton(row,app,'previous','上一积木',lambda:app.safe(lambda:adjacent(app,-1)))
    app.previous_button.pack(side='left')
    app.play_button=IconButton(row,app,'play','试听所选对象',lambda:app.safe(app.audition_selected),style='Curve.Primary.TButton')
    app.prepare_button=app.play_button;app.play_button.pack(side='left',padx=1)
    app.pause_button=IconButton(row,app,'pause','暂停或继续',lambda:app.safe(app.toggle_pause));app.pause_button.pack(side='left',padx=1)
    app.stop_button=IconButton(row,app,'stop','停止',app.stop);app.stop_button.pack(side='left',padx=1)
    app.next_button=IconButton(row,app,'next','下一积木',lambda:app.safe(lambda:adjacent(app,1)));app.next_button.pack(side='left',padx=1)
    app.seek_value=tk.DoubleVar(value=0.)
    # Retain callable Scale contract; the actual interactive surface is the PCM waveform.
    app.seek=ttk.Scale(row,variable=app.seek_value,from_=0,to=1,style='Curve.Horizontal.TScale')
    app.cancel_button=IconButton(row,app,'cancel','取消',app.cancel_jobs,label=True);app.cancel_button.pack(side='right')
    app.export_menu=tk.Menu(app.root,tearoff=False)
    app.page.export_buttons={}
    for fmt,text in (('wav','WAV'),('mid','MIDI'),('mmp','MMP')):
        app.export_menu.add_command(label=text,command=lambda f=fmt:app.export_history(f))
        b=ttk.Button(row,text=text,command=lambda f=fmt:app.export_history(f),style='Curve.TButton',width=0,padding=(pixels(app.root,5),0))
        b.pack(side='right',padx=1);app.page.export_buttons[fmt]=b
        hint(b,'仅导出所选版本的'+text+'；格式独立认证，不替换当前播放。',app.show_detail)
    app.export_menu_button=ttk.Menubutton(row,text='导出',menu=app.export_menu,style='Curve.TMenubutton')


def select_version(app):
    i=app.version_selector.current()
    if 0<=i<len(app.version_ids):
        app.select_target('history',app.version_ids[i]);app.update_exports()
        app.show_detail(app.history_output_description(app.resolve('history',app.version_ids[i])))


def navigate(app,index):
    playing=app.playing_target
    if not playing or not 0<=index<len(playing.get('segments',[])):return False
    app.validate_playing()
    segment=playing['segments'][index];app.seek_value.set(segment['start_tick']*60/(480*playing['bpm']))
    app.seek_release();return True


def adjacent(app,direction):
    playing=app.playing_target
    if not playing or not playing.get('segments'):return False
    tick=app.player.status()[0]*480*playing['bpm']/60
    rows=playing['segments'];index=max((i for i,s in enumerate(rows) if s['start_tick']<=tick),default=0)
    return navigate(app,max(0,min(len(rows)-1,index+direction)))


def update_navigation(app):
    playing=app.playing_target;rows=playing.get('segments',[]) if playing else []
    enabled=bool(rows and playing.get('bpm'))
    app.navigation_reason=(playing.get('mapping_reason') or '导航使用当前播放快照的精确范围；不会选择或应用工程积木。') if playing else '尚无播放对象；不会借用当前编辑工程推测。'
    if getattr(app,'navigation_rows',None)!=rows:
        app.navigation_rows=rows
        app.block_selector.configure(values=[f'{i+1} · {s["start_tick"]/480:g}–{s["end_tick"]/480:g}拍' for i,s in enumerate(rows)])
    app.block_selector.configure(state='readonly' if enabled else 'disabled')
    for b in (app.previous_button,app.next_button):b.state(['!disabled'] if enabled else ['disabled'])
    if enabled:
        tick=app.player.status()[0]*480*playing['bpm']/60
        index=max((i for i,s in enumerate(rows) if s['start_tick']<=tick),default=0)
        if playing.get('context',{}).get('total_ticks') is not None and tick>=playing['context']['total_ticks']:app.navigation.set('余音 · 正文结束')
        else:app.block_selector.current(index)
    else:app.navigation.set('映射不可用')
    app.waveform.set_target(playing);app.waveform.drain();app.waveform.draw()
