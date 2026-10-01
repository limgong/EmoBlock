"""Source snapshot display and cached single-instrument audition."""
import hashlib
import json
import subprocess
import wave
from pathlib import Path
import story_engine as engine


def source_blocks(source,bpm):
    engine.number(bpm,40,220,'试听速度')
    rate=bpm*480/60;rows=[]
    for start in range(0,source['ticks'],1920):
        end=min(start+1920,source['ticks']);notes=[]
        for n in source['notes']:
            a=max(start,n['start']);b=min(end,n['start']+n['duration'])
            if b>a:notes.append(dict(n,start=a-start,duration=b-a,continuation=n['start']<start))
        i=len(rows)+1
        rows.append(dict(entry_id=str(i),name=f'{source["name"]} · 第{i}块',start_tick=start,end_tick=end,
                         start_seconds=start/rate,end_seconds=end/rate,notes=notes,emotion='calm'))
    return rows


def render_source(source,bpm,progress=lambda _:None):
    rows=source_blocks(source,bpm)
    payload=dict(notes=source['notes'],ticks=source['ticks'],bpm=bpm,renderer='source-soft-v1')
    # Keep the cache path short enough for the legacy Windows MCI WAV driver.
    key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:32]
    folder=engine.flow.structure.ROOT/'auditions'/key;path=folder/'preview.wav'
    if path.is_file():
        try:
            with wave.open(str(path),'rb') as f:
                if f.getnframes()/f.getframerate()>=rows[-1]['end_seconds']:return path,rows
        except (wave.Error,EOFError):pass
    folder.mkdir(parents=True,exist_ok=True)
    progress('首次试听：用统一音色渲染输入旋律，随后按块播放…')
    music=engine.music
    score=dict(bpm=bpm,total_ticks=source['ticks'],layers=[dict(name='source melody',preset='soft',volume=28,pan=0,drum=None,notes=[music.Note(**n) for n in source['notes']])])
    music.export_mmp(score,folder/'source.mmp')
    proc=subprocess.run([str(music.LMMS),'render',str(folder/'source.mmp'),'-o',str(folder/'dry.wav'),'-s','44100','-x','1'],
                        capture_output=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (folder/'render.log').write_bytes(proc.stdout+proc.stderr)
    if proc.returncode or not (folder/'dry.wav').is_file():raise ValueError('素材试听渲染失败：'+str(folder/'render.log'))
    engine.flow.finish_audio(folder/'dry.wav',path,rows[-1]['end_seconds'])
    return path,rows
