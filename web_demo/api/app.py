"""Small single-process demo service; real r3 algorithms and LMMS outputs."""
import copy
import json
import os
import queue
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from .core import ROOT, SAMPLES, model, workflow, controller
from runtime_config import find_lmms

DATA = Path(os.environ.get('EMOBLOCKS_WEB_DATA', str(ROOT / 'data/web-demo'))).resolve()
COOKIE = 'emoblocks_demo'
MAX_AGE = 86400
LOCK = threading.RLock()
SESSIONS = {}
JOBS = {}
CREATIONS = {}
QUEUE = queue.Queue(maxsize=10)
STOP = threading.Event()


def db():
    connection = sqlite3.connect(DATA / 'sessions.sqlite')
    connection.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, touched REAL)')
    return connection


def persist(sid, c):
    folder = DATA / 'sessions' / sid
    folder.mkdir(parents=True, exist_ok=True)
    value = c._current_bundle()
    temp = folder / 'project.tmp'
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(folder / 'project.json')
    with db() as connection:
        connection.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (sid, time.time()))


def cleanup():
    with db() as connection:
        expired = connection.execute('SELECT id FROM sessions WHERE touched < ?', (time.time()-MAX_AGE,)).fetchall()
        for (sid,) in expired:
            if any(j['sid']==sid and j['status'] in ('QUEUED','RUNNING') for j in JOBS.values()):
                continue
            shutil.rmtree(DATA / 'sessions' / sid, ignore_errors=True)
            SESSIONS.pop(sid, None)
            for key in [k for k,j in JOBS.items() if j['sid']==sid]:
                JOBS.pop(key, None)
            connection.execute('DELETE FROM sessions WHERE id=?', (sid,))


def session(request):
    sid = request.cookies.get(COOKIE, '')
    if len(sid)!=48 or any(ch not in '0123456789abcdef' for ch in sid):
        raise HTTPException(401, '请重新开始体验。')
    with LOCK:
        with db() as connection:
            row = connection.execute('SELECT touched FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None or row[0] < time.time()-MAX_AGE:
            raise HTTPException(401, '体验已过期，请重新开始。')
        if sid not in SESSIONS:
            path = DATA / 'sessions' / sid / 'project.json'
            c = workflow.Controller()
            c.load(path)
            SESSIONS[sid] = c
        with db() as connection:
            connection.execute('UPDATE sessions SET touched=? WHERE id=?', (time.time(), sid))
        return sid, SESSIONS[sid]


def public_material(item):
    return {**{k:item[k] for k in ('id','label','kind','length_ticks')},
        'notes':[{k:n[k] for k in ('pitch','start_tick','duration_tick','velocity')} for n in item['notes']]}


def view(c):
    p = c.project
    placements = [{**{k:x[k] for k in ('id','material_id','start_tick','length_ticks','emotion')},
                   'base_snapshot':public_material(x['base_snapshot'])} for x in p['placements']]
    return dict(fingerprint=model.fingerprint(p), ppq=p['ppq'], bpm=p['bpm'], grid_count=p['grid_count'],
        total_ticks=p['total_ticks'], materials=[public_material(m) for m in p['materials']], placements=placements,
        intensity_points=p['intensity_points'], protections=[{k:x[k] for k in ('kind','start_tick','end_tick')} for x in p['protections']], blanks=[{k:b[k] for k in ('id','start_tick','end_tick')} for b in p['blank_regions']],
        memory=c.state()['memory_info'], can_undo=c.session.can_undo, can_redo=c.session.can_redo,
        candidates=candidates(c))


def candidates(c):
    attempt = c._recommendation_attempt()
    if not attempt or attempt['recommendation']['outcome'] is None:
        return []
    return [dict(id=x['id'], rank=x['rank'], reasons=x['reasons'], mode=attempt['recommendation']['request']['mode'],
                 changed=x['modes'][attempt['recommendation']['request']['mode']]['assets']['comparison']['files']['wav']['sha256']!=x['modes'][attempt['recommendation']['request']['mode']]['assets']['final']['files']['wav']['sha256'], ready=attempt['state']=='READY', applied=bool(attempt['recommendation']['receipt'] and attempt['recommendation']['receipt']['candidate_ref']['id']==x['id'] and c.project['accepted_candidate_id']==attempt['recommendation']['receipt']['accepted_record_id']))
            for x in attempt['recommendation']['outcome']['candidates']]


def version(c, fingerprint):
    if model.fingerprint(c.project) != fingerprint:
        raise HTTPException(409, '工程已变化，请刷新后重试。')


def cancel_active(sid, c):
    for j in JOBS.values():
        if j['sid']==sid and j['status'] in ('QUEUED','RUNNING'):
            (j['folder'] / 'cancel').touch()
            c.cancel_recommendations(j['capture']['token'])


def terminate(proc):
    if proc.poll() is None:
        if os.name=='posix': os.killpg(proc.pid, signal.SIGTERM)
        else: proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name=='posix': os.killpg(proc.pid, signal.SIGKILL)
            else: proc.kill()
            proc.wait()


def run_jobs():
    last_clean = 0
    while not STOP.is_set():
        if time.monotonic()-last_clean > 60:
            with LOCK: cleanup()
            last_clean = time.monotonic()
        try: j = QUEUE.get(timeout=.5)
        except queue.Empty: continue
        proc = None
        try:
            with LOCK:
                c = SESSIONS.get(j['sid'])
                if c is None or (j['folder']/'cancel').exists() or not c.accepts(j['capture']['token']):
                    j['status']='CANCELLED'
                    if c: c.fail_recommendations(j['capture']['token'], {'code':'CANCELLED','message':'任务已取消。','details':{}});persist(j['sid'],c)
                    continue
                j['status']='RUNNING'
            env = dict(os.environ, EMOBLOCKS_DATA_DIR=str(j['folder']/'assets'), PYTHONUNBUFFERED='1')
            with (j['folder']/'worker.log').open('wb') as log:
                proc = subprocess.Popen([sys.executable, '-m', 'web_demo.api.worker', str(j['folder'])],
                    cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=(os.name=='posix'))
                began=time.monotonic(); cancelling=None
                while proc.poll() is None:
                    if STOP.is_set() or time.monotonic()-began>600:
                        (j['folder']/'cancel').touch()
                        j['error']='任务超时或服务正在重启。'
                    if (j['folder']/'cancel').exists():
                        if cancelling is None: cancelling=time.monotonic()
                        if time.monotonic()-cancelling>3: terminate(proc)
                    time.sleep(.1)
            with LOCK:
                c=SESSIONS[j['sid']]
                if (j['folder']/'cancel').exists():
                    c.fail_recommendations(j['capture']['token'], {'code':'CANCELLED','message':'任务已取消。','details':{}})
                    j['status']='CANCELLED'
                elif (j['folder']/'output.json').is_file():
                    outcome=json.loads((j['folder']/'output.json').read_text())
                    accepted=c.finish_recommendations(j['capture']['token'],outcome)
                    j['status']=outcome['status'] if accepted else 'STALE'
                    if outcome.get('error'): j['error']=outcome['error']['message']
                else:
                    c.fail_recommendations(j['capture']['token'], {'code':'RENDER_FAILED','message':'生成失败，请重试或选择较短工程。','details':{}})
                    j['status']='FAILED';j['error']='生成失败。服务器已保留诊断。'
                persist(j['sid'],c)
        except Exception:
            import traceback
            traceback.print_exc()
            with LOCK:
                j['status']='FAILED';j['error']='生成未通过验证，请重试。'
                c=SESSIONS.get(j['sid'])
                if c:
                    c.fail_recommendations(j['capture']['token'], {'code':'VALIDATION_FAILED','message':j['error'],'details':{}})
                    persist(j['sid'],c)
        finally:
            if proc: terminate(proc)
            QUEUE.task_done()


@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True,exist_ok=True)
    with db(): pass
    STOP.clear()
    thread=threading.Thread(target=run_jobs,daemon=True);thread.start()
    yield
    STOP.set();thread.join(timeout=8)

app=FastAPI(title='EmoBlocks Demo', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

@app.middleware('http')
async def limits(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail':'不允许跨站修改。'},403)
        # Bound streamed requests, including chunked bodies.
        body=b''
        async for chunk in request.stream():
            body+=chunk
            if len(body)>131072: return JSONResponse({'detail':'请求过大。'},413)
        request._body=body
    result=await call_next(request)
    result.headers['X-Content-Type-Options']='nosniff'
    result.headers['Referrer-Policy']='same-origin'
    result.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):
        result.headers['Cache-Control']='no-store'
    return result

@app.exception_handler(model.ProjectError)
async def project_error(request, exc):
    return JSONResponse({'detail':str(exc), 'code':exc.code},422)

class NewSession(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sample:str='calm'
class Mutation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fingerprint:str=Field(max_length=128)
    action:str=Field(max_length=40)
    args:dict=Field(default_factory=dict)
class Generate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fingerprint:str=Field(max_length=128)
    mode:str='melody_only'
class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fingerprint:str=Field(max_length=128)
    candidate_id:str=Field(max_length=128)

@app.get('/api/health')
def health():
    return {'status':'ok','renderer_available':find_lmms().is_file(),'queue':QUEUE.qsize()}

@app.get('/api/samples')
def samples():
    return [{'id':key,'label':v[0]} for key,v in SAMPLES.items()]

@app.post('/api/session')
def create_session(data:NewSession, response:Response, request:Request):
    if data.sample not in SAMPLES: raise HTTPException(422,'示例不存在。')
    with LOCK:
        cleanup()
        ip=request.client.host if request.client else 'unknown'
        now=time.time()
        for key in list(CREATIONS):
            CREATIONS[key]=[t for t in CREATIONS[key] if now-t<3600]
            if not CREATIONS[key]: del CREATIONS[key]
        if len(CREATIONS.get(ip,[]))>=15: raise HTTPException(429,'请稍后再创建新体验。')
        CREATIONS.setdefault(ip,[]).append(now)
        with db() as connection:
            count=connection.execute('SELECT count(*) FROM sessions').fetchone()[0]
        if count>=100: raise HTTPException(429,'体验人数较多，请稍后再试。')
        sid=secrets.token_hex(24);c=controller(data.sample);SESSIONS[sid]=c;persist(sid,c)
        response.set_cookie(COOKIE,sid,max_age=MAX_AGE,httponly=True,samesite='strict',secure=os.environ.get('EMOBLOCKS_SECURE_COOKIE')=='1')
        return view(c)

@app.get('/api/project')
def project(request:Request):
    with LOCK:
        _,c=session(request);return view(c)

@app.post('/api/edit')
def edit(data:Mutation,request:Request):
    with LOCK:
        sid,c=session(request);version(c,data.fingerprint)
        if data.action not in ('place','move','delete','resize','set_intensity','set_trace','mark_blank','delete_blank','set_emotion','undo','redo','derive'):
            raise HTTPException(422,'此操作不可用。')
        args=data.args
        allowed={'place':{'material_id','start_tick'},'move':{'placement_id','start_tick'},'delete':{'placement_id'},
          'resize':{'grid_count'},'set_intensity':{'points'},'set_trace':{'points'},'mark_blank':{'start_tick','end_tick'},
          'delete_blank':{'blank_id'},'set_emotion':{'placement_ids','emotion'},'undo':set(),'redo':set(),'derive':{'material_id','method'}}
        if set(args)!=allowed[data.action]: raise HTTPException(422,'操作参数不完整或包含未知字段。')
        if data.action=='resize' and (type(args.get('grid_count')) is not int or not 1<=args['grid_count']<=32):
            raise HTTPException(422,'在线体验支持1至32格。')
        if data.action=='set_intensity' and (not isinstance(args.get('points'),list) or len(args['points'])>65):
            raise HTTPException(422,'最多65个强度控制点。')
        if data.action in ('place','move') and (type(args.get('start_tick')) is not int or args['start_tick']%480):
            raise HTTPException(422,'请按拍放置。')
        if data.action=='set_trace':
            if not isinstance(args['points'],list) or len(args['points'])>257: raise HTTPException(422,'手绘轨迹过长。')
            import curve_memory
            args={'points':curve_memory.normalize_trace(args['points'],c.project['total_ticks'])}
        cancel_active(sid,c)
        if data.action in ('undo','redo'): getattr(c,data.action)()
        elif data.action=='derive':
            if len(c.project['materials'])>150: raise HTTPException(422,'示例素材已达上限。')
            if set(args)!= {'material_id','method'} or args['method'] not in ('variant','answer','counter','rhythm','develop','density'):
                raise HTTPException(422,'请选择有效生成方式。')
            batch=workflow.prepare_generation(c.project,args['material_id'],args['method'])
            captured=c.capture_job('DERIVE',{'kind':'material','id':args['material_id']})
            c.apply_batch(batch,captured['token'])
        else: c.edit('set_intensity' if data.action=='set_trace' else data.action,**args)
        persist(sid,c);return view(c)

@app.post('/api/generate')
def generate(data:Generate,request:Request):
    with LOCK:
        sid,c=session(request);version(c,data.fingerprint)
        if data.mode not in ('melody_only','arranged'): raise HTTPException(422,'请选择编配方式。')
        if not find_lmms().is_file(): raise HTTPException(503,'渲染服务未就绪。')
        if not c.project['placements']: raise HTTPException(422,'请先放入至少一个旋律积木。')
        if any(j['sid']==sid and j['status'] in ('QUEUED','RUNNING') for j in JOBS.values()): raise HTTPException(409,'请等待或取消当前任务。')
        if sum(j['sid']==sid and time.time()-j['created']<900 for j in JOBS.values())>=6: raise HTTPException(429,'请稍后再生成，每15分钟最多6次。')
        if sum(j['sid']==sid for j in JOBS.values())>=12: raise HTTPException(429,'本次体验的生成次数已用完。')
        if shutil.disk_usage(DATA).free<1024**3: raise HTTPException(503,'服务器空间不足，请稍后重试。')
        if QUEUE.full(): raise HTTPException(429,'生成队列已满，请稍后重试。')
        captured=c.capture_recommendations(parameters={'max_pipeline_candidates':2,'max_recommendations':2,'completion_budget':{'max_expansions':4096,'beam_width':4,'material_limit':8,'max_new_notes':2048}},mode=data.mode)
        jid=secrets.token_hex(16);folder=DATA/'sessions'/sid/'jobs'/jid;folder.mkdir(parents=True)
        (folder/'input.json').write_text(json.dumps(captured,ensure_ascii=False),encoding='utf-8')
        j=dict(id=jid,sid=sid,folder=folder,capture=captured,status='QUEUED',created=time.time(),error=None)
        JOBS[jid]=j;QUEUE.put_nowait(j);persist(sid,c)
        return {'id':jid,'status':'QUEUED'}

@app.get('/api/jobs/{jid}')
def job(jid:str,request:Request):
    with LOCK:
        sid,_=session(request);j=JOBS.get(jid)
        if j is None or j['sid']!=sid: raise HTTPException(404,'任务不存在或服务已重启，请重新生成。')
        progress={}
        try: progress=json.loads((j['folder']/'progress.json').read_text())
        except (OSError,ValueError): pass
        return dict(id=jid,status=j['status'],error=j['error'],progress=progress)

@app.post('/api/jobs/{jid}/cancel')
def cancel(jid:str,request:Request):
    with LOCK:
        sid,c=session(request);j=JOBS.get(jid)
        if j is None or j['sid']!=sid: raise HTTPException(404,'任务不存在。')
        if j['status'] in ('QUEUED','RUNNING'): cancel_active(sid,c)
        return {'status':j['status']}

@app.post('/api/confirm')
def confirm(data:Confirm,request:Request):
    with LOCK:
        sid,c=session(request);version(c,data.fingerprint)
        c.apply_recommendation(data.candidate_id,confirmation_ref=c.confirmation_ref(data.candidate_id))
        persist(sid,c);return view(c)

@app.get('/api/assets/{candidate_id}/{kind}/{fmt}')
def asset(candidate_id:str,kind:str,fmt:str,request:Request):
    if kind not in ('final','comparison') or fmt not in ('wav','mid','mmp'): raise HTTPException(404)
    with LOCK:
        sid,c=session(request)
        authenticated=c.recommendation_asset(candidate_id,kind)
        from curve_recommendations import resolve, audio
        attempt,member_candidate=c._candidate(candidate_id)
        member=member_candidate['modes'][attempt['recommendation']['request']['mode']]
        score=resolve(c._bundle['final_facts'],member[kind+'_score_ref'],'final_score')
        audio.validate_asset(authenticated,score,dict(id=candidate_id,version=1,fingerprint=candidate_id),required_formats=(fmt,))
        path=Path(authenticated['files'][fmt]['path']).resolve()
        if not path.is_relative_to(DATA/'sessions'/sid) or not path.is_file(): raise HTTPException(404,'文件已过期。')
        return FileResponse(path,media_type={'wav':'audio/wav','mid':'audio/midi','mmp':'application/xml'}[fmt],filename=f'EmoBlocks-{kind}.{fmt}')

DIST=ROOT/'web_demo/client/dist'
if DIST.is_dir(): app.mount('/',StaticFiles(directory=DIST,html=True),name='web')
