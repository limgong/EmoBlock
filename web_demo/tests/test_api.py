import os
import tempfile
import unittest
os.environ['EMOBLOCKS_WEB_DATA']=tempfile.mkdtemp(prefix='emoblocks-web-test-')
from fastapi.testclient import TestClient
from web_demo.api import app as service

class API(unittest.TestCase):
    def setUp(self):
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
    def test_trace_single_undo_and_owner_checks(self):
        before=self.p['fingerprint']
        points=[{'tick':i*240,'level':1-abs(i-64)/64} for i in range(129)]
        self.assertEqual(self.edit('set_trace',{'points':points}).status_code,200)
        self.assertLess(len(self.p['intensity_points']),10)
        self.assertEqual(max(self.p['intensity_points'],key=lambda x:x['level'])['tick'],15360)
        self.assertEqual(self.edit('undo',{}).status_code,200)
        self.assertEqual(self.p['fingerprint'],before)
        sid=self.client.cookies.get(service.COOKIE)
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            folder=Path(directory)
            service.JOBS['ownership']=dict(sid=sid,status='SUCCEEDED',folder=folder,error=None)
            self.assertEqual(self.client.get('/api/jobs/ownership').status_code,200)
            other=TestClient(service.app)
            r=other.post('/api/session',json={'sample':'calm'})
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

if __name__=='__main__':unittest.main()
