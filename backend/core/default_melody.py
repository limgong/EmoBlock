"""Built-in, self-encoded C-major opening of Beethoven's Ode to Joy."""
import hashlib
import json

SOURCE_URL='https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=528'


def source():
    # Eight bars, 4/4, monophonic. Durations are quarter-note beats.
    phrase=[(64,1),(64,1),(65,1),(67,1),(67,1),(65,1),(64,1),(62,1),
            (60,1),(60,1),(62,1),(64,1)]
    sequence=phrase+[(64,1.5),(62,.5),(62,2)]+phrase+[(62,1.5),(60,.5),(60,2)]
    notes=[];tick=0
    for pitch,beats in sequence:
        duration=round(beats*480)
        notes.append(dict(pitch=pitch,start=tick,duration=duration,velocity=80));tick+=duration
    digest=hashlib.sha256(json.dumps(notes,sort_keys=True).encode()).hexdigest()
    return dict(id='builtin-ode-to-joy-v1',name='默认 · 欢乐颂主题（8小节）',notes=notes,ticks=tick,bpm=120.,role='main',tonic=0,mode='major',
                builtin_default=True,source=dict(url=SOURCE_URL,sha256=digest,composer='Ludwig van Beethoven',
                rights='Source edition marked Public Domain by Mutopia; own monophonic C-major encoding',
                adaptation='Opening eight bars, transposed to C major, 120 BPM; not a downloaded recording'),
                warnings=['内置演示素材，不是本项目原创主题；首段用户导入会替换默认素材。'])
