"""Emotion-only local revision: immutable baseline events outside explicit windows."""
import copy
import hashlib
import json
from pathlib import Path
import flow_engine as flow

BAR=flow.BAR


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def load_baseline(report):
    folder=Path(report['output_directory'])
    try:
        stored=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        doc=flow.structure.load(folder/'structure.json')
        raw=(folder/'score.json').read_bytes()
        score=json.loads(raw)
    except (OSError,ValueError,KeyError) as exc:
        raise ValueError('基准结果的结构／音符／报告缺失或损坏，请重新生成完整作品。') from exc
    if stored.get('status') not in ('complete','score_only'):
        raise ValueError('不能使用失败结果作为局部修改基准。')
    if stored.get('source_structure_sha256')!=digest(doc):
        raise ValueError('基准结构与生成报告不一致。')
    if stored.get('score_sha256') and hashlib.sha256(raw).hexdigest()!=stored['score_sha256']:
        raise ValueError('基准音符文件已被修改，请重新生成完整作品。')
    flow.validate(doc)
    rows=flow.structure.timeline(doc)['rows']
    if score['total_ticks']!=sum(r['bars'] for r in rows)*BAR or score['bpm']!=doc['pool']['items'][0]['bpm']:
        raise ValueError('基准音符时长或速度不一致。')
    names=set()
    for layer in score['layers']:
        if layer['name'] in names:raise ValueError('基准存在重复声部。')
        names.add(layer['name'])
        layer['notes']=[flow.Note(**n) for n in layer['notes']]
        flow.music._check_notes(layer['notes'])
        if any(n.start<0 or n.start+n.duration>score['total_ticks'] for n in layer['notes']):
            raise ValueError('基准音符越界。')
    score['report']=stored
    return doc,score


def merge_windows(windows):
    merged=[]
    for a,b in sorted(windows):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged


def touches(note,windows):
    return any(note.start<b and note.start+note.duration>a for a,b in windows)


def events_outside(score,windows):
    return sorted((layer['name'],n.pitch,n.start,n.duration,n.velocity)
                  for layer in score['layers'] for n in layer['notes'] if not touches(n,windows))


def compile_local(doc,base_doc,base_score,connections=True):
    flow.validate(doc);flow.validate(base_doc)
    if connections!=base_score['report']['connections_enabled']:
        raise ValueError('局部修改须保持基准的连接开关；改变连接策略请完整生成。')
    for key in ('placements','backbone'):
        if doc[key]!=base_doc[key]:raise ValueError('结构已变化；当前局部模式仅支持情绪修改，请完整生成新基准。')
    old_items={i['id']:i for i in base_doc['pool']['items']}
    items={i['id']:i for i in doc['pool']['items']}
    for entry in doc['placements']:
        if flow.structure.entry_material(doc,entry)!=flow.structure.entry_material(base_doc,entry):
            raise ValueError('使用中的旋律素材已变化，请完整生成新基准。')
    rows=flow.structure.timeline(doc)['rows']
    changed=[r for r in rows if doc['expression'][r['id']]!=base_doc['expression'][r['id']]]
    if not changed:raise ValueError('与所选基准相比，没有已应用的情绪修改。')
    total=base_score['total_ticks'];windows=[]
    for row in changed:
        a=(row['start_bar']-1)*BAR;b=a+row['bars']*BAR
        windows.append([max(0,a-(BAR if connections else 0)),min(total,b+(BAR if connections else 0))])
    windows=merge_windows(windows)
    # Anchor all harmony outside requested windows to the saved, actual baseline.
    fixed={i:c for i,c in enumerate(base_score['report']['chords'])
           if not any(i*BAR<b and (i+1)*BAR>a for a,b in windows)}
    candidate=flow.compile_score(doc,connections,fixed_chords=fixed)
    # Do not cut a saved sustained event in half. Expand whole bars until no old
    # or new event crosses a window edge; disclose this expansion before commit.
    initial=copy.deepcopy(windows)
    all_notes=[n for score in (base_score,candidate) for l in score['layers'] for n in l['notes']]
    while True:
        enlarged=list(windows)
        for n in all_notes:
            if touches(n,windows):
                enlarged.append([max(0,n.start//BAR*BAR),min(total,((n.start+n.duration+BAR-1)//BAR)*BAR)])
        enlarged=merge_windows(enlarged)
        if enlarged==windows:break
        windows=enlarged
    result=copy.deepcopy(candidate);result['layers']=[]
    old_layers={l['name']:l for l in base_score['layers']}
    new_layers={l['name']:l for l in candidate['layers']}
    for name in sorted(set(old_layers)|set(new_layers)):
        old=old_layers.get(name);new=new_layers.get(name)
        if old and new and {k:v for k,v in old.items() if k!='notes'}!={k:v for k,v in new.items() if k!='notes'}:
            raise ValueError('声部预设已改变，无法保证局部保留，请完整生成。')
        layer=copy.deepcopy(old or new)
        layer['notes']=sorted([n for n in (old or {}).get('notes',[]) if not touches(n,windows)]+
                              [n for n in (new or {}).get('notes',[]) if touches(n,windows)],key=lambda n:(n.start,n.pitch))
        if layer['notes']:result['layers'].append(layer)
    before=events_outside(base_score,windows);after=events_outside(result,windows)
    if before!=after:raise ValueError('未影响区域音符保持检查失败。')
    expected=sorted((n.pitch,n.start,n.duration) for l in base_score['layers'] if l['name'].startswith('theme_') for n in l['notes'])
    actual=sorted((n.pitch,n.start,n.duration) for l in result['layers'] if l['name'].startswith('theme_') for n in l['notes'])
    if actual!=expected:raise ValueError('局部修改的主题检查失败。')
    rep=result['report'];old_report=base_score['report']
    for i in range(rep['bars']):
        if not any(i*BAR<b and (i+1)*BAR>a for a,b in windows):rep['chords'][i]=copy.deepcopy(old_report['chords'][i])
    old_boundaries={r['tick']:r for r in old_report['boundaries']}
    rep['boundaries']=[r if any(r['tick']-BAR<b and r['tick']+BAR>a for a,b in windows)
                       else copy.deepcopy(old_boundaries[r['tick']]) for r in rep['boundaries']]
    changed_ids={r['id'] for r in changed}
    preserved=[];edges=[]
    for r in rows:
        a=(r['start_bar']-1)*BAR;b=a+r['bars']*BAR
        if r['id'] not in changed_ids:
            (edges if any(a<end and b>start for start,end in windows) else preserved).append(r['name'])
    rep['engine']='local-emotion-rules-v1'
    rep['local_revision']=dict(base_output_directory=old_report['output_directory'],
        changed_entries=[dict(entry_id=r['id'],name=r['name']) for r in changed],
        initial_windows=initial,affected_ticks=windows,
        affected_bars=[[a//BAR+1,b//BAR] for a,b in windows],
        boundary_blocks=edges,preserved_blocks=preserved,
        preserved_event_count=len(before),preserved_events_sha256=digest(before),
        preservation_verified=True,expanded_for_sustain=windows!=initial,
        audio_scope='full render; synthesizer tails and master peak protection may affect mixed samples')
    rep['warnings']=['局部保留的是影响范围外的音符事件和声部设置，不是最终混音采样。',
        '整段重新渲染，音源释放、回声尾音和全局峰值保护可能影响其他采样。',
        '若延音跨越修复范围，范围会扩展至完整音符，并在预览中说明。']
    return result


def prepare_revision(doc,report,connections=True):
    base_doc,base_score=load_baseline(report)
    return compile_local(doc,base_doc,base_score,connections)


def summary(arrangement):
    info=arrangement['report']['local_revision']
    names='、'.join(r['name'] for r in info['changed_entries'])
    spans='；'.join(f'第 {a}～{b} 小节' for a,b in info['affected_bars'])
    return (f'目标块：{names}\n处理范围：{spans}\n'
            f'仅边界涉及：{"、".join(info["boundary_blocks"]) or "无"}\n'
            f'整块保留：{"、".join(info["preserved_blocks"]) or "无（仍保留范围外事件）"}\n'
            f'范围外保留 {info["preserved_event_count"]} 个音符事件；'
            +('因跨边界延音扩大范围。\n' if info['expanded_for_sustain'] else '\n')
            +'音频整段渲染；保留音符和编配，不保证混音采样不变。')
