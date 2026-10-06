from ui_theme import color as theme_color
"""Contextual edits that do not need permanent toolbar buttons."""
import copy
import tkinter as tk
from tkinter import ttk
import block_editor
import emotion_input
import story_engine as engine


class BlockActions:
    def remove_emotion_region(self,index):
        if self.commit(emotion_input.remove_region(self.snapshot(),index),'移除情绪段'):
            self.host.tell('情绪段已移除，邻段填补原时间 · '+self.undo_hint())

    def clear_local_changes(self,start,end):
        if self.commit(block_editor.clear_overrides(self.snapshot(),start,end),'清除局部修改'):
            self.host.tell('已恢复此处的自动编排 · '+self.undo_hint())

    def set_region_source(self,index,source_id):
        project=self.snapshot();project['curve'][index]['source_id']=source_id
        if self.commit(project,'设置旋律来源'):self.host.tell('此情绪段旋律来源已更新 · '+self.undo_hint())

    def context_click(self,event):
        if self.host.busy or self.drag:return
        if 111<=event.y<=214:return
        previous=getattr(self,'context_menu',None)
        if previous is not None and previous.winfo_exists():previous.destroy()
        x=self.line.canvasx(event.x);menu=tk.Menu(self.line,tearoff=False)
        self.context_menu=menu
        if 30<=event.y<=108:
            index=next((i for i,a,b in self.regions if a<=x<=b),None)
            if index is None:menu.destroy();return
            region=self.project['curve'][index]
            menu.add_command(label='移除此情绪段',command=lambda:self.host.safe(lambda:self.remove_emotion_region(index)))
            sources=tk.Menu(menu,tearoff=False)
            sources.add_command(label='自动选择',command=lambda:self.host.safe(lambda:self.set_region_source(index,None)))
            for i,source in enumerate(self.project['sources']):
                sources.add_command(label=f'M{i+1} · '+source['name'],
                    command=lambda sid=source['id']:self.host.safe(lambda:self.set_region_source(index,sid)))
            menu.add_cascade(label='此情绪段旋律来源',menu=sources)
            self._clear_menu(menu,region['start'],region['end'])
        elif 244<=event.y<=305 and self.planned:
            ident=next((ident for a,b,ident in self.origin_boxes if a<=x<=b),None)
            if ident is None:menu.destroy();return
            block=next(b for b in self.planned['blocks'] if b['id']==ident)
            self.blocks.selection_set(ident);self.draw()
            if not block['pinned']:
                self._clear_menu(menu,block['start_seconds'],block['end_seconds'])
                if menu.index('end') is None:
                    menu.add_command(label='旋律来源：在上方情绪积木右键设置',state='disabled')
            else:
                menu.add_command(label='自动记忆点：随强度最高点移动',state='disabled')
        else:menu.destroy();return
        self.line_hint.hide()
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def _clear_menu(self,menu,start,end):
        if any(v['start']<end and v['end']>start for v in self.project['overrides']):
            menu.add_command(label='清除此处局部修改',command=lambda:self.host.safe(lambda:self.clear_local_changes(start,end)))
