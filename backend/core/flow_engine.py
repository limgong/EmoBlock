"""Structure-preserving, whole-score emotion arrangement and boundary repair."""
import copy
import hashlib
import json
import math
import random
import subprocess
import wave
from dataclasses import asdict

import structure_engine as structure

music = structure.materials.music
Note, BAR, PPQ = music.Note, music.BAR, music.PPQ


def expression_at(value,bars,beat):
    beat=max(0,min(bars*4,beat))
    nodes=value.get('beat_nodes')
    if nodes:
        if beat>=nodes[-1]['beat']:return dict(emotion=nodes[-1]['emotion'],intensity=nodes[-1]['intensity'])
        left,right=next((a,b) for a,b in zip(nodes,nodes[1:]) if a['beat']<=beat<b['beat'])
        ratio=(beat-left['beat'])/(right['beat']-left['beat'])
        return dict(emotion=left['emotion'],intensity=left['intensity']+(right['intensity']-left['intensity'])*ratio)
    settings=value.get('bar_settings')
    if settings:
        index=min(bars-1,int(beat//4));part=beat/4-index;v=settings[index]
        return dict(emotion=v['emotion'],intensity=v['start']+(v['end']-v['start'])*part)
    return dict(emotion=value['emotion'],intensity=value['start']+(value['end']-value['start'])*beat/(bars*4))


def edit_beat_node(doc,entry_id,beat,emotion=None,intensity=None,remove=False):
    validate(doc)
    entry=next((e for e in doc['placements'] if e['id']==entry_id),None)
    if entry is None:raise ValueError('请选择音乐块。')
    bars=structure.entry_material(doc,entry)['bars'];total=bars*4
    if type(beat) is not int or not 0<=beat<=total:raise ValueError('节点须落在有效整数拍或块终点。')
    result=copy.deepcopy(doc);value=result['expression'][entry_id]
    if 'bar_settings' in value:raise ValueError('此块已有小节细分。请先用整块应用明确重置，再建立拍级节点。')
    nodes=copy.deepcopy(value.get('beat_nodes',[dict(beat=0,emotion=value['emotion'],intensity=value['start']),
        dict(beat=total,emotion=value['emotion'],intensity=value['end'])]))
    if remove:
        if beat in (0,total):raise ValueError('起点和终点不能删除，可修改强度。')
        if not any(n['beat']==beat for n in nodes):raise ValueError('该拍没有节点。')
        nodes=[n for n in nodes if n['beat']!=beat]
    else:
        nodes=[n for n in nodes if n['beat']!=beat]+[dict(beat=beat,emotion=emotion,intensity=intensity)]
        nodes.sort(key=lambda n:n['beat'])
    value.update(emotion=nodes[0]['emotion'],start=nodes[0]['intensity'],end=nodes[-1]['intensity'],beat_nodes=nodes)
    validate(result);return result


def bar_settings(value,bars):
    if 'beat_nodes' in value:
        return [dict(emotion=expression_at(value,bars,i*4)['emotion'],start=expression_at(value,bars,i*4)['intensity'],
                     end=expression_at(value,bars,(i+1)*4)['intensity']) for i in range(bars)]
    if 'bar_settings' in value:return copy.deepcopy(value['bar_settings'])
    return [dict(emotion=value['emotion'],start=value['start']+(value['end']-value['start'])*i/bars,
                 end=value['start']+(value['end']-value['start'])*(i+1)/bars) for i in range(bars)]


def set_block_region(doc,entry_id,first,last,emotion,start,end):
    """One-based inclusive bar range inside one content or transition block."""
    validate(doc)
    entry=next((e for e in doc['placements'] if e['id']==entry_id),None)
    if entry is None:raise ValueError('请选择音乐块。')
    bars=structure.entry_material(doc,entry)['bars']
    if type(first) is not int or type(last) is not int or not 1<=first<=last<=bars:
        raise ValueError('块内小节范围无效。')
    result=copy.deepcopy(doc);value=result['expression'][entry_id];settings=bar_settings(value,bars)
    for i in range(first-1,last):
        settings[i]=dict(emotion=emotion,start=start+(end-start)*(i-first+1)/(last-first+1),
                        end=start+(end-start)*(i-first+2)/(last-first+1))
    if 'beat_nodes' in value:raise ValueError('此块已有拍级节点，请先整块重置后再使用小节细分。')
    value.update(emotion=settings[0]['emotion'],start=settings[0]['start'],end=settings[-1]['end'],bar_settings=settings)
    validate(result)
    return result


def prepare(doc):
    result = copy.deepcopy(structure.validate(doc))
    existing = result.get('expression', {})
    result['expression'] = {e['id']: existing.get(e['id'], dict(emotion='calm', start=.35, end=.35))
                            for e in result['placements']}
    for e in result['placements']:
        if e['kind']=='transition' and e['id'] not in existing:
            left=result['expression'][e['left_entry']];right=result['expression'][e['right_entry']]
            if 'bar_settings' in right:right=right['bar_settings'][0]
            result['expression'][e['id']]=dict(emotion=right['emotion'],start=left['end'],end=right['start'])
    validate(result)
    return result


def validate(doc):
    structure.validate(doc)
    if set(doc.get('expression', {})) != {e['id'] for e in doc['placements']}:
        raise ValueError('情绪设置未覆盖全部排列实例，请重新打开情绪工作台。')
    def check_value(value):
        if value['emotion'] not in music.EMOTIONS:
            raise ValueError('未知情绪。')
        if any(not isinstance(value[k], (int,float)) or not math.isfinite(value[k]) or not 0 <= value[k] <= 1 for k in ('start','end')):
            raise ValueError('强度必须为 0～100%。')
    for entry in doc['placements']:
        value=doc['expression'][entry['id']];check_value(value)
        if 'beat_nodes' in value:
            if 'bar_settings' in value:raise ValueError('拍级节点和小节细分不能同时使用。')
            nodes=value['beat_nodes'];total=structure.entry_material(doc,entry)['bars']*4
            if not isinstance(nodes,list) or not 2<=len(nodes)<=total+1:raise ValueError('拍级节点数量无效。')
            positions=[n['beat'] for n in nodes]
            if any(type(b) is not int or not 0<=b<=total for b in positions) or positions!=sorted(set(positions)) or positions[0]!=0 or positions[-1]!=total:
                raise ValueError('节点必须递增且包含起点和终点。')
            for node in nodes:check_value(dict(emotion=node['emotion'],start=node['intensity'],end=node['intensity']))
            if value['emotion']!=nodes[0]['emotion'] or value['start']!=nodes[0]['intensity'] or value['end']!=nodes[-1]['intensity']:
                raise ValueError('拍级节点与摘要不一致。')
        if 'bar_settings' in value:
            settings=value['bar_settings'];bars=structure.entry_material(doc,entry)['bars']
            if not isinstance(settings,list) or len(settings)!=bars:raise ValueError('块内情绪必须覆盖每个小节。')
            for setting in settings:check_value(setting)
            if value['emotion']!=settings[0]['emotion'] or value['start']!=settings[0]['start'] or value['end']!=settings[-1]['end']:
                raise ValueError('块内情绪摘要与小节设置不一致。')
    if structure.timeline(doc)['bars'] > 128:
        raise ValueError('首版连续作品最多 128 小节。')
    return doc


def set_region(doc, first, last, emotion, start, end):
    validate(doc)
    entries = doc['placements']
    if not 0 <= first <= last < len(entries): raise ValueError('请选择按顺序排列的起止块。')
    result = copy.deepcopy(doc)
    items = {i['id']:i for i in doc['pool']['items']}
    lengths = [structure.entry_material(doc,e)['bars'] for e in entries[first:last+1]]
    total = sum(lengths); cursor = 0
    for entry, length in zip(entries[first:last+1], lengths):
        result['expression'][entry['id']] = dict(emotion=emotion,
            start=start+(end-start)*cursor/total, end=start+(end-start)*(cursor+length)/total)
        cursor += length
    validate(result)
    return result


def chord_plan(notes, bars, tonic, mode, emotions):
    steps = [0,2,4,5,7,9,11] if mode=='major' else [0,2,3,5,7,8,10]
    chords = [tuple((tonic+steps[(d+k)%7])%12 for k in (0,2,4)) for d in range(7)]
    if mode=='minor': chords.append(((tonic+7)%12,(tonic+11)%12,(tonic+2)%12))
    costs, paths = {}, {}
    for bar in range(bars):
        weights = [0.]*12
        for n in notes:
            overlap=max(0,min(n.start+n.duration,(bar+1)*BAR)-max(n.start,bar*BAR))
            weights[n.pitch%12]+=overlap
        total=max(1,sum(weights)); new={}; next_paths={}
        for j,chord in enumerate(chords):
            score=3*sum(weights[p]/total for p in chord)
            if emotions[bar] in ('suspense','crisis') and j in (4,6,7): score+=.22
            if bar==bars-1 and j==0:score+=.65
            if not costs:new[j]=score;next_paths[j]=[j];continue
            best=max(costs,key=lambda k:costs[k]+.13*len(set(chords[k])&set(chord))-.03*min((chords[k][0]-chord[0])%12,(chord[0]-chords[k][0])%12))
            new[j]=score+costs[best]+.13*len(set(chords[best])&set(chord))-.03*min((chords[best][0]-chord[0])%12,(chord[0]-chords[best][0])%12)
            next_paths[j]=paths[best]+[j]
        costs,paths=new,next_paths
    return [chords[i] for i in paths[max(costs,key=costs.get)]]


def compile_score(doc, connections=True, fixed_chords=None):
    validate(doc)
    rows=structure.timeline(doc)['rows']; items={i['id']:i for i in doc['pool']['items']}
    first=items[rows[0]['material_id']]; tonic,mode=first['tonic'],first['mode']
    total_bars=sum(r['bars'] for r in rows); total=total_bars*BAR
    notes=[]; emotions=[]; levels=[]; starts=[];beat_values=[];fine_bars=set()
    for row in rows:
        begin=(row['start_bar']-1)*BAR; starts.append(begin)
        setting=doc['expression'][row['id']]
        for beat in range(row['bars']*4):
            if 'beat_nodes' in setting:
                beat_values.append(expression_at(setting,row['bars'],beat+.5));fine_bars.add(begin//BAR+beat//4)
            else:
                v=bar_settings(setting,row['bars'])[beat//4]
                beat_values.append(dict(emotion=v['emotion'],intensity=(v['start']+v['end'])/2))
        notes.extend(Note(n.pitch,n.start+begin,n.duration,n.velocity) for n in structure.materials.notes_of(structure.entry_material(doc,row)))
        for setting in bar_settings(setting,row['bars']):
            emotions.append(setting['emotion'])
            levels.append((setting['start']+setting['end'])/2)
    chords=chord_plan(notes,total_bars,tonic,mode,emotions)
    if fixed_chords:
        for bar,chord in fixed_chords.items():chords[bar]=tuple(chord)
    layers={}
    def layer(key,preset,volume,drum=None,pan=0):
        layers[key]=dict(name=key,preset=preset,volume=volume,pan=pan,drum=drum,notes=[])
    for preset in ('soft','bell','pluck','brass'):layer('theme_'+preset,preset,23)
    layer('harmony','pad',8,pan=-10);layer('bass','bass',18);layer('pulse','pluck',10,pan=12)
    layer('kick','bass',22,'bassdrum01.ogg');layer('snare','bass',16,'snare01.ogg');layer('hat','bass',9,'hihat_closed01.ogg',20)
    def add(key,pitch,start,length,vel):
        if start<0 or start>=total or length<=0:return
        layers[key]['notes'].append(Note(int(pitch),int(start),int(min(length,total-start)),max(1,min(110,round(vel)))))
    lead={'calm':'soft','hope':'bell','sad':'soft','suspense':'bell','crisis':'pluck','resolve':'brass'}
    for n in notes:
        state=beat_values[n.start//PPQ];level=state['intensity']
        add('theme_'+lead[state['emotion']],n.pitch,n.start,n.duration,n.velocity*(.68+.35*level))
    voicings=[]; previous=[48+tonic,55+tonic,60+tonic]
    for b,chord in enumerate(chords):
        # One continuous pad/bass vocabulary across content boundaries.
        voicing=sorted(min((p for p in range(45,78) if p%12==pc),key=lambda p:abs(p-previous[i])) for i,pc in enumerate(chord))
        voicings.append(voicing); previous=voicing
        span=PPQ if b in fine_bars else BAR
        for section in range(0,BAR,span):
            t=b*BAR+section;beat_index=t//PPQ
            state=beat_values[beat_index];level=state['intensity'];emotion=state['emotion']
            for pitch in voicing:add('harmony',pitch,t,span,(28 if emotion=='sad' else 34)+30*level)
            energetic=emotion in ('crisis','resolve')
            stride=240 if energetic and level>.65 else (480 if energetic else span)
            for offset in range(0,span,stride):add('bass',36+chord[0],t+offset,stride if stride==span else stride*.75,42+30*level)
            base={'calm':960,'hope':480,'sad':960,'suspense':480,'crisis':240,'resolve':480}[emotion]
            step=max(120,base//2) if level>.7 else base
            if not (emotion in ('calm','sad') and level<.25):
                for j,offset in enumerate(range(0,span,step)):
                    if emotion=='sad' and (j%2 or b%2):continue
                    if emotion=='suspense' and j%3==1:continue
                    if level<.4 and j%2:continue
                    pitch=voicing[(2-j)%3] if emotion=='sad' else voicing[j%3]
                    add('pulse',pitch,t+offset,min(step*.60,span-offset),35+28*level)
            if energetic or (emotion=='hope' and level>.75):
                for offset in ([0] if span==PPQ and beat_index%2==0 else [] if span==PPQ else [0,960]):add('kick',36,t+offset,100,58+22*level)
                for offset in ([0] if span==PPQ and beat_index%2==1 else [] if span==PPQ else [480,1440]):add('snare',38,t+offset,110,44+24*level)
                for offset in range(0,span,120 if level>.8 else 240):add('hat',42,t+offset,60,30+22*level)
    boundary_reports=[]
    boundaries=[(boundary,rows[i-1],rows[i],'between_blocks') for i,boundary in enumerate(starts[1:],1)]
    for row in rows:
        begin=(row['start_bar']-1)*4
        for beat in range(begin+1,begin+row['bars']*4):
            if beat_values[beat]['emotion']!=beat_values[beat-1]['emotion']:
                boundaries.append((beat*PPQ,row,row,'within_block'))
    boundaries.sort(key=lambda x:x[0])
    for boundary,left_row,right_row,boundary_kind in boundaries:
        b=boundary//BAR;left=chords[(boundary-1)//BAR];right=chords[b]
        before=beat_values[boundary//PPQ-1];after=beat_values[boundary//PPQ]
        rising=after['intensity']>before['intensity']+.08 or music.ENERGY[after['emotion']]>music.ENERGY[before['emotion']]+.2
        falling=after['intensity']<before['intensity']-.08 or music.ENERGY[after['emotion']]<music.ENERGY[before['emotion']]-.2
        record=dict(from_entry=left_row['id'],to_entry=right_row['id'],kind=boundary_kind,tick=boundary,
                    affected_ticks=[max(0,boundary-BAR),min(total,boundary+BAR)],left_chord=list(left),right_chord=list(right),
                    source_tail_pitch=max((n for n in notes if n.start<boundary),key=lambda n:n.start,default=notes[0]).pitch,
                    target_first_pitch=next((n.pitch for n in notes if n.start>=boundary),notes[-1].pitch),actions=[])
        if connections:
            # Clear only the last beat of the bass, then lead to the actual next root.
            cleaned=[]
            for n in layers['bass']['notes']:
                if boundary-PPQ<=n.start<boundary:continue
                if n.start<boundary-PPQ<n.start+n.duration:n=Note(n.pitch,n.start,boundary-PPQ-n.start,n.velocity)
                cleaned.append(n)
            layers['bass']['notes']=cleaned
            target=36+right[0]
            approach=min([p for p in range(31,61) if p%12 in left],key=lambda p:abs(p-target))
            add('bass',approach,boundary-PPQ,PPQ//2,48+20*before['intensity'])
            add('bass',target,boundary-PPQ//2,PPQ//2,45+20*after['intensity'])
            record['actions'].append('末拍低音导向下一实际和弦根音')
            if rising:
                for offset in (240,120):add('hat',42,boundary-offset,55,40+18*after['intensity'])
                record['actions'].append('末拍节奏引入')
            if falling:
                for key in ('pulse','kick','snare','hat'):
                    layers[key]['notes']=[n for n in layers[key]['notes'] if not boundary-PPQ//2<=n.start<boundary]
                record['actions'].append('末半拍伴奏撤出，主旋律保留')
            # Velocity handoff acts on accompaniment only, preserving melody attacks.
            for key in ('pulse','kick','snare','hat'):
                layers[key]['notes']=[Note(n.pitch,n.start,n.duration, max(1,round(n.velocity*.8))) if boundary<=n.start<boundary+PPQ else n for n in layers[key]['notes']]
            record['actions'].append('下一首拍伴奏柔化交接')
        boundary_reports.append(record)
    # Tie common pad tones at content boundaries only. No independent block fade-outs.
    if connections:
        boundary_set={r[0] for r in boundaries}; by_pitch={}
        for n in sorted(layers['harmony']['notes'],key=lambda n:(n.pitch,n.start)):
            history=by_pitch.setdefault(n.pitch,[])
            if history and n.start in boundary_set and history[-1].start+history[-1].duration==n.start:
                p=history[-1];history[-1]=Note(p.pitch,p.start,p.duration+n.duration,p.velocity)
                next(r for r in boundary_reports if r['tick']==n.start)['actions'].append('共同和弦音跨边界延留')
            else:history.append(n)
        layers['harmony']['notes']=[n for group in by_pitch.values() for n in group]
    result_layers=[]
    for value in layers.values():
        if value['notes']:
            value['notes'].sort(key=lambda n:(n.start,n.pitch));music._check_notes(value['notes']);result_layers.append(value)
    actual=sorted((n.pitch,n.start,n.duration) for l in result_layers if l['name'].startswith('theme_') for n in l['notes'])
    if actual!=sorted((n.pitch,n.start,n.duration) for n in notes):raise ValueError('主题保持检查失败。')
    return dict(bpm=first['bpm'],total_ticks=total,layers=result_layers,
        report=dict(engine='whole-score-rules-v1',bars=total_bars,duration_seconds=total_bars*240/first['bpm'],
            key=dict(tonic=tonic,mode=mode,source='素材池参考，非自动转调'),
            bar_emotions=emotions,bar_intensities=levels,beat_expressions=beat_values,chords=[list(c) for c in chords],
            playback_blocks=[dict(entry_id=r['id'],name=r['name'],kind=r['kind'],start_seconds=(r['start_bar']-1)*240/first['bpm'],
                end_seconds=(r['start_bar']-1+r['bars'])*240/first['bpm'],emotion=doc['expression'][r['id']]['emotion'],
                bar_settings=bar_settings(doc['expression'][r['id']],r['bars']),
                beat_nodes=copy.deepcopy(doc['expression'][r['id']].get('beat_nodes'))) for r in rows],
            connections_enabled=connections,boundaries=boundary_reports,theme_preserved=True,
            transition_blocks=[dict(entry_id=r['id'],left_entry=r['left_entry'],right_entry=r['right_entry'],
                name=r['name'],bars=r['bars'],start_bar=r['start_bar'],generator=r['generator'],time_policy='insert-and-shift')
                for r in rows if r['kind']=='transition'],
            warnings=['工作流规则原型，不宣称生成质量已通过评价。','原内容旋律保持；独立过渡块按结构新增小节，边界连接本身不加时长。',
                      '共同音延留会延续前侧力度；边界和声使用全曲规划，非局部缓存。',
                      '统一合成音色、固定速度拍号；MMP 时间网格会量化到 48 ticks/拍。']))


def finish_audio(dry_path, output_path, seconds, wet=.10):
    """Two streaming passes: stable memory usage even on long arrangements."""
    np=music.np
    with wave.open(str(dry_path),'rb') as f:
        rate=f.getframerate()
        if f.getnchannels()!=2 or f.getsampwidth()!=2:raise ValueError('需要双声道 16 位 PCM。')
    target=round(seconds*rate)+rate;fade=round(.08*rate)
    delays=[(round(.13*rate),wet,True),(round(.23*rate),wet*.65,False),(round(.37*rate),wet*.35,True)]
    history_size=delays[-1][0]
    def blocks():
        history=np.zeros((history_size,2));cursor=0
        with wave.open(str(dry_path),'rb') as f:
            while cursor<target:
                length=min(4096,target-cursor)
                raw=np.frombuffer(f.readframes(length),dtype='<i2').astype(np.float64).reshape(-1,2)/32768
                dry=np.zeros((length,2));dry[:len(raw)]=raw
                extended=np.concatenate((history,dry));result=dry.copy()
                for delay,gain,swap in delays:
                    delayed=extended[history_size-delay:history_size-delay+length]
                    result+=gain*(delayed[:,::-1] if swap else delayed)
                positions=np.arange(cursor,cursor+length)
                result*=np.clip((target-1-positions)/max(1,fade-1),0,1)[:,None]
                yield result,int(np.sum(np.abs(raw)>=32767/32768))
                history=extended[-history_size:];cursor+=length
    peak=0.;clipped=0
    for block,count in blocks():peak=max(peak,float(np.max(np.abs(block))));clipped+=count
    gain=min(1,.9/max(peak,1e-9));output_peak=0.;output_clipped=0
    with wave.open(str(output_path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate)
        for block,_ in blocks():
            block*=gain;output_peak=max(output_peak,float(np.max(np.abs(block))))
            pcm=np.round(np.clip(block,-1,.999969)*32768).astype('<i2')
            output_clipped+=int(np.sum(np.abs(pcm.astype(np.int32))>=32767));f.writeframes(pcm.tobytes())
    return dict(sample_rate=rate,seconds=target/rate,peak=round(output_peak,5),dry_clipped_samples=clipped,
                clipped_samples=output_clipped,peak_protection_gain=gain,tail_seconds=1)


def generate(doc, connections=True, progress=lambda text:None, render=True, arrangement=None):
    progress('统一规划情绪、和声与配器…')
    arrangement=copy.deepcopy(arrangement) if arrangement is not None else compile_score(doc,connections)
    folder=structure.ROOT/'renders'/structure.uid();folder.mkdir(parents=True)
    report=arrangement['report'];report['output_directory']=str(folder)
    report['source_structure_sha256']=hashlib.sha256(json.dumps(doc,sort_keys=True).encode()).hexdigest()
    try:
        structure.save(doc,folder/'structure.json')
        music.export_midi(arrangement,folder/'composition.mid');music.export_mmp(arrangement,folder/'composition.mmp')
        # Persist exact symbolic events for inspection and comparison.
        structure.materials.write_json(folder/'score.json',dict(bpm=arrangement['bpm'],total_ticks=arrangement['total_ticks'],
            layers=[dict(l,notes=[asdict(n) for n in l['notes']]) for l in arrangement['layers']]))
        report['score_sha256']=hashlib.sha256((folder/'score.json').read_bytes()).hexdigest()
        if render:
            progress('正在一次性渲染整段作品，不拼接单块 WAV…')
            proc=subprocess.run([str(music.LMMS),'render',str(folder/'composition.mmp'),'-o',str(folder/'dry.wav'),'-s','44100'],
                capture_output=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (folder/'render.log').write_bytes(proc.stdout+proc.stderr)
            if proc.returncode or not (folder/'dry.wav').is_file():raise ValueError('整段渲染失败，详情见 '+str(folder/'render.log'))
            report['audio']=finish_audio(folder/'dry.wav',folder/'preview.wav',report['duration_seconds'])
            if report['audio']['peak']<.0001:raise ValueError('整段音频静音。')
            if report['audio']['dry_clipped_samples']:report['warnings'].append('原始渲染存在削波，请降低音量。')
        report['status']='complete' if render else 'score_only'
    except Exception as exc:
        report.update(status='failed',error=str(exc));raise
    finally:structure.materials.write_json(folder/'report.json',report)
    return report
