"""Windows Explorer file drops, without a second window or external dependency."""
import ctypes
from ctypes import wintypes
import os


class FileDrop:
    def __init__(self,root,callback):
        self.root=root;self.callback=callback;self.closed=False
        if os.name!='nt':raise OSError('文件拖入目前仅支持 Windows。')
        root.update_idletasks()
        self.user=ctypes.WinDLL('user32',use_last_error=True);self.shell=ctypes.WinDLL('shell32')
        self.user.GetParent.argtypes=[wintypes.HWND];self.user.GetParent.restype=wintypes.HWND
        self.hwnd=self.user.GetParent(root.winfo_id()) or root.winfo_id()
        self.proc_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
        self.setter=getattr(self.user,'SetWindowLongPtrW',self.user.SetWindowLongW)
        self.setter.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_void_p];self.setter.restype=ctypes.c_void_p
        self.user.CallWindowProcW.argtypes=[ctypes.c_void_p,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.user.CallWindowProcW.restype=ctypes.c_ssize_t
        self.shell.DragAcceptFiles.argtypes=[wintypes.HWND,wintypes.BOOL]
        self.shell.DragQueryFileW.argtypes=[wintypes.HANDLE,wintypes.UINT,wintypes.LPWSTR,wintypes.UINT]
        self.shell.DragFinish.argtypes=[wintypes.HANDLE]
        self.proc=self.proc_type(self.dispatch)
        self.old=self.setter(self.hwnd,-4,ctypes.cast(self.proc,ctypes.c_void_p))
        if not self.old:raise ctypes.WinError(ctypes.get_last_error())
        self.shell.DragAcceptFiles(self.hwnd,True)
        root.bind('<Destroy>',self.destroy,add='+')

    def dispatch(self,hwnd,message,wparam,lparam):
        if message==0x233:
            paths=[]
            try:
                count=self.shell.DragQueryFileW(wparam,0xffffffff,None,0)
                for i in range(count):
                    length=self.shell.DragQueryFileW(wparam,i,None,0)
                    buffer=ctypes.create_unicode_buffer(length+1)
                    self.shell.DragQueryFileW(wparam,i,buffer,length+1);paths.append(buffer.value)
            finally:self.shell.DragFinish(wparam)
            try:self.root.after(0,lambda:None if self.closed else self.callback(paths))
            except Exception:pass
            return 0
        return self.user.CallWindowProcW(self.old,hwnd,message,wparam,lparam)

    def destroy(self,event):
        if event.widget==self.root:self.close()

    def close(self):
        if not self.closed:
            self.closed=True
            self.shell.DragAcceptFiles(self.hwnd,False)
            self.setter(self.hwnd,-4,self.old)
