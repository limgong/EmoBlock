"""Shared window gestures with platform-owned taskbar and work-area access."""
import tkinter as tk
import ui_platform
from curve_icons import IconButton
from file_drop import FileDrop


class WindowChrome:
    def __init__(self,app,header):
        self.app=app;self.root=app.root;self.buttons=[];self.maximized=False
        self.saved_geometry=None;self.drag=None
        self.restore_drop=False
        if ui_platform.NATIVE_CHROME:return
        self.root.overrideredirect(True)
        for icon,label,command in [('cancel','关闭',app.close),('maximize','最大化 / 还原',self.toggle_maximize),('minus','最小化',self.minimize)]:
            button=IconButton(header,app,icon,label,command,style='Curve.Header.TButton')
            button.pack(side='right',padx=2);self.buttons.append(button)
        header.bind('<ButtonPress-1>',self.start_drag)
        header.bind('<B1-Motion>',self.move)
        header.bind('<Double-Button-1>',lambda _:self.toggle_maximize())
        self.root.bind('<Map>',self.mapped,add='+')
        self.root.bind('<Alt-F4>',lambda _:app.close(),add='+')
        grip=tk.Frame(self.root,cursor='size_nw_se',bg=app.theme.colors['bg'])
        grip.place(relx=1,rely=1,anchor='se',width=8,height=8)
        grip.bind('<ButtonPress-1>',self.start_resize);grip.bind('<B1-Motion>',self.resize)
        self.root.after_idle(self.taskbar)

    def taskbar(self):
        if self.root.winfo_exists():ui_platform.taskbar(self.root)

    def mapped(self,event):
        if event.widget==self.root and self.root.state()=='normal':
            self.root.overrideredirect(True);self.taskbar()
            if self.restore_drop:
                self.restore_drop=False
                try:self.app.file_drop=FileDrop(self.root,self.app.drop_files)
                except (OSError,tk.TclError) as exc:
                    self.app.show_detail('可用“导入旋律”选择文件。文件拖入未启用：'+str(exc))

    def minimize(self):
        # Tk recreates the Windows wrapper when changing override_redirect.
        # Release the old native hook before that wrapper is destroyed.
        drop=getattr(self.app,'file_drop',None)
        self.restore_drop=drop is not None
        if drop is not None:
            drop.close();self.app.file_drop=None
        self.root.overrideredirect(False);self.root.iconify()

    def toggle_maximize(self):
        if self.maximized:self.root.geometry(self.saved_geometry)
        else:
            self.saved_geometry=self.root.geometry()
            x,y,w,h=ui_platform.work_area(self.root)
            self.root.geometry(f'{w}x{h}+{x}+{y}')
        self.maximized=not self.maximized
        self.buttons[1].set_icon('restore' if self.maximized else 'maximize')

    def start_drag(self,event):self.drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())
    def move(self,event):
        if self.drag:
            if self.maximized:self.toggle_maximize();self.drag=(100,20)
            self.root.geometry(f'+{event.x_root-self.drag[0]}+{event.y_root-self.drag[1]}')
    def start_resize(self,event):self.origin=(event.x_root,event.y_root,self.root.winfo_width(),self.root.winfo_height())
    def resize(self,event):
        if self.maximized:return
        x,y,w,h=self.origin;mw,mh=self.root.minsize()
        self.root.geometry(f'{max(mw,w+event.x_root-x)}x{max(mh,h+event.y_root-y)}')
