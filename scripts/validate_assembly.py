"""Opt-in macOS/Windows real assembly render and programmatic Tk evidence in a temp folder.

Runs real LMMS and the installed audio adapter. Does not claim human listening quality.
Usage: .venv/bin/python scripts/validate_assembly.py [--output TEMP_DIRECTORY]
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from emoblocks_bootstrap import configure
configure()
import assembly
import default_melody
import story_engine
import studio_model
import ui_scale
from unified_ui import UnifiedApp

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path)
args=parser.parse_args()
folder=args.output or Path(tempfile.mkdtemp(prefix='emoblocks-assembly-'))
folder.mkdir(parents=True,exist_ok=True)
if any(folder.iterdir()):raise SystemExit('Evidence directory must be empty.')
story_engine.flow.structure.ROOT=folder
p=assembly.new_project(default_melody.source())
b=default_melody.source();b['id']='validation-B';b['name']='中文 English 第二旋律';b['notes']=[dict(n,pitch=min(127,n['pitch']+2)) for n in b['notes']]
p=assembly.add_source(p,b);A=p['library'][:3];B=next(m for m in p['library'] if m['name']=='B1')
p=assembly.save_combination(p,[A[1],B],'C');C=p['library'][-1]
for m in (A[0],C,A[2]):p=assembly.insert(p,m['id'])
p=assembly.paint(p,[1],'suspense');p=assembly.paint(p,[2],'resolve')
p['intensity_points']=[dict(time=0.,level=.2),dict(time=3.,level=.5),dict(time=6.5,level=.9),dict(time=8.,level=.3)]
root=tk.Tk();errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
app=UnifiedApp(root);page=app.story_page;page.restore(p)
evidence=dict(platform=platform.platform(),python=sys.version.split()[0],tk=str(root.tk.call('info','patchlevel')),folder=str(folder),gui='programmatic mapped Tk; no human visual/listening acceptance',layout=[])

def settle():
    deadline=time.monotonic()+300
    while app.busy:
        if time.monotonic()>deadline:raise TimeoutError('background job did not settle')
        root.update();time.sleep(.01)
    root.update()
    if app.last_job_error:raise RuntimeError(app.last_job_error)

try:
    for theme in ('light','dark'):
        app.set_theme(theme)
        for size in ('1020x700','1280x800','1440x900'):
            root.geometry(size);root.update();page.draw()
            boxes=copy.deepcopy(page.preview_boxes)
            widths=[box[3]-box[1] for box in boxes]
            assert len(boxes)==3 and abs(widths[1]/widths[0]-2)<1e-8 and abs(widths[2]/widths[0]-1)<1e-8
            bounds={}
            for name,widget in dict(generate=page.generate_button,play=app.transport_play,stop=app.stop_button,**app.export_buttons).items():
                bounds[name]=[widget.winfo_rootx()-root.winfo_rootx(),widget.winfo_rooty()-root.winfo_rooty(),widget.winfo_width(),widget.winfo_height()]
                assert widget.winfo_ismapped() and bounds[name][0]+bounds[name][2]<=root.winfo_width()
            evidence['layout'].append(dict(theme=theme,size=size,actual=[root.winfo_width(),root.winfo_height()],preview=boxes,controls=bounds))
    page.generate();page.generate();settle();assert len(app.results)==1
    assert page.generation_state=='success' and app.playing_path is None
    report=app.results[0]['report'];render=Path(report['output_directory']);plan=json.loads((render/'story-plan.json').read_text())
    assert [b['name'] for b in plan['assembly_blocks']]==['A1','C','A3']
    assert plan['total_ticks']==7680 and report['duration_seconds']==8
    assert [r['assembly_order'] for r in plan['blocks']]==sorted(r['assembly_order'] for r in plan['blocks'])
    assert all(r['use_id']==p['uses'][r['assembly_order']]['id'] for r in plan['blocks'])
    with wave.open(str(render/'preview.wav'),'rb') as w:evidence['audio']=dict(seconds=w.getnframes()/w.getframerate(),frames=w.getnframes(),rate=w.getframerate())
    evidence.update(render=str(render),total_ticks=plan['total_ticks'],names=[b['name'] for b in plan['assembly_blocks']],mapping=[dict(use_id=r['use_id'],order=r['assembly_order'],sources=r['assembly_sources'],kind=r['kind']) for r in plan['blocks']],report_audio=report['audio'])
    saved=app.save_project();before=app.project_payload();app.load_project(saved);assert app.project_payload()==before and not app.dirty
    assert app.story_page.snapshot()==p|{'melody_only':False}
    # Real native audio stream opens, pauses, resumes, and stops. Human perception is not evaluated.
    audio_checks=[]
    try:
        app.play();root.update();time.sleep(.15);app.player.pause();app.player.resume();app.stop_playback();audio_checks.append('history WAV native stream play/pause/resume/stop')
        page.audition_material(C);settle();time.sleep(.15);app.stop_playback();audio_checks.append('combination full snapshot LMMS audition/native stream')
        page.audition_material(A[0]);settle();time.sleep(.15);app.stop_playback();audio_checks.append('block snapshot LMMS audition/native stream')
    except Exception as exc:
        evidence['native_audio_pending']=str(exc);app.stop_playback()
    evidence['native_audio_executed']=audio_checks
    export=folder/'中文 空格 longer export directory';export.mkdir()
    signature=app.project_signature();history=copy.deepcopy(page.history);selection=app.result_list.curselection()
    evidence['exports']={}
    for kind,source in (('wav','preview.wav'),('mid','composition.mid'),('mmp','composition.mmp')):
        target=export/f'成品 V01 中文.{kind}'
        with patch('unified_ui.filedialog.asksaveasfilename',return_value=str(target)):app.export_result(kind)
        assert target.read_bytes()==(render/source).read_bytes()
        evidence['exports'][kind]=dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    assert signature==app.project_signature() and history==page.history and selection==app.result_list.curselection()
    assert not errors,errors
    evidence['errors']=errors;evidence['saved']=str(saved);evidence['status']='PASS'
    evidence['pending']=['human GUI mouse/trackpad acceptance','human listening','third-party MIDI/MMP reopening','Windows physical device and 125/150% scaling']
    (folder/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2));print(json.dumps(evidence,ensure_ascii=False,indent=2))
finally:
    page.preview_planner.close();root.after_cancel(app.timer);app.stop_playback();root.destroy()
