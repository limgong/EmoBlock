"""Actual whole-score renders based on the user's original theme."""
import hashlib
import wave
import flow_engine as f
import structure_engine as s
from runtime_config import ASSETS


def build_demo():
    source=ASSETS/'EmoBlocks-Calm.mmp'
    theme=s.materials.import_theme(source,bars=8,name='A',trim_overlaps=True,simultaneous='lower')
    pool=s.materials.new_pool();s.materials.add_item(pool,theme)
    answers=s.materials.generate_candidates(theme,'answer',31)
    for name,item in zip('EFG',answers):
        item['name']=name;item['accepted']=True;item['demo_auto_selected']=True;s.materials.add_item(pool,item)
    doc=s.create(pool,[theme['id']])
    for item in answers:doc=s.edit(doc,'insert',slot_id=doc['backbone'][0]['id'],material_id=item['id'])
    doc=f.prepare(doc)
    doc=f.set_region(doc,0,1,'calm',.2,.5)
    doc=f.set_region(doc,2,2,'crisis',.5,.9)
    doc=f.set_region(doc,3,3,'resolve',.65,.95)
    doc['demo_note']='A 来自用户平静版；E/F/G 为程序选取的演示回答句，非用户听感确认。'
    return doc


if __name__=='__main__':
    source=ASSETS/'EmoBlocks-Calm.mmp';before=hashlib.sha256(source.read_bytes()).hexdigest()
    doc=build_demo();results=[]
    for connections in (True,False):
        report=f.generate(doc,connections,lambda text:print(text,flush=True))
        assert report['audio']['clipped_samples']==0
        assert report['audio']['dry_clipped_samples']==0
        assert report['audio']['seconds']==65
        assert report['theme_preserved']
        # Every music bar must contain non-silent audio; tail is not counted as a bar.
        with wave.open(report['output_directory']+'/preview.wav','rb') as w:
            for _ in range(report['bars']):
                audio=f.music.np.frombuffer(w.readframes(88200),dtype='<i2')
                assert f.music.np.max(f.music.np.abs(audio.astype('int32')))>100
        results.append(report)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    s.materials.write_json(s.ROOT/'flow-verification.json',dict(technical_passed=True,human_listening_accepted=False,
        body_seconds=64,tail_seconds=1,results=results))
    print(results[0]['output_directory'],flush=True)
