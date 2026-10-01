"""Emotion regions and whole-score preview, without rearranging the backbone."""
import copy
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from ui_scale import font as scaled_font
import legacy_audio as winsound
import flow_engine as engine

COLORS=dict(calm='#75bddd',hope='#e6c778',sad='#8291d6',suspense='#b391cc',crisis='#df7972',resolve='#73c6a1')


class FlowWindow:
    def __init__(self,parent,doc):
        self.window=tk.Toplevel(parent);self.window.title('EmoBlocks · 情绪线与连续作品')
        self.window.geometry('1060x760');self.window.minsize(900,680)
        self.doc=engine.prepare(doc);self.dirty=False;self.busy=False;self.report=None
        self.messages=queue.Queue();self.undo_stack=[]
        base=ttk.Frame(self.window,padding=16);base.pack(fill='both',expand=True)
        ttk.Label(base,text='在固定结构上绘制情绪发展',font=scaled_font(('Microsoft YaHei UI',18,'bold'))).pack(anchor='w')
        ttk.Label(base,text='选择连续多个块作为情绪区间；强度按小节展开。主旋律与骨架保留，不新增过渡小节。').pack(anchor='w',pady=6)
        self.tree=ttk.Treeview(base,columns=('range','emotion','level'),show='tree headings',height=7)
        for col,title,width in [('#0','内容顺序（不可拖动）',280),('range','小节',130),('emotion','情绪',180),('level','强度起止',150)]:
            self.tree.heading(col,text=title);self.tree.column(col,width=width)
        self.tree.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(base,height=140,bg='#101724',highlightthickness=0);self.canvas.pack(fill='x',pady=8)
        self.canvas.bind('<Configure>',lambda event:self.draw())
        row=ttk.Frame(base);row.pack(fill='x',pady=5)
        ttk.Label(row,text='区间起点').pack(side='left')
        self.first=ttk.Combobox(row,state='readonly',width=24);self.first.pack(side='left',padx=5)
        ttk.Label(row,text='终点').pack(side='left')
        self.last=ttk.Combobox(row,state='readonly',width=24);self.last.pack(side='left',padx=5)
        self.emotion=ttk.Combobox(row,state='readonly',values=list(engine.music.EMOTIONS.values()),width=18)
        self.emotion.current(0);self.emotion.pack(side='left',padx=5)
        row=ttk.Frame(base);row.pack(fill='x',pady=5)
        self.start=tk.StringVar(value='35');self.end=tk.StringVar(value='65')
        for label,var in [('开始强度 %',self.start),('结束强度 %',self.end)]:
            ttk.Label(row,text=label).pack(side='left',padx=4);ttk.Entry(row,textvariable=var,width=6).pack(side='left',padx=4)
        ttk.Button(row,text='应用情绪区间',command=lambda:self.guard(self.apply)).pack(side='left',padx=8)
        ttk.Button(row,text='撤销情绪修改',command=lambda:self.guard(self.undo)).pack(side='left',padx=4)
        ttk.Button(row,text='保存情绪结构快照',command=lambda:self.guard(self.save)).pack(side='left',padx=4)
        self.connections=tk.BooleanVar(value=True)
        ttk.Checkbutton(base,text='启用连接处理：和弦共同音延留、低音导向、节奏引入／释放（关闭可生成对照版）',variable=self.connections).pack(anchor='w',pady=8)
        row=ttk.Frame(base);row.pack(fill='x',pady=4)
        ttk.Button(row,text='生成整段作品',command=lambda:self.guard(self.generate)).pack(side='left',padx=4)
        ttk.Button(row,text='试听上次结果',command=lambda:self.guard(self.play)).pack(side='left',padx=4)
        ttk.Button(row,text='停止',command=lambda:winsound.PlaySound(None,0)).pack(side='left',padx=4)
        ttk.Button(row,text='打开结果文件夹',command=lambda:self.guard(self.folder)).pack(side='left',padx=4)
        self.progress=ttk.Progressbar(base,mode='indeterminate');self.progress.pack(fill='x',pady=7)
        self.status=ttk.Label(base,text='尚未生成。整段共用和声规划、音轨和一次渲染；每次输出另存。',wraplength=990)
        self.status.pack(anchor='w',pady=5)
        self.refresh();self.timer=self.window.after(100,self.poll)
        self.window.protocol('WM_DELETE_WINDOW',self.close)

    def guard(self,fn):
        if self.busy:return
        try:return fn()
        except Exception as exc:messagebox.showerror('情绪作品操作未完成',str(exc),parent=self.window)

    def refresh(self):
        rows=engine.structure.timeline(self.doc)['rows']
        self.tree.delete(*self.tree.get_children())
        names=[]
        for i,row in enumerate(rows):
            v=self.doc['expression'][row['id']];names.append(f'{i+1}. {row["name"]}')
            self.tree.insert('','end',iid=row['id'],text=names[-1],values=(f'{row["start_bar"]}–{row["start_bar"]+row["bars"]-1}',engine.music.EMOTIONS[v['emotion']],f'{v["start"]*100:.0f}% → {v["end"]*100:.0f}%'))
        a,b=self.first.current(),self.last.current()
        self.first.configure(values=names);self.last.configure(values=names)
        self.first.current(max(0,a));self.last.current(len(names)-1 if b<0 else b)
        self.draw()

    def draw(self):
        if not hasattr(self,'canvas'):return
        canvas=self.canvas;canvas.delete('all');width=max(300,canvas.winfo_width())
        rows=engine.structure.timeline(self.doc);total=rows['bars']
        for value in (0,.5,1):
            y=115-value*85;canvas.create_line(32,y,width-10,y,fill='#324052');canvas.create_text(16,y,text=f'{round(value*100)}',fill='#adc0ce')
        previous=None
        for row in rows['rows']:
            v=self.doc['expression'][row['id']];color=COLORS[v['emotion']]
            x=32+(width-42)*(row['start_bar']-1)/total;end=x+(width-42)*row['bars']/total
            y1,y2=115-v['start']*85,115-v['end']*85
            canvas.create_rectangle(x,4,end,18,fill=color,outline='')
            canvas.create_text((x+end)/2,11,text=row['name'],fill='#101724')
            canvas.create_line(x,20,x,125,fill='#293952')
            if previous:canvas.create_line(x,previous,x,y1,fill='#d6dfe7',dash=(3,3))
            canvas.create_line(x,y1,end,y2,fill=color,width=3);previous=y2
        canvas.create_text(36,133,anchor='w',text='颜色＝情绪类别；折线＝目标强度（非音频响度测量）。',fill='#adc0ce')

    def apply(self):
        key=list(engine.music.EMOTIONS)[self.emotion.current()]
        new=engine.set_region(self.doc,self.first.current(),self.last.current(),key,float(self.start.get())/100,float(self.end.get())/100)
        self.undo_stack.append(self.doc);self.doc=new;self.dirty=True;self.refresh()
        self.status.configure(text='情绪区间已更新。旧试听不会自动改变，请重新生成；本版重新规划整段，不承诺其他块编配不变。')

    def undo(self):
        if not self.undo_stack:raise ValueError('没有可撤销的情绪修改。')
        self.doc=self.undo_stack.pop();self.dirty=True;self.refresh()

    def save(self):
        path=engine.structure.save(self.doc);self.dirty=False;self.status.configure(text='已保存：'+str(path));return path

    def generate(self):
        snapshot=copy.deepcopy(self.doc);connection=self.connections.get()
        self.busy=True;self.progress.start(12);self.status.configure(text='生成中…')
        def worker():
            try:self.messages.put(('done',engine.generate(snapshot,connection,lambda msg:self.messages.put(('progress',msg)))))
            except Exception as exc:self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.messages.get_nowait()
                if kind=='progress':self.status.configure(text=value)
                else:
                    self.busy=False;self.progress.stop()
                    if kind=='done':
                        self.report=value
                        self.status.configure(text=f'已生成 {value["duration_seconds"]:.1f} 秒主体 + 1 秒尾音，{len(value["boundaries"])} 处边界。可试听或打开 MIDI / MMP / WAV 与连接报告。')
                    else:
                        self.status.configure(text='生成失败，原结构和上次结果保留。')
                        messagebox.showerror('生成失败',value,parent=self.window)
        except queue.Empty:pass
        self.timer=self.window.after(100,self.poll)

    def folder(self):
        if not self.report:raise ValueError('请先生成作品。')
        os.startfile(self.report['output_directory'])

    def play(self):
        if not self.report:raise ValueError('请先生成作品。')
        winsound.PlaySound(str(Path(self.report['output_directory'])/'preview.wav'),winsound.SND_FILENAME|winsound.SND_ASYNC)

    def preserve(self):
        if self.busy:messagebox.showinfo('正在生成','请等待整段渲染完成再关闭。',parent=self.window);return False
        if not self.dirty:return True
        result=messagebox.askyesnocancel('保存情绪线','是否保存当前情绪结构快照？',parent=self.window)
        if result is None:return False
        if result and not self.guard(self.save):return False
        return True

    def close(self):
        if self.preserve():self.dispose()

    def dispose(self):
        winsound.PlaySound(None,0);self.window.after_cancel(self.timer);self.window.destroy()
