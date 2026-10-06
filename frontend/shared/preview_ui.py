from ui_scale import font as scaled_font
from combobox_selection import selected_index
"""Preview-matched navigation, saved-version cards and real audio waveform."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import wave
import numpy as np
from ui_theme import color
from ui_hints import rounded, Tooltip, BoundedLabel
from window_ui import IconButton
import ui_scale


def waveform(path,bins=48):
    """Read PCM in bounded chunks; displayed amplitudes come from the real WAV."""
    with wave.open(str(path),'rb') as audio:
        width=audio.getsampwidth();frames=audio.getnframes();result=[]
        if width not in (1,2,3,4):return []
        for i in range(bins):
            count=frames*(i+1)//bins-frames*i//bins
            data=audio.readframes(count)
            if not data:result.append(0.);continue
            if width==3:
                raw=np.frombuffer(data,dtype=np.uint8).reshape(-1,3).astype(np.int32)
                values=raw[:,0]|(raw[:,1]<<8)|(raw[:,2]<<16)
                values=np.where(values&0x800000,values-0x1000000,values).astype(float)
            else:
                values=np.frombuffer(data,dtype={1:'u1',2:'<i2',4:'<i4'}[width]).astype(float)
                if width==1:values-=128
            result.append(float(np.sqrt(np.mean(values*values)))/(2**(8*width-1)))
        return result


class Navigation(tk.Canvas):
    def __init__(self,parent,notebook):
        super().__init__(parent,height=36,highlightthickness=0,takefocus=True,cursor='hand2')
        self.notebook=notebook
        self.bind('<Configure>',lambda _:self.refresh_theme())
        self.bind('<Button-1>',self.pick)
        self.bind('<Left>',lambda _:self.select(0));self.bind('<Right>',lambda _:self.select(1))
        notebook.bind('<<NotebookTabChanged>>',lambda _:self.refresh_theme())
    def select(self,index):
        if len(self.notebook.tabs())>index:self.notebook.select(index)
    def pick(self,event):
        x=event.x/ui_scale.factor
        if x<196:self.select(0 if x<106 else 1)
    def refresh_theme(self):
        self.configure(bg=color('bg'));self.delete('all')
        current=self.notebook.index('current') if self.notebook.select() else 0
        self.create_line(0,35,max(1,self.winfo_width())/ui_scale.factor,35,fill=color('line'))
        for i,label in enumerate(('快速成品','精细创作')):
            x=12+i*104
            self.create_text(x,16,text=label,anchor='w',fill=color('ink') if current==i else color('muted'),font=scaled_font(('Microsoft YaHei UI',10)))
            if current==i:self.create_line(x,34,x+70,34,fill=color('accent'),width=2)
        self.scale('all',0,0,ui_scale.factor,ui_scale.factor)


class PreviewAudio:
    def build_preview_audio(self,rail):
        self.history_canvas=tk.Canvas(rail,height=104,bg=color('panel'),highlightthickness=0,takefocus=True)
        self.history_canvas.pack(fill='x',pady=(10,5))
        self.selected_version_label=BoundedLabel(rail,text='尚无成品版本',style='Muted.TLabel')
        self.selected_version_label.pack(fill='x',pady=(0,4))
        self.history_canvas.bind('<Configure>',lambda _:self.draw_history())
        self.history_offset=0.;self.history_scroll_timer=None;self.history_scroll_visible=False;self.history_drag=None
        self.history_canvas.bind('<Button-1>',self.choose_history)
        self.history_canvas.bind('<MouseWheel>',self.scroll_history)
        if self.history_canvas.tk.call('info','commands','tk::PreciseScrollDeltas'):
            self.history_canvas.bind('<TouchpadScroll>',self.scroll_history_touchpad)
        self.history_canvas.bind('<B1-Motion>',self.drag_history)
        self.history_canvas.bind('<ButtonRelease-1>',self.release_history_scroll)
        self.history_canvas.bind('<Destroy>',self.destroy_history_scroll)

        import ui_platform
        for event in ui_platform.CONTEXT_EVENTS:self.history_canvas.bind(event,self.history_menu)
        self.history_canvas.bind('<Up>',lambda _:self.move_history(1))
        self.history_canvas.bind('<Down>',lambda _:self.move_history(-1))
        self.history_canvas.bind('<Return>',lambda _:self.safe(self.toggle_result_play))
        Tooltip(self.history_canvas,'滚轮浏览全部版本；点击选择，右键查看历史菜单。')
        self.play_canvas=tk.Canvas(rail,height=64,bg=color('panel'),highlightthickness=0,cursor='hand2',takefocus=True)
        self.play_canvas.pack(fill='x',pady=(4,8))
        self.play_canvas.bind('<Configure>',lambda _:self.draw_playback())
        for event,phase in (('<ButtonPress-1>','start'),('<B1-Motion>','move'),('<ButtonRelease-1>','end')):
            self.play_canvas.bind(event,lambda e,p=phase:self.safe(lambda:self.seek_to_pointer(e.x,p,self.play_canvas.winfo_width())))
        Tooltip(self.play_canvas,lambda _:self.play_label.cget('text')+'\n点击或拖动波形定位；空格播放 / 暂停。')
        row=ttk.Frame(rail);row.pack(fill='x',pady=(2,8))
        self.result_transport_buttons=[]
        row.columnconfigure(0,weight=1);row.columnconfigure(4,weight=1)
        for column,label,command in ((1,'previous',lambda:self.step_result_block(-1)),(2,'play',self.toggle_result_play),(3,'next',lambda:self.step_result_block(1))):
            button=IconButton(row,label,lambda fn=command:self.safe(fn),size=40,surface='panel',primary=column==2)
            button.grid(row=0,column=column,padx=7)
            self.result_transport_buttons.append(button)
            if column==2:self.transport_play=button
            Tooltip(button,'播放 / 暂停' if column==2 else '上一块' if column==1 else '下一块')
        self.stop_button=ttk.Button(row,text='■ 停止',width=6,command=self.stop_playback)
        self.stop_button.available_while_busy=True
        self.stop_button.grid(row=0,column=4,sticky='e')
        self.audition_tiles=tk.Canvas(rail,height=104,bg=color('panel'),highlightthickness=0,takefocus=True,cursor='hand2')
        self.audition_tiles.pack(fill='x',pady=(4,6))
        self.audition_page=0;self.audition_boxes=[]
        self.audition_tiles.bind('<Configure>',lambda _:self.draw_result_tiles())
        self.audition_tiles.bind('<Button-1>',self.pick_result_tile)
        self.audition_tiles.bind('<Left>',lambda _:self.safe(lambda:self.step_result_block(-1)))
        self.audition_tiles.bind('<Right>',lambda _:self.safe(lambda:self.step_result_block(1)))
        self.audition_tiles.bind('<Return>',lambda _:self.safe(self.play_result_block))
        Tooltip(self.audition_tiles,self.result_tile_hint)
        self.play_canvas.bind('<space>',lambda _:self.safe(self.toggle_result_play))

    def history_extent(self):
        height=self.history_canvas.winfo_height()/ui_scale.factor
        if height<=1:height=float(self.history_canvas.cget('height'))/ui_scale.factor
        content=max(0,len(self.results)*49-3)
        return height,content,max(0,content-height)

    def draw_history(self):
        if not hasattr(self,'history_canvas'):return
        c=self.history_canvas;c.delete('all');c.configure(bg=color('panel'));w=max(200,c.winfo_width())
        ids=self.result_list.curselection();selected=ids[0] if ids else None
        self.history_rows=[]
        viewport,content,maximum=self.history_extent()
        self.history_offset=max(0,min(self.history_offset,maximum))
        self.history_thumb=None
        if not self.results:
            rounded(c,1,1,w-1,viewport-1,color('inset'),color('line'),radius=14)
            c.create_text(w/2,viewport/2-10,text='尚无成品版本',fill=color('muted'),font=scaled_font(('Microsoft YaHei UI',10)))
            c.create_text(w/2,viewport/2+13,text='生成后在此试听',fill=color('muted'),font=scaled_font(('Microsoft YaHei UI',9)))
            c.scale('all',0,0,1,ui_scale.factor);return
        self.history_offset=max(0,min(self.history_offset,maximum))
        indexes=list(reversed(range(len(self.results))))
        for slot,index in enumerate(indexes):
            r=self.results[index];y=slot*49-self.history_offset;active=index==selected
            if y+46<0 or y>=viewport:continue
            rounded(c,1,y+1,w-1,y+46,color('inset'),color('accent') if active else color('line'),radius=12)
            c.create_text(18,y+25,text=f'{index+1:02}',fill=color('muted'),font=scaled_font(('Segoe UI',10)))
            available=(Path(r['report']['output_directory'])/'preview.wav').is_file()
            c.create_text(40,y+17,text=r['mode']+('' if available else ' · 音频不可用'),anchor='w',fill=color('ink'),font=scaled_font(('Microsoft YaHei UI',10)))
            seconds=r['report']['duration_seconds']
            stamp=r.get('generated_at','')[:16].replace('T',' ') or '时间未记录'
            c.create_text(40,y+33,text=f'{seconds:g} 秒 · {stamp}',anchor='w',fill=color('muted'),font=scaled_font(('Microsoft YaHei UI',8)))
            if active:c.create_text(w-17,y+25,text='✓',fill=color('accent'),font=scaled_font(('Segoe UI',12)))
            self.history_rows.append((y,y+46,index))
        c.scale('all',0,0,1,ui_scale.factor)
        if maximum and self.history_scroll_visible:
            height=viewport*ui_scale.factor;thumb=min(height,max(18*ui_scale.factor,height*viewport/content))
            top=(height-thumb)*self.history_offset/maximum
            self.history_thumb=(top,thumb,height)
            c.create_line(w-4,top+3,w-4,top+thumb-3,fill=color('muted'),width=5,capstyle='round',tags='history-scrollbar')

    def reveal_history_scroll(self):
        if self.history_scroll_timer:self.history_canvas.after_cancel(self.history_scroll_timer)
        self.history_scroll_visible=self.history_extent()[2]>0
        self.history_scroll_timer=self.history_canvas.after(900,self.hide_history_scroll)
        self.draw_history()

    def hide_history_scroll(self):
        self.history_scroll_timer=None
        if self.history_drag is not None:
            self.history_scroll_timer=self.history_canvas.after(900,self.hide_history_scroll);return
        self.history_scroll_visible=False;self.draw_history()

    def destroy_history_scroll(self,event):
        if event.widget is self.history_canvas and self.history_scroll_timer:
            self.history_canvas.after_cancel(self.history_scroll_timer);self.history_scroll_timer=None

    def scroll_history(self,event):
        import ui_platform
        self.history_offset=max(0,min(self.history_extent()[2],self.history_offset+ui_platform.wheel_units(event.delta)*49))
        self.reveal_history_scroll();return 'break'

    def scroll_history_touchpad(self,event):
        from scroll_input import touchpad_deltas
        _,dy=touchpad_deltas(event)
        self.history_offset=max(0,min(self.history_extent()[2],self.history_offset-dy/ui_scale.factor))
        self.reveal_history_scroll();return 'break'

    def drag_history(self,event):
        if self.history_drag is None:return
        origin,offset=self.history_drag
        if not self.history_thumb:return
        _,thumb,height=self.history_thumb
        self.history_offset=max(0,min(self.history_extent()[2],offset+(event.y-origin)/max(1,height-thumb)*self.history_extent()[2]))
        self.reveal_history_scroll();return 'break'

    def release_history_scroll(self,event):
        if self.history_drag is not None:
            self.history_drag=None;self.reveal_history_scroll()

    def choose_history(self,event):
        self.history_canvas.focus_set()
        if self.history_extent()[2]>0 and getattr(event,'x',0)>=max(200,self.history_canvas.winfo_width())-10:
            self.reveal_history_scroll()
            top,thumb,height=self.history_thumb
            if not top<=event.y<=top+thumb:
                self.history_offset=max(0,min(self.history_extent()[2],(event.y-thumb/2)/max(1,height-thumb)*self.history_extent()[2]))
                self.draw_history()
            self.history_drag=(event.y,self.history_offset);return
        if not 0<=event.y<self.history_extent()[0]*ui_scale.factor:return
        for start,end,index in self.history_rows:
            if start<=event.y/ui_scale.factor<=end:self.select_history(index);return

    def select_history(self,index):
        top=(len(self.results)-1-index)*49
        if top<self.history_offset:self.history_offset=top
        elif top+46>self.history_offset+self.history_extent()[0]:self.history_offset=top+46-self.history_extent()[0]
        self.result_list.selection_clear(0,'end');self.result_list.selection_set(index);self.show_result()

    def move_history(self,delta):
        if not self.results:return
        selected=self.result_list.curselection()
        self.select_history(max(0,min(len(self.results)-1,(selected[0] if selected else 0)+delta)))

    def history_menu(self,event):
        menu=tk.Menu(self.root,tearoff=False)
        for i,r in reversed(list(enumerate(self.results))):
            menu.add_command(label=f'{i+1:02} · {r["mode"]} · {r["report"]["duration_seconds"]:g} 秒',command=lambda index=i:self.select_history(index))
        if self.results:
            try:menu.tk_popup(event.x_root,event.y_root)
            finally:menu.grab_release()

    def load_waveform(self,report):
        path=Path(report['output_directory'])/'preview.wav'
        self.load_waveform_path(path)

    def load_waveform_path(self,path):
        path=Path(path)
        try:
            stamp=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
            if getattr(self,'waveform_stamp',None)!=stamp:
                self.waveform_values=waveform(path);self.waveform_stamp=stamp
        except (OSError,wave.Error,ValueError):self.waveform_values=[];self.waveform_stamp=None

    def draw_playback(self):
        if not hasattr(self,'play_canvas'):return
        c=self.play_canvas;c.delete('all');c.configure(bg=color('panel'));w=max(100,c.winfo_width())
        visible=max(40,c.winfo_height()/ui_scale.factor)
        center=(visible-20)/2
        values=getattr(self,'waveform_values',[]);maximum=max(values,default=0) or 1
        fraction=self.play_position/max(.001,self.play_duration)
        for i,value in enumerate(values or [0]*40):
            count=len(values) if values else 40;x=8+(w-16)*(i+.5)/count
            height=max(2,min(36,visible-24)*(value/maximum)**.65)
            c.create_line(x,center-height/2,x,center+height/2,fill=color('accent') if values and i/count<fraction else color('line'),width=3,capstyle='round')
        def clock(seconds):return f'{int(seconds)//60:02}:{int(seconds)%60:02}'
        c.create_text(8,visible-8,text=clock(self.play_position),anchor='w',fill=color('muted'),font=scaled_font(('Consolas',9)))
        c.create_text(w-8,visible-8,text=clock(self.play_duration),anchor='e',fill=color('muted'),font=scaled_font(('Consolas',9)))
        c.scale('all',0,0,1,ui_scale.factor)
        if hasattr(self,'transport_play'):
            self.transport_play.icon='pause' if getattr(self,'transport_running',False) else 'play'
            self.transport_play.refresh_theme()
        self.draw_result_tiles()

    def toggle_result_play(self):
        # The transport controls the active device, including source auditions.
        # Requiring a generated report here prevented pausing source playback.
        if self.playing_path and self.player.opened:
            _,mode=self.player.status()
            if mode=='playing':self.player.pause();self.transport_running=False
            elif mode=='paused':self.player.resume();self.transport_running=True
            else:self.play()
            self.draw_playback()
            self.update_play_origin()
            if hasattr(self,'story_page'):self.story_page.sync_source_player()
        else:self.play()

    def draw_result_tiles(self):
        if not hasattr(self,'audition_tiles'):return
        from story_ui import COLORS
        c=self.audition_tiles;c.delete('all');c.configure(bg=color('panel'));w=max(180,c.winfo_width())
        blocks=getattr(self,'audition_blocks',[]);columns=max(3,int(w//(42*ui_scale.factor)))
        visible=c.winfo_height()/ui_scale.factor
        rows=max(1,min(2,int((visible-27+6)//35)));capacity=columns*rows
        from studio_model import active_block
        current=None
        try:
            if self.playing_path and self.playing_path==self.selected_report()['output_directory']:
                current=active_block(blocks,self.play_position)
        except (ValueError,KeyError):pass
        if current is not None and current!=getattr(self,'visible_playback_block',None):
            self.audition_page=current//capacity
        self.visible_playback_block=current
        pages=max(1,(len(blocks)+capacity-1)//capacity);self.audition_page=min(self.audition_page,pages-1)
        heading=f'第 {current+1} / {len(blocks)} 块' if current is not None else '成品分块'
        c.create_text(2,10,text=heading,anchor='w',fill=color('accent') if current is not None else color('muted'),font=scaled_font(('Microsoft YaHei UI',9)))
        if pages>1:c.create_text(w-4,10,text=f'‹  {self.audition_page+1}/{pages}  ›',anchor='e',fill=color('ink'),font=scaled_font(('Segoe UI',10)))
        self.audition_boxes=[]
        if not blocks:
            c.create_text(w/2,min(42,visible-10),text='生成后点击分块试听',fill=color('muted'),font=scaled_font(('Microsoft YaHei UI',9)));c.scale('all',0,0,1,ui_scale.factor);return
        selected=selected_index(self.result_block);tile=(w-2)/columns
        for slot,index in enumerate(range(self.audition_page*capacity,min(len(blocks),(self.audition_page+1)*capacity))):
            b=blocks[index];x=slot%columns*tile+2;y=27+slot//columns*35;active=index==selected
            shade=COLORS.get(b.get('emotion'),color('line'))
            rounded(c,x,y,x+tile-5,y+29,color('selected') if active else color('inset'),shade,3 if active else 1.5,radius=6)
            if index==current:
                rounded(c,x+2,y+2,x+tile-7,y+27,color('selected'),color('accent'),2,radius=4)
                c.create_line(x+6,y+25,x+tile-11,y+25,fill=color('accent'),width=3,tags='playing-block')
            c.create_text(x+(tile-5)/2,y+14,text=str(index+1),fill=color('ink') if active else color('muted'),font=scaled_font(('Segoe UI',9)))
            self.audition_boxes.append((x,y,x+tile-5,y+29,index))
        c.scale('all',0,0,1,ui_scale.factor)

    def pick_result_tile(self,event):
        self.audition_tiles.focus_set()
        y_event=event.y/ui_scale.factor
        if y_event<23 and event.x>self.audition_tiles.winfo_width()-90:
            self.audition_page=max(0,self.audition_page+(-1 if event.x<self.audition_tiles.winfo_width()-45 else 1));self.draw_result_tiles();return
        for x,y,right,bottom,index in self.audition_boxes:
            if x<=event.x<=right and y<=y_event<=bottom:
                self.result_block.current(index);self.safe(self.play_result_block);self.draw_result_tiles();return

    def result_tile_hint(self,event):
        for x,y,right,bottom,index in self.audition_boxes:
            if x<=event.x<=right and y<=event.y/ui_scale.factor<=bottom:
                b=self.audition_blocks[index]
                return f'第 {index+1} 块 · {b["start_seconds"]:.2f}–{b["end_seconds"]:.2f} 秒\n{b["name"]}\n点击试听此块'
        return '点击色框分块试听；左右键切换分块。'

    def step_result_block(self,delta):
        values=self.result_block.cget('values')
        if not values:raise ValueError('请先生成或选择成品。')
        index=max(0,min(len(values)-1,selected_index(self.result_block)+delta))
        columns=max(3,int(max(180,self.audition_tiles.winfo_width())//(42*ui_scale.factor)))
        self.audition_page=index//(columns*2)
        self.result_block.current(index);self.play_result_block()
