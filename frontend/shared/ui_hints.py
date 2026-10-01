from ui_scale import font as scaled_font
from ui_theme import color as theme_color
"""Small Tk-only tooltips, compatible with the portable runtime."""
import tkinter as tk


class Tooltip:
    def __init__(self, widget, text):
        self.widget=widget;self.text=text;self.timer=None;self.popup=None;self.value=None
        widget.bind('<Enter>',self.schedule,add='+')
        widget.bind('<Motion>',self.schedule,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')

    def schedule(self,event):
        value=self.text(event) if callable(self.text) else self.text
        if value==self.value and (self.timer or self.popup):return
        self.hide();self.value=value
        if value:
            self.x=event.x_root;self.y=event.y_root
            self.timer=self.widget.after(500,self.show)

    def show(self):
        self.timer=None
        if not self.widget.winfo_exists() or not self.value:return
        self.popup=tk.Toplevel(self.widget);self.popup.withdraw();self.popup.overrideredirect(True)
        tk.Label(self.popup,text=self.value,bg=theme_color('#263746'),fg=theme_color('#edf2f7'),justify='left',
                 padx=12,pady=8,wraplength=320,relief='solid',borderwidth=1,
                 font=scaled_font(('Microsoft YaHei UI',10))).pack()
        self.popup.update_idletasks()
        x=max(0,min(self.x+12,self.popup.winfo_screenwidth()-self.popup.winfo_reqwidth()-12))
        y=max(0,min(self.y+20,self.popup.winfo_screenheight()-self.popup.winfo_reqheight()-12))
        self.popup.geometry(f'+{x}+{y}');self.popup.deiconify()

    def hide(self,event=None):
        if self.timer:
            self.widget.after_cancel(self.timer);self.timer=None
        if self.popup:
            self.popup.destroy();self.popup=None
        self.value=None


def rounded(canvas,x1,y1,x2,y2,fill,outline='',width=1,tags=(),radius=9):
    radius=min(radius,(x2-x1)/4,(y2-y1)/4)
    return canvas.create_polygon(x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,
        x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,
        x1,y1+radius,x1,y1,smooth=True,splinesteps=16,fill=fill,outline=outline,width=width,tags=tags)
