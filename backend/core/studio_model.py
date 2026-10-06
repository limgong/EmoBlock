"""Shared state operations for quick creation and detailed editing."""
import copy
import json
import math
import os
from pathlib import Path
import flow_engine as flow
import structure_engine as structure

materials=structure.materials
SCHEMA='emoblocks.studio.v1'


def validate_curve(curve):
    if not 1<=len(curve)<=6:raise ValueError('快速模式支持 1～6 段。')
    for point in curve:
        if point['emotion'] not in flow.music.EMOTIONS:raise ValueError('未知情绪。')
        if any(not math.isfinite(point[k]) or not 0<=point[k]<=1 for k in ('start','end')):
            raise ValueError('强度需在 0～100%。')


def quick_document(theme,curve,seed=31):
    validate_curve(curve)
    pool=materials.new_pool();materials.add_item(pool,copy.deepcopy(theme))
    doc=structure.create(pool,[theme['id']])
    if len(curve)>1:
        candidates=materials.generate_candidates(theme,'answer',seed,len(curve)-1)
        if len(candidates)!=len(curve)-1:raise ValueError('未得到足够的不同回答句。请减少段数或换一个候选种子。')
        for index,item in enumerate(candidates):
            item['name']=chr(ord('E')+index);item['accepted']=True
            item['selection']='quick-mode automatic selection; not human listening approval'
            materials.add_item(pool,item)
        doc=structure.create(pool,[theme['id']])
        for item in candidates:doc=structure.edit(doc,'insert',slot_id=doc['backbone'][0]['id'],material_id=item['id'])
    doc=flow.prepare(doc)
    for i,point in enumerate(curve):doc=flow.set_region(doc,i,i,point['emotion'],point['start'],point['end'])
    doc['creation_mode']='quick: one reference plus motif-related answer phrases'
    return doc


def multi_document(themes,curve):
    """Use each supplied theme once, in the explicitly listed order."""
    validate_curve(curve)
    if len(themes)!=len(curve):raise ValueError('多旋律模式中，情绪段数必须与输入主题数相同。')
    pool=materials.new_pool()
    for theme in themes:materials.add_item(pool,copy.deepcopy(theme))
    doc=flow.prepare(structure.create(pool,[i['id'] for i in themes]))
    for i,point in enumerate(curve):doc=flow.set_region(doc,i,i,point['emotion'],point['start'],point['end'])
    doc['creation_mode']='multiple given themes in user-confirmed order; no automatic reordering'
    return doc


def validate_inputs(settings,curve):
    themes=settings.get('input_themes',[])
    if not isinstance(themes,list) or len(themes)>6:raise ValueError('多段输入列表格式无效。')
    if themes:
        if len(themes)!=len(curve):raise ValueError('多段输入与情绪模板数量不一致。')
        pool=materials.new_pool()
        for theme in themes:
            if theme['kind']!='theme':raise ValueError('多段输入列表必须是给定原主题。')
            materials.add_item(pool,theme)


def playback_blocks(report):
    blocks=report.get('playback_blocks')
    if blocks is None:
        path=Path(report['output_directory'])/'structure.json'
        if not path.is_file():return []
        doc=structure.load(path);rows=structure.timeline(doc)['rows']
        bpm=doc['pool']['items'][0]['bpm']
        blocks=[dict(entry_id=r['id'],name=r['name'],start_seconds=(r['start_bar']-1)*240/bpm,
            end_seconds=(r['start_bar']-1+r['bars'])*240/bpm,emotion=doc.get('expression',{}).get(r['id'],{}).get('emotion','calm'),
            bar_settings=flow.bar_settings(doc.get('expression',{}).get(r['id'],dict(emotion='calm',start=.35,end=.35)),r['bars']),
            beat_nodes=copy.deepcopy(doc.get('expression',{}).get(r['id'],{}).get('beat_nodes'))) for r in rows]
    previous=0.
    for block in blocks:
        a,b=block['start_seconds'],block['end_seconds']
        if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in (a,b)) or abs(a-previous)>.01 or b<=a:
            raise ValueError('结果中的分块时间信息无效。')
        previous=b
    if blocks and abs(previous-report['duration_seconds'])>.02:raise ValueError('分块时间与音频主体长度不符。')
    return copy.deepcopy(blocks)


def active_block(blocks,seconds):
    return next((i for i,b in enumerate(blocks) if b['start_seconds']<=seconds<b['end_seconds']),None)


def playback_emotion(block,seconds):
    if block.get('intensity_points'):
        import intensity_curve
        return dict(emotion=block['emotion'],bar=None,intensity=intensity_curve.evaluate(block['intensity_points'],seconds))
    if 'intensity_start' in block:
        fraction=max(0,min(1,(seconds-block['start_seconds'])/(block['end_seconds']-block['start_seconds'])))
        return dict(emotion=block['emotion'],bar=None,intensity=block['intensity_start']+(block['intensity_end']-block['intensity_start'])*fraction)
    if block.get('beat_nodes'):
        bars=len(block['bar_settings']);beat=max(0,min(bars*4,(seconds-block['start_seconds'])/(block['end_seconds']-block['start_seconds'])*bars*4))
        value=flow.expression_at(dict(beat_nodes=block['beat_nodes']),bars,beat)
        return dict(value,bar=min(bars,int(beat//4)+1),beat=min(bars*4,int(beat)+1))
    settings=block.get('bar_settings')
    if not settings:return dict(emotion=block.get('emotion','calm'),bar=None)
    position=(seconds-block['start_seconds'])/(block['end_seconds']-block['start_seconds'])*len(settings)
    index=max(0,min(len(settings)-1,int(position)));value=settings[index]
    return dict(emotion=value['emotion'],bar=index+1,
                intensity=value['start']+(value['end']-value['start'])*max(0,min(1,position-index)))


def merge_pool(doc,pool):
    structure.check_pool(pool)
    result=copy.deepcopy(doc);result['pool']=copy.deepcopy(pool)
    items={i['id']:i for i in pool['items']}
    for item in items.values():
        if item['id'] not in result['permissions'] and structure.family(items,item['id'])['kind']=='answer':
            original=structure.source_theme(items,item['id'])
            result['permissions'][item['id']]=[s['id'] for s in result['backbone'] if s['theme_id']==original]
    return flow.prepare(result)


def save_project(pool,doc,curve,results,settings=None,path=None):
    if settings and 'story' in settings:
        import story_engine
        story_engine.validate(settings['story'],require_source=False)
    structure.check_pool(pool);validate_curve(curve)
    validate_inputs(settings or {},curve)
    if doc:
        flow.validate(doc)
        if doc['pool']!=pool:raise ValueError('素材池与结构不同步，无法保存。')
    data=dict(schema=SCHEMA,pool=pool,doc=doc,curve=curve,results=results,settings=settings or {})
    serialized=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)
    if path is None:
        folder=structure.ROOT/'projects';folder.mkdir(exist_ok=True)
        path=folder/('studio-'+structure.uid()+'.json')
    path=Path(path);created=False
    try:
        with path.open('x',encoding='utf-8') as f:
            created=True;f.write(serialized);f.flush();os.fsync(f.fileno())
    except Exception:
        if created:path.unlink(missing_ok=True)  # Only our incomplete new snapshot, never an old file.
        raise
    return Path(path)


def load_project(path):
    path=Path(path)
    if path.stat().st_size>20*1024*1024:raise ValueError('工程文件过大。')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')==SCHEMA:
        if not isinstance(data.get('settings'),dict) or not isinstance(data.get('results'),list) or len(data['results'])>500:
            raise ValueError('工程设置或结果列表格式无效。')
        for result in data['results']:
            report=result.get('report',{})
            if not isinstance(result.get('mode'),str) or not isinstance(report.get('output_directory'),str):raise ValueError('结果记录无效。')
            if any(not isinstance(report.get(k),(int,float)) or not math.isfinite(report[k]) or report[k]<=0 for k in ('duration_seconds','bars')):
                raise ValueError('结果时长记录无效。')
        structure.check_pool(data['pool']);validate_curve(data['curve'])
        if 'story' in data['settings']:
            import story_engine
            story_engine.validate(data['settings']['story'],require_source=False)
        validate_inputs(data['settings'],data['curve'])
        if data['doc']:
            flow.validate(data['doc'])
            if data['doc']['pool']!=data['pool']:raise ValueError('工程素材与结构不一致。')
        return data
    if data.get('schema')==structure.SCHEMA:
        doc=flow.prepare(data)
        curve=list(doc['expression'].values())[:6]
        return dict(pool=copy.deepcopy(doc['pool']),doc=doc,curve=curve,results=[],settings={})
    if data.get('schema')==materials.SCHEMA:
        pool=materials.load_pool(path)
        return dict(pool=pool,doc=None,curve=[dict(emotion='calm',start=.3,end=.5)],results=[],settings={})
    raise ValueError('请选择工作台、结构或素材池的 JSON 工程。')
