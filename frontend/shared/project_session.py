"""Snapshot persistence and guarded project switching; all methods run on the Tk thread."""
import copy
from datetime import datetime
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import studio_model as model
import story_ui
import ui_platform


class ProjectSession:
    @property
    def dirty(self):
        if not getattr(self,'persistence_ready',False):return getattr(self,'_dirty_hint',False)
        try:return self.project_signature()!=self.saved_signature
        except (ValueError,TypeError,tk.TclError):return True

    @dirty.setter
    def dirty(self,value):
        # Legacy edit sites only request a display refresh; persisted content decides dirty.
        self._dirty_hint=value;self.save_status_pending=True

    def project_payload(self):
        settings=dict(connections=self.connections.get(),seed=self.seed.get(),source_path=self.source_path,
                      track=self.track_var.get(),start_bar=self.start_bar.get(),bars=self.bars.get(),
                      policy=self.policy.get(),trim=self.trim.get(),key=self.key.get(),input_themes=self.input_themes,
                      story=self.story_page.snapshot())
        return copy.deepcopy(dict(schema=model.SCHEMA,pool=self.pool,doc=self.doc,curve=self.curve,results=self.results,settings=settings))

    def project_signature(self):
        return json.dumps(self.project_payload(),sort_keys=True,ensure_ascii=False,separators=(',',':'))

    def init_persistence(self):
        self.saved_path=None;self.saved_time='';self.save_error='';self.switching_project=False
        self.recent_snapshot_path=None;self.recent_snapshot_time=''
        self.saved_signature=self.project_signature();self.persistence_ready=True;self.update_save_status()

    def update_save_status(self):
        if not getattr(self,'persistence_ready',False) or self.switching_project:return
        text='工程未保存' if self.dirty else ('工程已保存' if self.saved_path else '新工程 · 尚未保存')
        if self.save_error:text+=' · 保存失败'
        self.save_status_label.configure(text=text);self.save_status_pending=False
        self.save_location_button.state(['!disabled'] if self.saved_path or self.recent_snapshot_path else ['disabled'])

    def save_location_text(self):
        path=getattr(self,'saved_path',None) or getattr(self,'recent_snapshot_path',None)
        if not path:return '保存工程快照包含素材与编辑；导出音频是另一项操作。'
        label='当前工程快照' if self.saved_path else '前一工程的最近快照（当前新工程尚未保存）'
        stamp=self.saved_time if self.saved_path else self.recent_snapshot_time
        return f'{label}：{path.name}\n文件时间：{stamp}\n完整路径：{path}\n每次保存创建新快照，不覆盖旧文件。'

    @staticmethod
    def shorten_path(path,limit=65):
        text=str(path)
        return text if len(text)<=limit else text[:18]+'…'+text[-(limit-19):]

    def show_save_location(self):
        if not (self.saved_path or self.recent_snapshot_path):return
        window=tk.Toplevel(self.root);window.title('工程快照位置');window.transient(self.root)
        box=tk.Text(window,width=65,height=6,wrap='word');box.pack(fill='both',expand=True,padx=12,pady=12)
        box.insert('1.0',self.save_location_text());box.configure(state='disabled')
        ttk.Button(window,text='打开所在文件夹',command=self.open_saved_folder).pack(pady=(0,12))

    def open_saved_folder(self):
        path=self.saved_path or self.recent_snapshot_path
        if not path:return
        try:ui_platform.open_folder(path.parent)
        except Exception as exc:self.tell('无法打开文件夹，请从“位置”复制完整路径手动打开：'+str(exc),True)

    def save_project(self):
        if self.busy:raise ValueError('任务进行中，请结束后再保存工程快照。')
        try:
            data=self.project_payload()
            path=model.save_project(data['pool'],data['doc'],data['curve'],data['results'],data['settings'])
        except Exception as exc:
            self.save_error=str(exc);self.update_save_status()
            raise ValueError('快照保存失败，当前编辑已保留。请检查保存目录权限和磁盘空间后重试。详情：'+str(exc)) from exc
        self.saved_path=Path(path).resolve();self.saved_time=datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
        self.recent_snapshot_path=self.saved_path;self.recent_snapshot_time=self.saved_time
        self.saved_signature=json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        self.save_error='';self.update_save_status()
        self.tell(f'快照已保存 · {self.shorten_path(self.saved_path.name,28)} · {self.saved_time[-8:]} · {self.shorten_path(self.saved_path.parent,32)}')
        self.notice_detail=self.save_location_text()
        return self.saved_path

    def prepare_project(self,data):
        data=copy.deepcopy(data);settings=data.get('settings',{})
        story=settings.get('story',story_ui.engine.new_project())
        story_ui.engine.validate(story,require_source=False)
        # Resolve optional raw input before touching the active editor. Snapshot notes remain usable.
        source=None;source_issue='';source_path=settings.get('source_path')
        if source_path:
            try:source=model.flow.music.load_source(source_path)
            except Exception:source_issue='原导入文件不可用；工程内素材快照仍可编辑和生成。'
        paths=[s.get('source',{}).get('path') for s in story['sources']]
        if any(path and not Path(path).is_file() for path in paths):source_issue='原导入文件缺失；工程内素材快照仍可编辑和生成。'
        return data,story,source,source_issue

    def checkpoint(self):
        app_names=('pool','doc','curve','results','input_themes','source','source_path','undo_stack','preview_cache',
                   'play_blocks','play_duration','play_position','playing_path','segment_end','segment_label',
                   'transport_running','seek_drag','waveform_values','waveform_stamp','audition_blocks','audition_page','history_offset')
        page_names=('project','planned','history','paint_emotion','selected_region','source','path','source_audio',
                    'source_seek','source_error','source_block_playing','preview_status','generation_state','generation_stage',
                    'generation_started','generation_detail','assembly_selection','selected_material_id','material_audio')
        p=self.story_page
        return dict(app={k:copy.deepcopy(getattr(self,k)) for k in app_names if hasattr(self,k)},
                    page={k:copy.deepcopy(getattr(p,k)) for k in page_names if hasattr(p,k)},
                    variables=[(v,v.get()) for owner in (self,p) for v in vars(owner).values() if isinstance(v,tk.Variable)],
                    track_values=[box.cget('values') for box in self.track_boxes],
                    result_selection=self.result_list.curselection(),source_selection=p.sources.selection(),
                    mode=self.modes.select(),detail_tab=self.detail_tabs.select(),
                    generation_visible=bool(p.generation_panel.winfo_manager()),details_visible=bool(p.generation_details.winfo_manager()))

    def restore_checkpoint(self,state):
        p=self.story_page
        for key,value in state['app'].items():setattr(self,key,value)
        for key,value in state['page'].items():setattr(p,key,value)
        for var,value in state['variables']:var.set(value)
        for box,values in zip(self.track_boxes,state['track_values']):box.configure(values=values)
        # Rebuild from restored data; keep going if the failing presentation callback is still faulty.
        for action in (self.refresh_inputs,self.refresh,self.refresh_results,p.refresh):
            try:action()
            except Exception:pass
        if state['result_selection']:
            self.result_list.selection_clear(0,'end');self.result_list.selection_set(state['result_selection'][0])
            try:self.show_result()
            except Exception:pass
        selected=[sid for sid in state['source_selection'] if p.sources.exists(sid)]
        if selected:p.sources.selection_set(selected)
        self.modes.select(state['mode']);self.detail_tabs.select(state['detail_tab'])
        if state['generation_visible']:p.generation_panel.pack(fill='x',before=p.footer)
        else:p.generation_panel.pack_forget()
        if p.generation_state=='failed':
            p.generation_failed(p.generation_stage,p.generation_detail)
            p.set_generation_details(state['details_visible'])
        p.draw();p.update_generation_controls()

    def apply_project(self,data,story,source,source_issue):
        settings=data.get('settings',{});p=self.story_page
        self.input_themes=copy.deepcopy(settings.get('input_themes',[]))
        self.pool,self.doc,self.curve,self.results=data['pool'],data['doc'],data['curve'],data['results']
        self.undo_stack=[];self.preview_cache={};self.source=source;self.source_path=settings.get('source_path')
        defaults=dict(connections=True,seed='31',track='',start_bar='1',bars='8',policy='遇到同时起音时停止',trim=True,key='自动 / 沿用素材池')
        for var,key in ((self.connections,'connections'),(self.seed,'seed'),(self.track_var,'track'),(self.start_bar,'start_bar'),
                        (self.bars,'bars'),(self.policy,'policy'),(self.trim,'trim'),(self.key,'key')):
            var.set(settings.get(key,defaults[key]))
        names=[f'{i+1}. {t.name}' for i,t in enumerate(source.tracks)] if source else []
        for box in self.track_boxes:box.configure(values=names)
        self.source_text.set(source_issue or ('已恢复参考旋律。' if source else '工程内素材快照可继续编辑。'))
        self.count.set(str(len(self.curve)))
        self.refresh_inputs();self.refresh();self.refresh_results()
        p.restore(story)
        self.modes.select(p if story['sources'] else 1)
        if self.doc:self.detail_tabs.select(2)

    def switch_project(self,prepared,path=None):
        if self.busy:raise ValueError('任务进行中，请结束后再切换工程。')
        saved=False;autosave_detail=''
        if self.dirty:self.save_project();saved=True;autosave_detail=self.save_location_text()
        state=self.checkpoint();self.switching_project=True
        try:
            self.story_page.preview_planner.invalidate()
            self.apply_project(*prepared)
            signature=self.project_signature()
        except Exception as exc:
            self.restore_checkpoint(state)
            raise ValueError('工程恢复失败，当前项目和历史已保留：'+str(exc)) from exc
        finally:self.switching_project=False
        self.story_page.discard_combination_drafts();self.story_page.material_audio=None
        self.stop_playback();self.story_page.source_audio=None;self.story_page.source_seek=False
        self.last_job_error=''
        self.story_page.source_block_playing=None;self.story_page.cancel_drag()
        self.story_page.source_time.set('选择一张旋律卡片');self.play_blocks=[];self.draw_playback()
        self.saved_signature=signature;self.saved_path=Path(path).resolve() if path else None;self.save_error=''
        try:self.saved_time=datetime.fromtimestamp(self.saved_path.stat().st_mtime).astimezone().strftime('%Y-%m-%d %H:%M:%S') if path else ''
        except OSError:self.saved_time='时间不可用'
        if self.saved_path:
            self.recent_snapshot_path=self.saved_path;self.recent_snapshot_time=self.saved_time
        self.update_save_status();self.update_edit_status();self.update_result_controls()
        message=('工程已打开 · '+self.saved_path.name) if path else '新工程就绪。'
        if saved:message+=' 前一个工程已自动保存新快照。'
        if prepared[3]:message+=' '+prepared[3]
        self.tell(message)
        if saved:self.notice_detail='切换前自动保存：\n'+autosave_detail

    def load_project(self,path):
        if self.busy:raise ValueError('任务进行中，请结束后再打开工程。')
        prepared=self.prepare_project(model.load_project(path))
        self.switch_project(prepared,path)

    def open_project(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('EmoBlocks 工程','*.json')])
        if path:self.load_project(path)

    def new_project(self):
        if self.busy:raise ValueError('任务进行中，请结束后再新建工程。')
        data=dict(pool=model.materials.new_pool(),doc=None,results=[],settings={'story':story_ui.assembly.new_project(story_ui.default_melody.source())},
                  curve=[dict(emotion='calm',start=.2,end=.4),dict(emotion='suspense',start=.4,end=.55),
                         dict(emotion='crisis',start=.55,end=.9),dict(emotion='resolve',start=.7,end=.95)])
        self.switch_project(self.prepare_project(data))
        self.modes.select(self.story_page);self.name.set('A')
        self.set_info('新工程。保存快照保留工程素材与编辑；导出用于分享成品音频。')

    def close(self):
        if self.busy:self.tell('任务进行中，请结束后再关闭。',True);return
        try:
            if self.dirty:self.save_project()
        except Exception as exc:self.tell('自动保存失败，未关闭：'+str(exc),True);return
        self.story_page.preview_planner.close()
        if hasattr(self.story_page,'file_drop'):self.story_page.file_drop.close()
        self.stop_playback();self.root.after_cancel(self.timer);self.root.destroy()
