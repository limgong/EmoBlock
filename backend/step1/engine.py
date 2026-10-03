"""EmoBlocks step 1: bounded, offline, rule-based MIDI arrangement.

Input files are parsed as note data only; imported plugins are never executed.
All times in the arrangement are integer ticks at PPQ=480.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import subprocess
import sys
import uuid
import wave
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
from runtime_config import data_root, find_lmms, sample_path
sys.path.insert(0, str(ROOT / 'vendor'))
import mido
import numpy as np

PPQ = 480
BAR = PPQ * 4
LMMS = find_lmms()
EMOTIONS = {
    'calm': '平静／安定', 'hope': '温暖／希望', 'sad': '悲伤／失落',
    'suspense': '悬疑／不安', 'crisis': '紧张／危机', 'resolve': '振奋／坚定',
}
ENERGY = dict(calm=.15, hope=.4, sad=.2, suspense=.3, crisis=.85, resolve=.9)
DARK = {'suspense', 'crisis'}
NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']


@dataclass(frozen=True)
class Note:
    pitch: int
    start: int
    duration: int
    velocity: int = 80


@dataclass
class Melody:
    name: str
    notes: list


@dataclass
class Source:
    path: str
    sha256: str
    bpm: float
    tracks: list
    warnings: list = field(default_factory=list)


@dataclass
class Options:
    emotion: str = 'calm'
    intensity: float = .55
    variation: float = .25
    previous: str = ''
    following: str = ''
    seed: int = 1


def _check_notes(notes):
    if not notes:
        raise ValueError('没有可用音符。请选择包含主旋律的非鼓轨。')
    if len(notes) > 3000:
        raise ValueError('选定轨道音符太多，请先截取 4～8 小节。')
    for n in notes:
        if not (12 <= n.pitch <= 119 and n.start >= 0 and n.duration > 0 and 1 <= n.velocity <= 127):
            raise ValueError('音符超出原型支持范围（MIDI 12～119），或时长／力度无效。')


def load_source(path):
    path = Path(path)
    if path.suffix.lower() not in {'.mid', '.midi', '.mmp'}:
        raise ValueError('仅支持 .mid、.midi 和未压缩 .mmp；WAV／MMPZ 暂不支持。')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('文件超过 8 MB，请提供较短的旋律工程。')
    data = path.read_bytes()
    warnings = []
    if path.suffix.lower() == '.mmp':
        if b'<!ENTITY' in data.upper():
            raise ValueError('不支持含实体声明的 XML 工程。')
        root = ET.fromstring(data)
        head = root.find('head')
        if head is None:
            raise ValueError('缺少 LMMS 工程头。')
        bpm = float(head.get('bpm', '120'))
        if (int(head.get('timesig_numerator', '4')), int(head.get('timesig_denominator', '4'))) != (4, 4):
            raise ValueError('首版只支持固定 4/4 拍。')
        if int(head.get('masterpitch', '0')) != 0:
            raise ValueError('请先将 LMMS 全局移调还原为 0，再导出旋律。')
        for a in root.findall('.//automationpattern'):
            if a.findall('time') or a.findall('object'):
                raise ValueError('此 MMP 含自动化事件；请先导出固定速度的纯旋律 MIDI。')
        tracks = []
        for t in root.findall('./song/trackcontainer/track'):
            if t.get('type') != '0' or t.get('muted', '0') == '1':
                continue
            it = t.find('instrumenttrack')
            if it is not None and (float(it.get('pitch', '0')) != 0 or int(it.get('basenote', '57')) != 57):
                raise ValueError('此工程含乐器轨移调，请导出纯旋律 MIDI。')
            notes = []
            for p in t.findall('pattern'):
                if p.get('muted', '0') == '1':
                    continue
                offset = int(p.get('pos', '0')) * 10
                for n in p.findall('note'):
                    length = float(n.get('len', '0'))
                    if length <= 0:
                        continue
                    notes.append(Note(int(n.get('key')) + 12,
                                      offset + round(float(n.get('pos', '0')) * 10),
                                      round(length * 10), max(1, min(127, round(float(n.get('vol', '80')))))))
            if notes:
                _check_notes(notes)
                tracks.append(Melody(t.get('name', '旋律轨'), sorted(notes, key=lambda n: (n.start, n.pitch))))
        warnings.append('MMP 只读取音符；原插件、音色、效果与声像不导入。使用本原型的合成音色。')
    else:
        mid = mido.MidiFile(path)
        if mid.type == 2 or mid.ticks_per_beat <= 0:
            raise ValueError('暂不支持 MIDI type 2 或 SMPTE 时间格式。')
        tempos, signatures = {0: 500000}, {0: (4, 4)}
        tracks, controls = [], set()
        for ti, track in enumerate(mid.tracks):
            absolute = 0
            pending = defaultdict(deque)
            by_channel = defaultdict(list)
            for msg in track:
                absolute += msg.time
                if msg.type == 'set_tempo':
                    tempos[absolute] = msg.tempo
                elif msg.type == 'time_signature':
                    signatures[absolute] = (msg.numerator, msg.denominator)
                elif msg.type in {'pitchwheel', 'control_change', 'aftertouch', 'polytouch'}:
                    controls.add(msg.type)
                elif msg.type == 'note_on' and msg.velocity > 0:
                    pending[(msg.channel, msg.note)].append((absolute, msg.velocity))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    queue = pending[(msg.channel, msg.note)]
                    if queue:
                        start, vel = queue.popleft()
                        if msg.channel != 9 and absolute > start:
                            by_channel[msg.channel].append(Note(msg.note, round(start * PPQ / mid.ticks_per_beat),
                                max(1, round((absolute - start) * PPQ / mid.ticks_per_beat)), vel))
            if any(pending.values()):
                raise ValueError('MIDI 含未结束的音符，请在编辑器中修复后重试。')
            for channel, notes in sorted(by_channel.items()):
                _check_notes(notes)
                tracks.append(Melody(f'{track.name or "轨道 " + str(ti + 1)} · CH{channel + 1}',
                                     sorted(notes, key=lambda n: (n.start, n.pitch))))
        if len(set(tempos.values())) != 1:
            raise ValueError('检测到速度变化。首版只支持固定 BPM，不会自动压平速度。')
        if set(signatures.values()) != {(4, 4)}:
            raise ValueError('首版只支持固定 4/4 拍。')
        bpm = mido.tempo2bpm(tempos[0])
        if controls:
            warnings.append('输入含踏板／弯音等控制事件：首版仅参考音符，不复现这些演奏控制。')
    if not math.isfinite(bpm) or not 40 <= bpm <= 220:
        raise ValueError('首版支持 40～220 BPM。')
    if not tracks:
        raise ValueError('没有可用的非鼓旋律轨。')
    return Source(str(path.resolve()), hashlib.sha256(data).hexdigest(), bpm, tracks, warnings)


def select_melody(source, index=0):
    if not 0 <= index < len(source.tracks):
        raise ValueError('旋律轨选择无效。')
    melody = source.tracks[index]
    bars = math.ceil(max(n.start + n.duration for n in melody.notes) / BAR)
    if not 4 <= bars <= 8:
        raise ValueError(f'选定轨道跨度为 {bars} 小节；请先在编辑器截取 4～8 小节（从项目零点计）。')
    return melody, bars


def infer_key(notes):
    hist = np.zeros(12)
    for n in notes:
        hist[n.pitch % 12] += min(n.duration, BAR) * (1.25 if n.start % PPQ == 0 else 1)
    profiles = {'major': np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]),
                'minor': np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])}
    ranked = []
    for mode, profile in profiles.items():
        for tonic in range(12):
            score = float(np.corrcoef(hist, np.roll(profile, tonic))[0,1]) if np.std(hist) else 0
            if not math.isfinite(score):
                score = 0
            ranked.append((score, tonic, mode))
    ranked.sort(reverse=True)
    return ranked[0][1], ranked[0][2], round(ranked[0][0] - ranked[1][0], 3)


def choose_chords(notes, bars, tonic, mode, options, rng):
    scale = [0,2,4,5,7,9,11] if mode == 'major' else [0,2,3,5,7,8,10]
    candidates = []
    for degree in range(7):
        pcs = tuple((tonic + scale[(degree + k) % 7]) % 12 for k in (0,2,4))
        candidates.append((pcs[0], pcs, degree))
    if mode == 'minor':
        root = (tonic + 7) % 12
        candidates.append((root, (root, (root+4)%12, (root+7)%12), 4))
    dp, paths = {}, {}
    for bar in range(bars):
        weights = np.zeros(12)
        for n in notes:
            overlap = max(0, min(n.start+n.duration, (bar+1)*BAR) - max(n.start, bar*BAR))
            weights[n.pitch % 12] += overlap * (1.3 if n.start % PPQ == 0 else 1)
        weights /= max(1, weights.sum())
        new_dp, new_paths = {}, {}
        for ci,(root,pcs,degree) in enumerate(candidates):
            score = sum(weights[p] for p in pcs) * 3
            score -= .2 * sum(weights[p] for p in range(12) if p not in pcs and any((p-q)%12 in (1,11) for q in pcs))
            if options.emotion in {'calm','resolve'} and degree == 0:
                score += .16
            if options.emotion == 'sad' and (pcs[1]-root)%12 == 3:
                score += .16
            if options.emotion in DARK and degree in (4,6):
                score += .13
            if bar == bars-1:
                score += .4 if degree == (4 if options.following in DARK else 0) else 0
            score += rng.uniform(-.1,.1)
            if not dp:
                new_dp[ci],new_paths[ci] = score,[ci]
            else:
                scored = [(value - (.13 if prev == ci else 0) - .015*min((root-candidates[prev][0])%12,(candidates[prev][0]-root)%12),prev) for prev,value in dp.items()]
                best,prev = max(scored)
                new_dp[ci],new_paths[ci] = best+score,paths[prev]+[ci]
        dp,paths = new_dp,new_paths
    return [candidates[i] for i in paths[max(dp,key=dp.get)]]


PRESETS = {
    'soft': (0, .005,.24,.5, 0, '柔和键盘（合成）'),
    'bell': (0, .001,.36,.15, 10, '钟音键盘（合成）'),
    'pad': (1, .09,.3,.75, 48, '暖弦垫（合成）'),
    'dark': (1, .04,.25,.55, 89, '暗色长音（合成）'),
    'pluck': (1, .001,.025,.15, 45, '短拨弦（合成）'),
    'brass': (1, .009,.12,.72, 61, '明亮合奏（合成）'),
    'bass': (0, .003,.08,.7, 33, '低音（合成）'),
}
PROFILES = {
    'calm': ('soft','bell','pad',960,.13),
    'hope': ('bell','soft','pad',240,.19),
    'sad': ('soft','dark','dark',960,.22),
    'suspense': ('dark','bell','dark',480,.28),
    'crisis': ('pluck','brass','dark',240,.08),
    'resolve': ('brass','bell','pad',240,.18),
}


def arrange(source, index, options):
    if options.emotion not in EMOTIONS or options.previous not in {'',*EMOTIONS} or options.following not in {'',*EMOTIONS}:
        raise ValueError('未知情绪。')
    if not (0 <= options.intensity <= 1 and 0 <= options.variation <= 1):
        raise ValueError('强度和变化程度应在 0～1。')
    melody,bars = select_melody(source,index)
    total = bars*BAR
    rng = random.Random(options.seed)
    tonic,mode,confidence = infer_key(melody.notes)
    chords = choose_chords(melody.notes,bars,tonic,mode,options,rng)
    primary,secondary,pad,step,space = PROFILES[options.emotion]
    level = options.intensity
    theme = copy.deepcopy(melody.notes)
    edits = []
    for i,n in enumerate(theme):
        # Preserve the beginning of each bar; vary only short phrase-tail notes.
        if n.start % BAR >= 1200 and n.duration <= PPQ and rng.random() < options.variation*.7:
            pcs = chords[n.start//BAR][1]
            candidates = [p for p in range(max(24,n.pitch-3),min(108,n.pitch+4)) if p%12 in pcs and p!=n.pitch]
            if candidates:
                pitch = min(candidates,key=lambda p:abs(p-n.pitch))
                theme[i] = Note(pitch,n.start,n.duration,n.velocity)
                edits.append({'start_tick':n.start,'from':n.pitch,'to':pitch,'type':'句尾邻近和弦音变奏'})
    layers=[]
    def layer(name,preset,volume,pan=0,drum=None):
        result={'name':name,'preset':preset,'volume':volume,'pan':pan,'drum':drum,'notes':[]}
        layers.append(result)
        return result['notes']
    lead=layer('主题 · '+PRESETS[primary][5],primary,28)
    relay=layer('接力 · '+PRESETS[secondary][5],secondary,24,8)
    bass=layer('低音支撑','bass',22)
    harmony=layer('和声铺底',pad,9,-12)
    pulse=layer('琶音／脉冲','pluck' if options.emotion in DARK else 'soft',12,14)
    reply=layer('句间回应','bell',16,-18)
    double=layer('主题八度叠奏','brass' if options.emotion=='resolve' else 'soft',10)
    kick=layer('底鼓','bass',29,drum='bassdrum01.ogg')
    snare=layer('军鼓','bass',20,drum='snare01.ogg')
    hat=layer('踩镲','bass',12,20,drum='hihat_closed01.ogg')
    crash=layer('进入重音','bass',14,drum='crash01.ogg')
    context=[]
    if options.previous:
        context.append('参考前块标签 '+EMOTIONS[options.previous]+' 调整开头力度包络；未推测其实际和声或音色。')
    if options.following:
        context.append('参考后块标签 '+EMOTIONS[options.following]+' 调整末尾密度与解决倾向；不生成整段连接。')
    def contour(t):
        fraction=t/total
        value=.73 + .27*level
        if options.previous:
            value *= 1 + (ENERGY[options.previous]-ENERGY[options.emotion])*.3*max(0,1-fraction*4)
        if options.following:
            value *= 1 + (ENERGY[options.following]-ENERGY[options.emotion])*.4*max(0,(fraction-.5)*2)
        return max(.4,min(1.2,value))
    def add(dest,pitch,t,length,velocity):
        if t>=total or length<=0:
            return
        dest.append(Note(max(12,min(119,int(pitch))),int(t),int(min(length,total-t)),
                         max(1,min(115,round(velocity*contour(t))))))
    for n in theme:
        target=lead if (n.start//BAR//2)%2==0 else relay
        add(target,n.pitch,n.start,n.duration,n.velocity*(.7+.4*level))
        if options.emotion=='resolve' and n.start>=total//2 and level>.35:
            add(double,n.pitch+12,n.start,n.duration,n.velocity*.65)
    for bar,(root,pcs,degree) in enumerate(chords):
        start=bar*BAR
        root_pitch=36+root
        low_pedal=36+tonic if options.emotion=='suspense' else root_pitch
        if options.emotion in {'crisis','resolve'}:
            stride=240 if level>.45 else 480
            for t in range(0,BAR,stride):
                add(bass,root_pitch+(12 if t%480 else 0),start+t,int(stride*.72),64+25*level)
        else:
            add(bass,low_pedal,start,BAR-60,48+20*level)
        voicing=sorted(48+p for p in pcs)
        if options.emotion in {'hope','resolve'}:
            voicing[-1]+=12
        if options.emotion=='suspense':
            voicing=[48+tonic,55+tonic]
        # Layers enter or leave at musical boundaries, rather than all at once.
        pad_active=not (options.emotion=='sad' and bar==bars-1) and (bar>0 or options.emotion in {'sad','calm'})
        if pad_active:
            for p in voicing:
                add(harmony,p,start,BAR-80,45+30*level)
        local_step=step
        if level>.75 or (options.following in DARK and bar>=bars-2):
            local_step=max(120,step//2)
        if options.emotion=='crisis' and bar>=bars//2:
            local_step=max(120,local_step//2)
        if options.emotion=='calm' and bar<bars//2:
            continue_pulse=False
        else:
            continue_pulse=True
        if continue_pulse:
            pattern=rng.choice([(0,1,2,1),(0,2,1,2)])
            for j,t in enumerate(range(0,BAR,local_step)):
                if options.emotion=='suspense' and j%3==1:
                    continue
                p=voicing[pattern[j%4] % len(voicing)]
                add(pulse,p,start+t,max(60,int(local_step*.62)),45+24*level+(10 if t%480==0 else 0))
        drums=options.emotion in {'crisis','resolve'} or (options.emotion=='hope' and level>.7 and bar>=bars//2)
        if drums:
            for t in (0,480,960,1440):
                add(kick,36,start+t,100,72+18*level)
            for t in (480,1440):
                add(snare,38,start+t,110,62+23*level)
            for t in range(240,BAR,240 if level<.7 else 120):
                add(hat,42,start+t,55,40+25*level)
            if bar in (0,bars//2) and options.emotion=='resolve':
                add(crash,49,start,480,62)
        if options.emotion=='suspense' and bar%2:
            add(hat,42,start+1440,60,32)
    # Respond only in existing gaps, including between motifs inside a phrase.
    occupied=sorted((n.start,n.start+n.duration) for n in theme)
    merged=[]
    for a,b in occupied:
        if merged and a<=merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],b)
        else:
            merged.append([a,b])
    gaps=[(b,merged[i+1][0] if i+1<len(merged) else total) for i,(a,b) in enumerate(merged)]
    used=set()
    for a,b in gaps:
        bar=min(bars-1,a//BAR)
        if b-a>=120 and bar not in used and (bar%2==1 or options.emotion in {'hope','suspense'}):
            used.add(bar)
            pcs=chords[bar][1]
            length=min(120,(b-a)//2)
            for j in range(min(2,(b-a)//length)):
                add(reply,60+pcs[(j+options.seed)%3],a+j*length,max(30,length-15),40+18*level)
    layers=[l for l in layers if l['notes']]
    for l in layers:
        l['notes'].sort(key=lambda n:(n.start,n.pitch))
        _check_notes(l['notes'])
    chord_names=[]
    for root,pcs,degree in chords:
        chord_names.append(NAMES[root]+('m' if (pcs[1]-root)%12==3 else '')+('dim' if (pcs[2]-root)%12==6 else ''))
    report={
        'engine':'EmoBlocks rules v0.1 (no AI model)', 'emotion':EMOTIONS[options.emotion],
        'options':asdict(options),'bpm':source.bpm,'bars':bars,'duration_seconds':bars*4*60/source.bpm,
        'source':source.path,'source_sha256':source.sha256,'selected_track':melody.name,
        'estimated_key':NAMES[tonic]+(' major' if mode=='major' else ' minor'),
        'key_score_margin':confidence,'chords':chord_names,'theme_edits':edits,
        'theme_note_count':len(theme),'context':context or ['独立片段：无前后情绪条件。'],
        'warnings':source.warnings+['调性／和弦来自启发式评分，非人工确认；主题识别与情绪效果需试听。',
            '只使用内置合成音色与 LMMS 自带鼓采样；MIDI 通用音色不等于 LMMS 实际音色。',
            'MMP 采用 48 ticks/拍：MIDI 精细时值输出 MMP 时会四舍五入；MID 保留 480 ticks/拍。'],
        'layers':[{'name':l['name'],'events':len(l['notes'])} for l in layers],
        'spatial_effect':{'kind':'stereo feed-forward echoes','wet':round(space*(.6+.4*level),3)},
        'notes':'选择情绪后自动规划；可适度变奏，无全曲移调，无 BPM 修改。无合适空隙时跳过回应。',
    }
    return {'layers':layers,'report':report,'total_ticks':total,'bpm':source.bpm}


def export_midi(arrangement,path):
    mid=mido.MidiFile(type=1,ticks_per_beat=PPQ)
    conductor=mido.MidiTrack()
    mid.tracks.append(conductor)
    conductor.append(mido.MetaMessage('set_tempo',tempo=mido.bpm2tempo(arrangement['bpm'])))
    conductor.append(mido.MetaMessage('time_signature',numerator=4,denominator=4))
    conductor.append(mido.MetaMessage('end_of_track',time=arrangement['total_ticks']))
    channels=iter([c for c in range(16) if c!=9])
    for index,l in enumerate(arrangement['layers']):
        channel=9 if l['drum'] else next(channels)
        track=mido.MidiTrack();mid.tracks.append(track)
        track.append(mido.MetaMessage('track_name',name=f'{index+1} {l["preset"]}'))
        track.append(mido.Message('program_change',channel=channel,program=PRESETS[l['preset']][4]))
        events=[]
        for n in l['notes']:
            velocity=max(1,min(127,round(n.velocity*l['volume']/35)))
            events.extend([(n.start,1,n.pitch,velocity),(n.start+n.duration,0,n.pitch,0)])
        prev=0
        for t,on,pitch,vel in sorted(events):
            track.append(mido.Message('note_on' if on else 'note_off',channel=channel,note=pitch,velocity=vel,time=t-prev));prev=t
        track.append(mido.MetaMessage('end_of_track',time=max(0,arrangement['total_ticks']-prev)))
    mid.save(path)


def _xml(parent,tag,**attrs):
    return ET.SubElement(parent,tag,{k:str(v) for k,v in attrs.items()})


def export_mmp(arrangement,path):
    root=ET.Element('lmms-project',{'creator':'LMMS','creatorversion':'1.2.2','version':'1.0','type':'song'})
    _xml(root,'head',bpm=arrangement['bpm'],mastervol=62,masterpitch=0,timesig_numerator=4,timesig_denominator=4)
    song=_xml(root,'song');tc=_xml(song,'trackcontainer',type='song',visible=1,width=1100,height=650,x=0,y=0)
    for l in arrangement['layers']:
        t=_xml(tc,'track',type=0,name=l['name'],muted=0,solo=0)
        it=_xml(t,'instrumenttrack',vol=l['volume'],pan=l['pan'],pitch=0,basenote=57,fxch=0,usemasterpitch=1)
        if l['drum']:
            sample=sample_path(LMMS,l['drum'])
            if not sample.is_file():
                raise ValueError('缺少 LMMS 鼓采样：'+str(sample))
            inst=_xml(it,'instrument',name='audiofileprocessor')
            _xml(inst,'audiofileprocessor',src=sample.as_posix(),amp=100,interp=1,sframe=0,eframe=1,lframe=0,reversed=0)
        else:
            wave_type,attack,release,sustain,_,_=PRESETS[l['preset']]
            inst=_xml(it,'instrument',name='tripleoscillator')
            _xml(inst,'tripleoscillator',vol0=100,vol1=12 if l['preset']=='brass' else 0,vol2=0,
                 coarse0=0,coarse1=0,finel0=0,finer0=0,finel1=-4,finer1=4,pan0=0,wavetype0=wave_type,wavetype1=wave_type)
            env=_xml(it,'eldata',fwet=1 if l['preset']=='dark' else 0,ftype=0,fcut=1500,fres=.5)
            _xml(env,'elvol',amt=1,att=attack,hold=0,dec=.22,sustain=sustain,rel=release,pdel=0,lamt=0)
        _xml(it,'fxchain',enabled=0,numofeffects=0)
        p=_xml(t,'pattern',type=1,name=l['name'],pos=0,len=round(arrangement['total_ticks']/10),steps=16)
        for n in l['notes']:
            _xml(p,'note',key=57 if l['drum'] else n.pitch-12,pos=round(n.start/10),len=max(1,round(n.duration/10)),vol=n.velocity,pan=0)
    _xml(song,'timeline',lp0pos=0,lp1pos=round(arrangement['total_ticks']/10),lpstate=0)
    notes=_xml(song,'projectnotes');notes.text='原型合成音色；最终 WAV 额外应用立体声短回声空间处理，MMP 为处理前可编辑编配。'
    ET.indent(root)
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def postprocess(dry_path,output_path,seconds,wet):
    with wave.open(str(dry_path),'rb') as f:
        rate,channels,width=f.getframerate(),f.getnchannels(),f.getsampwidth()
        if channels!=2 or width!=2:
            raise ValueError('渲染音频格式不是双声道 16-bit PCM。')
        dry=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64).reshape(-1,2)/32768
    body=round(seconds*rate)
    # Retain a fixed 1-second tail for spatial processing and note release.
    target=body+rate
    padded=np.zeros((target,2));padded[:min(len(dry),target)]=dry[:target]
    result=padded.copy()
    for delay,gain,swap in [(.13,wet,True),(.23,wet*.65,False),(.37,wet*.35,True)]:
        shift=round(delay*rate)
        result[shift:]+=padded[:-shift,::-1] * gain if swap else padded[:-shift]*gain
    fade=min(round(.08*rate),target)
    result[-fade:]*=np.linspace(1,0,fade)[:,None]
    raw_peak=float(np.max(np.abs(result)))
    gain=min(1,.9/max(raw_peak,1e-9))
    result*=gain
    pcm=np.round(np.clip(result,-1,.999969)*32768).astype('<i2')
    with wave.open(str(output_path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm.tobytes())
    return {'sample_rate':rate,'seconds':target/rate,'peak':round(float(np.max(np.abs(result))),5),
            'dry_clipped_samples':int(np.sum(np.abs(dry)>=32767/32768)),
            'clipped_samples':int(np.sum(np.abs(pcm.astype(np.int32))>=32767)),
            'peak_protection_gain':gain}


def generate(source,index,options,progress=lambda text:None,render=True):
    progress('分析参考旋律，选择和弦与编配方案…')
    arrangement=arrange(source,index,options)
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+options.emotion+'-'+uuid.uuid4().hex[:6]
    folder=data_root()/'step1'/'generated'/run_id;folder.mkdir(parents=True)
    report=arrangement['report'];report['output_directory']=str(folder)
    try:
        export_midi(arrangement,folder/'arrangement.mid')
        export_mmp(arrangement,folder/'arrangement.mmp')
        if render:
            if not LMMS.is_file():
                raise ValueError('找不到 LMMS：'+str(LMMS))
            progress('编配完成，正在生成声音…')
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            proc=subprocess.run([str(LMMS),'render',str(folder/'arrangement.mmp'),'-o',str(folder/'dry.wav'),'-s','44100'],
                                capture_output=True,timeout=120,creationflags=flags)
            (folder/'render.log').write_bytes(proc.stdout+proc.stderr)
            if proc.returncode or not (folder/'dry.wav').is_file():
                raise ValueError('LMMS 渲染失败；MIDI 和工程已保存，详情见 render.log。')
            progress('应用空间效果，检查音频…')
            report['audio']=postprocess(folder/'dry.wav',folder/'preview.wav',report['duration_seconds'],report['spatial_effect']['wet'])
            if report['audio']['dry_clipped_samples']:
                report['warnings'].append('原始渲染存在削波样本，请降低音轨音量后重试。')
        report['status']='complete' if render else 'score_only'
    except Exception as exc:
        report['status']='failed';report['error']=str(exc)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    progress('完成。可以试听，或打开工程继续编辑。')
    return report
