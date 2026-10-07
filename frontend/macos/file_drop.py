"""Finder drops through TkDND, using the shared import callback."""
import tkinter as tk


class FileDrop:
    def __init__(self,root,callback):
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError as exc:raise OSError('安装 requirements-macos.txt 以启用 Finder 拖入。') from exc
        if not hasattr(root,'drop_target_register'):raise OSError('请使用 run.py 创建支持 Finder 拖入的窗口。')
        self.root=root;self.callback=callback;self.closed=False
        root.drop_target_register(DND_FILES)
        self.binding=root.dnd_bind('<<Drop>>',self.drop)
    def drop(self,event):
        if self.closed:return 'refuse_drop'
        self.callback(list(self.root.tk.splitlist(event.data)))
        return 'copy'
    def close(self):
        if not self.closed:
            self.closed=True
            self.root.unbind('<<Drop>>',self.binding)
            try:
                self.root.drop_target_unregister()
            except tk.TclError as exc:
                # TkDND 2.9.5's Aqua unregister branch is explicitly unimplemented.
                # Remove its remaining logical target binding before root destruction.
                if str(exc)!='todo' or self.root.tk.call('tk','windowingsystem')!='aqua':raise
                self.root.unbind('<<DropTargetTypes>>')
