"""Structure editing UI. No free reordering once the user confirms the backbone."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import structure_engine as engine


class StructureWindow:
    def __init__(self, parent, pool):
        self.window = tk.Toplevel(parent)
        self.window.title('EmoBlocks · 步骤三 / 结构约束')
        self.window.geometry('1020x720'); self.window.minsize(880,640)
        self.pool = copy.deepcopy(pool); self.doc = None; self.dirty = False; self.undo_stack = []
        self.flow_windows=[]
        self.themes = [i for i in self.pool['items'] if i['kind']=='theme' and i['accepted']]
        base = ttk.Frame(self.window,padding=16); base.pack(fill='both',expand=True)
        from ui_scale import font as scaled_font
        ttk.Label(base,text='先确认主题骨架，再发展内容',font=scaled_font(('Microsoft YaHei UI',18,'bold'))).pack(anchor='w')
        ttk.Label(base,text='默认按原主题导入顺序建议；这不是自动推断乐句关系。确认后禁止重排、删减和重复。').pack(anchor='w',pady=5)
        top = ttk.Frame(base); top.pack(fill='x',pady=6)
        for text,cmd in [('打开结构工程',self.open),('保存快照',self.save),('撤销本次编辑',self.undo)]:
            ttk.Button(top,text=text,command=lambda fn=cmd:self.guard(fn)).pack(side='left',padx=4)
        ttk.Button(top,text='情绪线与连续作品 →',command=lambda:self.guard(self.open_flow)).pack(side='right',padx=4)
        self.draft = tk.Listbox(base,height=4,exportselection=False,font=scaled_font(('Microsoft YaHei UI',11)))
        self.draft.pack(fill='x')
        self.refresh_draft()
        actions=ttk.Frame(base); actions.pack(fill='x',pady=6)
        self.up=ttk.Button(actions,text='确认前上移',command=lambda:self.move(-1)); self.up.pack(side='left',padx=4)
        self.down=ttk.Button(actions,text='确认前下移',command=lambda:self.move(1)); self.down.pack(side='left',padx=4)
        self.confirm=ttk.Button(actions,text='确认并固定此骨架',command=lambda:self.guard(self.lock)); self.confirm.pack(side='left',padx=4)
        ttk.Label(actions,text='确认仅限本结构工程，不改素材池。').pack(side='left',padx=8)
        self.route=ttk.Treeview(base,columns=('role','range','kind'),show='tree headings',height=7,selectmode='browse')
        for c,t,w in [('#0','当前展开',300),('role','段落角色',130),('range','小节范围',120),('kind','内容类型',140)]:
            self.route.heading(c,text=t); self.route.column(c,width=w)
        self.route.pack(fill='both',expand=True)
        row=ttk.Frame(base); row.pack(fill='x',pady=7)
        ttk.Label(row,text='骨架位置').pack(side='left')
        self.slot=ttk.Combobox(row,state='readonly',width=22); self.slot.pack(side='left',padx=6)
        self.slot.bind('<<ComboboxSelected>>',lambda event:self.refresh_choices())
        self.role=ttk.Combobox(row,state='readonly',values=engine.ROLES,width=12); self.role.current(0); self.role.pack(side='left',padx=4)
        ttk.Button(row,text='设置角色',command=lambda:self.guard(lambda:self.apply('role',slot_id=self.sid(),role=self.role.get()))).pack(side='left')
        row=ttk.Frame(base); row.pack(fill='x',pady=4)
        self.replacement=ttk.Combobox(row,state='readonly',width=36); self.replacement.pack(side='left',padx=4)
        ttk.Button(row,text='原位替换 / 还原',command=lambda:self.guard(self.replace)).pack(side='left',padx=4)
        row=ttk.Frame(base); row.pack(fill='x',pady=4)
        self.answer=ttk.Combobox(row,state='readonly',width=36); self.answer.pack(side='left',padx=4)
        ttk.Button(row,text='在此段后插入',command=lambda:self.guard(self.insert)).pack(side='left',padx=4)
        ttk.Button(row,text='明确授权此位置',command=lambda:self.guard(self.authorize)).pack(side='left',padx=4)
        ttk.Button(row,text='移除选中插入项',command=lambda:self.guard(self.remove)).pack(side='left',padx=4)
        self.status=ttk.Label(base,text='先检查并确认原主题顺序，再打开“情绪线与连续作品”。',wraplength=960)
        self.status.pack(anchor='w',pady=8)
        self.window.protocol('WM_DELETE_WINDOW',self.close)

    def guard(self, fn):
        try: return fn()
        except Exception as exc: messagebox.showerror('结构操作未完成',str(exc),parent=self.window)

    def refresh_draft(self):
        self.draft.configure(state='normal')
        self.draft.delete(0,'end')
        for i,item in enumerate(self.themes): self.draft.insert('end',f'{i+1}. {item["name"]} · {item["bars"]} 小节')
        if self.doc:self.draft.configure(state='disabled')

    def move(self, delta):
        if self.doc is not None: return
        selection=self.draft.curselection()
        if not selection: return
        i=selection[0]; j=i+delta
        if 0<=j<len(self.themes):
            self.themes[i],self.themes[j]=self.themes[j],self.themes[i]
            self.refresh_draft(); self.draft.selection_set(j)

    def lock(self):
        if self.doc is not None: raise ValueError('骨架已经固定。')
        if not self.themes: raise ValueError('请先在素材池中导入原主题，再打开结构窗口。也可以打开已有结构工程。')
        if not messagebox.askyesno('确认主题顺序','固定为：'+' → '.join(i['name'] for i in self.themes)+'\n这是你的结构选择，不是程序判断的音乐顺序。',parent=self.window): return
        self.doc=engine.create(self.pool,[i['id'] for i in self.themes]); self.dirty=True; self.render()

    def sid(self):
        if not self.doc or self.slot.current()<0: raise ValueError('请先确认骨架并选择位置。')
        return self.doc['backbone'][self.slot.current()]['id']

    def apply(self, operation, **args):
        result=engine.edit(self.doc,operation,**args)
        self.undo_stack.append(self.doc); self.doc=result; self.dirty=True; self.render()

    def render(self):
        engine.validate(self.doc)
        for button in (self.up,self.down,self.confirm): button.configure(state='disabled')
        items={i['id']:i for i in self.doc['pool']['items']}
        self.themes=[items[s['theme_id']] for s in self.doc['backbone']]; self.refresh_draft()
        self.draft.configure(state='disabled')
        selected=self.slot.current()
        self.slot.configure(values=[f'{i+1}. {items[s["theme_id"]]["name"]}' for i,s in enumerate(self.doc['backbone'])])
        self.slot.current(max(0,min(selected,len(self.doc['backbone'])-1)))
        self.route.delete(*self.route.get_children())
        rows=engine.timeline(self.doc)
        slots={s['id']:s for s in self.doc['backbone']}
        for row in rows['rows']:
            role=slots[row['slot_id']]['role'] if row['kind']=='slot' else '关联回答 / 插入'
            self.route.insert('', 'end', iid=row['id'], text=row['name'], values=(role,f'{row["start_bar"]}–{row["start_bar"]+row["bars"]-1}',row['kind']))
        self.status.configure(text=' → '.join(r['name'] for r in rows['rows'])+f'\n{rows["bars"]} 小节 / {rows["seconds"]:.1f} 秒（结构时长，无生成过渡）。原主题順序固定；结构通过不代表音乐衔接自然。')
        self.refresh_choices()

    def refresh_choices(self):
        if not self.doc:return
        sid=self.sid(); slot=next(s for s in self.doc['backbone'] if s['id']==sid)
        items={i['id']:i for i in self.doc['pool']['items']}
        self.replace_options=[it for it in items.values() if it['accepted'] and engine.family(items,it['id'])['id']==slot['theme_id']]
        self.answer_options=[it for it in items.values() if it['accepted'] and engine.family(items,it['id'])['kind']=='answer']
        self.replacement.configure(values=[i['name']+' · '+i['id'][:6] for i in self.replace_options])
        if self.replace_options:self.replacement.current(0)
        self.answer.configure(values=[i['name']+(' · 此处允许' if sid in self.doc['permissions'].get(i['id'],[]) else ' · 此处未授权')+' · '+i['id'][:6] for i in self.answer_options])
        if self.answer_options:self.answer.current(0)
        self.role.set(slot['role'])

    def replace(self):
        sid=self.sid()
        if self.replacement.current()<0:raise ValueError('没有可用的已保留变体。')
        self.apply('replace',slot_id=sid,material_id=self.replace_options[self.replacement.current()]['id'])

    def answer_id(self):
        self.sid()
        if self.answer.current()<0:raise ValueError('请先在素材池保留回答句，再重新打开结构窗口。')
        return self.answer_options[self.answer.current()]['id']

    def insert(self):self.apply('insert',slot_id=self.sid(),material_id=self.answer_id())

    def authorize(self):
        mid=self.answer_id(); sid=self.sid()
        if messagebox.askyesno('明确开放插入位置','允许所选关联素材用于此段之后？\n这只是你开放的结构权限，不代表系统已验证音乐相容性。',parent=self.window):
            self.apply('authorize',slot_id=sid,material_id=mid,confirmed=True)

    def remove(self):
        selection=self.route.selection()
        if not selection: raise ValueError('请在当前展开列表选中要移除的插入项。')
        self.apply('remove_insert',entry_id=selection[0])

    def undo(self):
        if not self.undo_stack:raise ValueError('没有可撤销的结构编辑。')
        self.doc=self.undo_stack.pop(); self.dirty=True; self.render()

    def save(self):
        if not self.doc:raise ValueError('请先确认骨架。')
        path=engine.save(self.doc); self.dirty=False; self.status.configure(text='已另存结构快照（含素材副本）：'+str(path)); return path

    def preserve(self):
        for child in self.flow_windows:
            if child.window.winfo_exists() and not child.preserve():return False
        if not self.dirty:return True
        answer=messagebox.askyesnocancel('保存结构','是否保存当前结构快照？',parent=self.window)
        if answer is None:return False
        if answer and self.guard(self.save) is None:return False
        return True

    def open(self):
        path=filedialog.askopenfilename(parent=self.window,initialdir=str(engine.ROOT/'structures'),filetypes=[('结构工程','*.json')])
        if path and self.preserve():
            doc=engine.load(path)
            self.doc=doc; self.pool=copy.deepcopy(doc['pool']); self.undo_stack=[]; self.dirty=False
            self.draft.configure(state='normal'); self.render()

    def close(self):
        if self.preserve():
            for child in self.flow_windows:
                if child.window.winfo_exists():child.dispose()
            self.window.destroy()

    def open_flow(self):
        if not self.doc:raise ValueError('请先确认主题骨架。')
        from flow_ui import FlowWindow
        child=FlowWindow(self.window,self.doc);self.flow_windows.append(child);return child
