"""Real service + LMMS acceptance; no mocked audio. Run against local server."""
import json,time,os
from pathlib import Path
import httpx
out=Path(os.environ.get('SMOKE_OUTPUT','data/web-demo-evidence'));out.mkdir(parents=True,exist_ok=True)
with httpx.Client(base_url=os.environ.get('SMOKE_URL','http://127.0.0.1:8765'),timeout=60) as c:
 def post(url,payload):
  r=c.post(url,json=payload);r.raise_for_status();return r.json()
 p=post('/api/session',{'sample':os.environ.get('SMOKE_SAMPLE','joy')})
 def edit(action,args):
  global p
  p=post('/api/edit',dict(fingerprint=p['fingerprint'],action=action,args=args))
 edit('resize',{'grid_count':8})
 edit('set_intensity',{'points':[{'tick':0,'level':.2},{'tick':3840,'level':.45},{'tick':9600,'level':.9},{'tick':15360,'level':.3}]})
 mids=[m['id'] for m in p['materials'] if m['kind']=='block']
 for i in (0,1,4,5,7):
  edit('place',{'material_id':mids[i%len(mids)],'start_tick':i*1920})
  if i>=4:edit('set_emotion',{'placement_ids':[p['placements'][-1]['id']],'emotion':'hope' if i<7 else 'resolve'})
 if os.environ.get('SMOKE_BLANK')=='1':edit('mark_blank',{'start_tick':11520,'end_tick':13440})
 jid=post('/api/generate',{'fingerprint':p['fingerprint'],'mode':os.environ.get('SMOKE_MODE','melody_only')})['id']
 (out/'session.json').write_text(json.dumps({'cookies':dict(c.cookies),'job':jid}))
 start=time.monotonic()
 while time.monotonic()-start<610:
  j=c.get('/api/jobs/'+jid).json()
  print(j,flush=True)
  if j['status'] not in ('QUEUED','RUNNING'):break
  time.sleep(3)
 p=c.get('/api/project').json();(out/'result.json').write_text(json.dumps({'job':j,'project':p},ensure_ascii=False,indent=2))
 assert p['candidates'],j
 cid=p['candidates'][0]['id']
 for kind in ('comparison','final'):
  for fmt in ('wav','mid','mmp'):
   r=c.get(f'/api/assets/{cid}/{kind}/{fmt}');r.raise_for_status();(out/f'{kind}.{fmt}').write_bytes(r.content)
 p=post('/api/confirm',{'fingerprint':p['fingerprint'],'candidate_id':cid})
 assert sum(bool(x['applied']) for x in p['candidates'])==1
 assert next(x for x in p['candidates'] if x['id']==cid)['applied']
 (out/'confirmed.json').write_text(json.dumps(p,ensure_ascii=False))
 print('REAL_RENDER_PASS',len(p['candidates']),flush=True)
