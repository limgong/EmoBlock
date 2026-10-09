import os
import tempfile
import unittest
os.environ['EMOBLOCKS_WEB_DATA']=tempfile.mkdtemp(prefix='emoblocks-web-test-')
from fastapi.testclient import TestClient
from web_demo.api import app as service

class API(unittest.TestCase):
    def setUp(self):
        service.CREATIONS.clear()
        self.client=TestClient(service.app);self.client.__enter__()
        response=self.client.post('/api/session',json={'sample':'joy'})
        self.assertEqual(response.status_code,200,response.text)
        self.p=response.json()
    def tearDown(self): self.client.__exit__(None,None,None)
    def edit(self,action,args):
        r=self.client.post('/api/edit',json={'fingerprint':self.p['fingerprint'],'action':action,'args':args})
        if r.status_code==200:self.p=r.json()
        return r
    def test_edits_and_restore(self):
        mid=self.p['materials'][0]['id'];before=self.p['fingerprint']
        self.assertEqual(self.edit('place',{'material_id':mid,'start_tick':0}).status_code,200)
        self.assertEqual(self.edit('place',{'material_id':mid,'start_tick':0}).status_code,422)
        self.assertEqual(self.edit('resize',{'grid_count':33}).status_code,422)
        self.assertEqual(self.edit('move',{'placement_id':self.p['placements'][0]['id'],'start_tick':1}).status_code,422)
        r=self.client.post('/api/edit',json={'fingerprint':before,'action':'resize','args':{'grid_count':4}})
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.edit('undo',{}).status_code,200)
        self.assertEqual(len(self.p['placements']),0)
        service.SESSIONS.clear()
        r=self.client.get('/api/project');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['fingerprint'],self.p['fingerprint'])
    def test_security_and_isolation(self):
        self.assertEqual(self.client.post('/api/edit',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/edit',content=b'x'*131073).status_code,413)
        other=TestClient(service.app)
        self.assertEqual(other.get('/api/project').status_code,401)
        self.assertEqual(self.client.get('/api/jobs/missing').status_code,404)
        self.assertNotIn('/Users/',str(self.p))

    def test_populated_joy_example_is_new_and_persists(self):
        original_sid=self.client.cookies.get(service.COOKIE)
        before=self.p['fingerprint']
        response=self.client.post('/api/session',json={'sample':'joy','example':True})
        self.assertEqual(response.status_code,200,response.text)
        example=response.json()
        self.assertNotEqual(self.client.cookies.get(service.COOKIE),original_sid)
        self.assertEqual(service.model.fingerprint(service.SESSIONS[original_sid].project),before)
        self.assertEqual(example['grid_count'],8)
        self.assertEqual([p['start_tick']//1920 for p in example['placements']],[0,1,2,4,5,6,7])
        self.assertEqual([p['emotion'] for p in example['placements']],['calm','hope','crisis','resolve','resolve','hope','calm'])
        self.assertEqual([p['base_snapshot']['display_name'] for p in example['placements']],['A1','A2','A3','A5','A6','A7','A8'])
        self.assertEqual(example['memory']['state'],'BOUND')
        service.SESSIONS.clear()
        self.assertEqual(self.client.get('/api/project').json()['fingerprint'],example['fingerprint'])
        self.assertEqual(self.client.post('/api/session',json={'sample':'missing','example':True}).status_code,422)
    def test_trace_single_undo_and_owner_checks(self):
        before=self.p['fingerprint']
        points=[{'tick':i*120,'level':1-abs(i-64)/64} for i in range(129)]
        self.assertEqual(self.edit('set_trace',{'points':points}).status_code,200)
        self.assertLess(len(self.p['intensity_points']),10)
        self.assertEqual(max(self.p['intensity_points'],key=lambda x:x['level'])['tick'],7680)
        self.assertEqual(self.edit('undo',{}).status_code,200)
        self.assertEqual(self.p['fingerprint'],before)
        sid=self.client.cookies.get(service.COOKIE)
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            folder=Path(directory)
            service.JOBS['ownership']=dict(sid=sid,status='SUCCEEDED',folder=folder,error=None)
            self.assertEqual(self.client.get('/api/jobs/ownership').status_code,200)
            other=TestClient(service.app)
            r=other.post('/api/session',json={'sample':'joy'})
            self.assertEqual(r.status_code,200)
            self.assertEqual(other.get('/api/jobs/ownership').status_code,404)
            self.assertEqual(other.post('/api/jobs/ownership/cancel',json={}).status_code,404)
            service.JOBS.pop('ownership')

    def test_variants_blanks(self):
        n=len(self.p['materials'])
        r=self.edit('derive',{'material_id':self.p['materials'][0]['id'],'method':'rhythm'})
        self.assertEqual(r.status_code,200,r.text);self.assertGreater(len(self.p['materials']),n)
        self.assertEqual(self.edit('mark_blank',{'start_tick':0,'end_tick':1920}).status_code,200)
        self.assertEqual(self.edit('place',{'material_id':self.p['materials'][0]['id'],'start_tick':0}).status_code,422)
        self.assertEqual(self.edit('delete_blank',{'blank_id':self.p['blanks'][0]['id']}).status_code,200)

    def test_default_and_shrink_drawn_curve(self):
        self.assertEqual(self.p['grid_count'],8)
        self.assertEqual(self.p['total_ticks'],32*480)
        points=[dict(tick=0,level=.2),dict(tick=7680,level=.9),dict(tick=14000,level=.4),dict(tick=15360,level=.25)]
        self.assertEqual(self.edit('set_intensity',{'points':points}).status_code,200)
        before=self.p.copy()
        controller=service.SESSIONS[self.client.cookies.get(service.COOKIE)]
        expected=service.model.intensity_at(controller.project,13440)
        self.assertEqual(self.edit('resize',{'grid_count':7}).status_code,200)
        self.assertEqual(self.p['intensity_points'][-1],dict(tick=13440,level=expected))
        self.assertTrue(all(p['tick']<=13440 for p in self.p['intensity_points']))
        self.assertEqual(self.edit('undo',{}).status_code,200)
        self.assertEqual(self.p['fingerprint'],before['fingerprint'])
        self.assertEqual(self.edit('redo',{}).status_code,200)
        service.SESSIONS.clear()
        self.assertEqual(self.client.get('/api/project').json()['grid_count'],7)

    def test_shrink_preserves_tail_music_and_blank(self):
        mid=self.p['materials'][0]['id']
        self.assertEqual(self.edit('place',{'material_id':mid,'start_tick':13440}).status_code,200)
        before=self.p['fingerprint']
        response=self.edit('resize',{'grid_count':7})
        self.assertEqual(response.status_code,422)
        self.assertIn('清空画板',response.json()['detail'])
        self.assertEqual(self.p['fingerprint'],before)
        self.assertEqual(self.edit('delete',{'placement_id':self.p['placements'][0]['id']}).status_code,200)
        self.assertEqual(self.edit('mark_blank',{'start_tick':13440,'end_tick':15360}).status_code,200)
        self.assertEqual(self.edit('resize',{'grid_count':7}).status_code,422)

    def test_clear_is_one_undoable_transaction_and_invalidates_job(self):
        mid=self.p['materials'][0]['id']
        self.assertEqual(self.edit('derive',{'material_id':mid,'method':'rhythm'}).status_code,200)
        self.assertEqual(self.edit('place',{'material_id':mid,'start_tick':13440}).status_code,200)
        self.assertEqual(self.edit('mark_blank',{'start_tick':0,'end_tick':1920}).status_code,200)
        self.assertEqual(self.edit('set_intensity',{'points':[dict(tick=0,level=.2),dict(tick=14000,level=.9),dict(tick=15360,level=.3)]}).status_code,200)
        self.assertEqual(self.p['memory']['state'],'BOUND')
        before=self.p.copy()
        controller=service.SESSIONS[self.client.cookies.get(service.COOKIE)]
        captured=controller.capture_recommendations(mode='melody_only')
        self.assertTrue(controller.accepts(captured['token']))
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            folder=Path(directory)
            service.JOBS['clear-active']=dict(sid=self.client.cookies.get(service.COOKIE),status='RUNNING',folder=folder,capture=captured)
            try:
                self.assertEqual(self.edit('clear_canvas',{}).status_code,200)
                self.assertTrue((folder/'cancel').is_file())
            finally:
                service.JOBS.pop('clear-active')
        self.assertFalse(controller.accepts(captured['token']))
        self.assertEqual(self.p['materials'],before['materials'])
        self.assertEqual(self.p['grid_count'],before['grid_count'])
        self.assertFalse(self.p['placements']);self.assertFalse(self.p['blanks']);self.assertFalse(self.p['protections']);self.assertFalse(self.p['candidates'])
        self.assertEqual(self.p['intensity_points'],[dict(tick=0,level=.25),dict(tick=15360,level=.25)])
        self.assertEqual(self.edit('undo',{}).status_code,200)
        self.assertEqual(self.p['fingerprint'],before['fingerprint'])
        self.assertEqual(self.edit('redo',{}).status_code,200)
        self.assertFalse(self.p['placements'])
        self.assertEqual(self.edit('resize',{'grid_count':7}).status_code,200)
        fingerprint=self.p['fingerprint']
        self.assertEqual(self.edit('clear_canvas',{'unknown':True}).status_code,422)
        self.assertEqual(self.p['fingerprint'],fingerprint)

    def test_official_names_and_catalog(self):
        samples=self.client.get('/api/samples').json()
        self.assertEqual([s['id'] for s in samples],['joy','canon-simple','canon-developed','minuet-g','fur-elise'])
        self.assertEqual(sum(s['label']=='欢乐颂' for s in samples),1)
        self.assertEqual(samples[1]['license'],'CC BY 3.0')
        self.assertIn('Jim Paterson',samples[1]['credit'])
        self.assertEqual(self.client.post('/api/session',json={'sample':'calm'}).status_code,422)
        visible=[m for m in self.p['materials'] if m['library_visible']]
        names=[m['display_name'] for m in visible]
        self.assertEqual(names[:8],[f'A{i}' for i in range(1,9)])
        self.assertEqual(len(names),len(set(names)))
        self.assertTrue(all(name.startswith('B') for name in names[8:]))
        original=self.p['fingerprint']
        self.assertEqual(self.client.get('/api/project').json()['fingerprint'],original)
        target=visible[0]['id']
        self.assertEqual(self.edit('derive',{'material_id':target,'method':'rhythm'}).status_code,200)
        self.assertEqual(self.p['materials'][-1]['display_name'],'A1′')
        self.assertEqual(self.edit('place',{'material_id':target,'start_tick':0}).status_code,200)
        self.assertEqual(self.p['placements'][0]['base_snapshot']['display_name'],'A1')

    def test_classical_midi_imports(self):
        import hashlib
        import mido
        from web_demo.api.core import ROOT, SAMPLE_CATALOG
        for item in SAMPLE_CATALOG:
            with self.subTest(sample=item['id']):
                path=ROOT/'assets/samples'/item['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item['sha256'])
                response=self.client.post('/api/session',json={'sample':item['id']})
                self.assertEqual(response.status_code,200,response.text)
                project=response.json()
                sid=self.client.cookies.get(service.COOKIE)
                source=service.SESSIONS[sid].project['sources'][0]
                self.assertEqual(len(source['notes']),item['notes'])
                self.assertEqual(source['length_ticks'],item['beats']*480)
                self.assertEqual(round(source['provenance']['original_bpm']),item['bpm'])
                midi=mido.MidiFile(path);tick=0;starts={};expected=[]
                for message in mido.merge_tracks(midi.tracks):
                    tick+=message.time
                    if message.type=='note_on' and message.velocity:
                        starts[message.note]=tick
                    elif message.type=='note_off' or (message.type=='note_on' and not message.velocity):
                        start=starts.pop(message.note)
                        expected.append((message.note,start*480//midi.ticks_per_beat,(tick-start)*480//midi.ticks_per_beat))
                actual=[(n['pitch'],n['start_tick'],n['duration_tick']) for n in source['notes']]
                self.assertEqual(sorted(actual),sorted(expected))
                self.assertFalse(project['placements'])
                originals=[m for m in project['materials'] if m['display_name'].startswith('A') and m['library_visible']]
                self.assertEqual(len(originals),item['beats']//4)
                self.assertEqual(originals[0]['notes'][0]['pitch'],source['notes'][0]['pitch'])
                self.assertEqual(self.client.get('/api/project').json()['fingerprint'],project['fingerprint'])

if __name__=='__main__':unittest.main()
