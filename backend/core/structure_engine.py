"""Immutable backbone order with lineage-aware substitutions and insertions."""
import copy
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from runtime_config import data_root
ROOT = data_root()
import material_engine as materials

SCHEMA = 'emoblocks.structure.v1'
ROLES = ('未指定', '起句', '承接', '发展', '收束')


def uid(): return uuid.uuid4().hex


def entry_material(doc, entry):
    """Transitions belong to an explicit adjacent pair, not to the motif pool."""
    items={i['id']:i for i in doc['pool']['items']}
    if entry['kind']!='transition':return items[entry['material_id']]
    entries={e['id']:e for e in doc['placements']}
    left=items[entries[entry['left_entry']]['material_id']]
    right=items[entries[entry['right_entry']]['material_id']]
    start=materials.notes_of(left)[-1].pitch;end=materials.notes_of(right)[0].pitch
    scale=materials.scale_for(left);count=entry['bars']*4;notes=[]
    for i in range(count):
        pitch=start if i==0 else end if i==count-1 else materials.nearest(start+(end-start)*i/(count-1),scale)
        notes.append(asdict(materials.Note(pitch,i*materials.music.PPQ,materials.music.PPQ,80)))
    return dict(id=entry['id'],name=f'T({left["name"]} → {right["name"]})',kind='transition',
                bars=entry['bars'],bpm=left['bpm'],tonic=left['tonic'],mode=left['mode'],notes=notes,
                parents=[left['id'],right['id']],generator='bridge-v1')


def check_pool(pool):
    if pool.get('schema') != materials.SCHEMA:
        raise ValueError('素材池格式不支持。')
    rebuilt = materials.new_pool()
    for item in pool['items']:
        materials.add_item(rebuilt, item)
    if len({it['id'] for it in pool['items']}) != len(pool['items']):
        raise ValueError('素材 ID 重复。')
    return {it['id']: it for it in pool['items']}


def family(items, material_id):
    """Variants inherit their closest non-variant family, not every ancestor."""
    seen = set()
    while True:
        if material_id in seen or material_id not in items:
            raise ValueError('来源关系缺失或循环。')
        seen.add(material_id)
        item = items[material_id]
        if item['kind'] != 'variant': return item
        if len(item['parents']) != 1: raise ValueError('首版只支持单来源变体。')
        material_id = item['parents'][0]


def source_theme(items, material_id):
    seen = set()
    while material_id not in seen:
        seen.add(material_id)
        item = items.get(material_id)
        if item is None: break
        if item['kind'] == 'theme': return item['id']
        if len(item['parents']) != 1: break
        material_id = item['parents'][0]
    raise ValueError('无法确定关联素材对应的原主题。')


def create(pool, theme_ids):
    items = check_pool(pool)
    if not theme_ids or len(set(theme_ids)) != len(theme_ids):
        raise ValueError('骨架至少包含一个原主题，同一主题不能重复指定。')
    if any(i not in items or items[i]['kind'] != 'theme' or not items[i]['accepted'] for i in theme_ids):
        raise ValueError('骨架只能使用已保留的原主题。')
    slots = [dict(id=uid(), theme_id=i, role='未指定') for i in theme_ids]
    doc = dict(schema=SCHEMA, id=uid(), pool=copy.deepcopy(pool), backbone=slots,
               locked_order=[s['id'] for s in slots], placements=[], permissions={}, history=[])
    doc['placements'] = [dict(id=uid(), kind='slot', slot_id=s['id'], material_id=s['theme_id']) for s in slots]
    for item in items.values():
        if family(items, item['id'])['kind'] == 'answer':
            original = source_theme(items, item['id'])
            doc['permissions'][item['id']] = [s['id'] for s in slots if s['theme_id'] == original]
    validate(doc)
    return doc


def validate(doc):
    if doc.get('schema') != SCHEMA: raise ValueError('不是受支持的结构工程。')
    items = check_pool(doc['pool'])
    slots = doc['backbone']; order = [s['id'] for s in slots]
    if not order or len(set(order)) != len(order) or order != doc['locked_order']:
        raise ValueError('已确认的骨架顺序不能重排。')
    themes = [s['theme_id'] for s in slots]
    if len(set(themes)) != len(themes): raise ValueError('骨架主题重复。')
    for slot in slots:
        if slot['theme_id'] not in items or items[slot['theme_id']]['kind'] != 'theme':
            raise ValueError('骨架必须引用原主题。')
        if slot['role'] not in ROLES: raise ValueError('未知段落角色。')
    slot_map = {s['id']:s for s in slots}
    permissions = doc['permissions']
    for mid, allowed in permissions.items():
        if mid not in items or family(items, mid)['kind'] != 'answer' or not isinstance(allowed,list) or any(s not in slot_map for s in allowed):
            raise ValueError('关联素材的插入授权无效。')
    sequence, seen, anchor = [], set(), None
    for index,entry in enumerate(doc['placements']):
        if entry['id'] in seen: raise ValueError('排列实例 ID 重复。')
        seen.add(entry['id'])
        if entry['kind']=='transition':
            if type(entry.get('bars')) is not int or entry['bars'] not in (1,2):raise ValueError('过渡块仅支持 1 或 2 小节。')
            if entry.get('generator')!='bridge-v1':raise ValueError('未知过渡生成方式。')
            if not 0<index<len(doc['placements'])-1:raise ValueError('过渡块必须位于两个内容块之间。')
            left,right=doc['placements'][index-1],doc['placements'][index+1]
            if left['kind']=='transition' or right['kind']=='transition':raise ValueError('不能连续插入过渡块。')
            if entry.get('left_entry')!=left['id'] or entry.get('right_entry')!=right['id']:
                raise ValueError('过渡两端已变化，请先移除相关过渡块再调整插入项。')
            continue
        item = items.get(entry['material_id'])
        if item is None or not item['accepted']: raise ValueError('排列只能使用已保留素材。')
        if entry['kind'] == 'slot':
            sid = entry['slot_id']
            if sid not in slot_map or family(items, item['id'])['id'] != slot_map[sid]['theme_id']:
                raise ValueError('变体只能替换其来源主题所在的位置，回答句不能冒充原主题。')
            sequence.append(sid); anchor = sid
        elif entry['kind'] == 'insert':
            if family(items, item['id'])['kind'] != 'answer': raise ValueError('插入项必须为关联回答句或其变体。')
            if entry['after_slot'] != anchor or anchor not in permissions.get(item['id'], []):
                raise ValueError('关联素材不允许插入此位置，需先明确授权。')
        else: raise ValueError('未知排列项。')
    if sequence != order: raise ValueError('原段必须保序且完整，当前不允许省略、重复或 A→C→D→B 式重排。')
    return doc


def edit(doc, operation, **args):
    """Transactional editing: rejected operations never mutate existing content."""
    validate(doc)
    result = copy.deepcopy(doc)
    items = {i['id']:i for i in result['pool']['items']}
    slots = {s['id']:s for s in result['backbone']}
    sid = args.get('slot_id')
    if operation in ('replace','insert','authorize','role') and sid not in slots:
        raise ValueError('请选择骨架位置。')
    mid = args.get('material_id')
    if operation == 'replace':
        entry = next(e for e in result['placements'] if e['kind']=='slot' and e['slot_id']==sid)
        entry['material_id'] = mid
    elif operation == 'authorize':
        if mid not in items or family(items,mid)['kind'] != 'answer': raise ValueError('只能授权关联回答句及其变体。')
        if args.get('confirmed') is not True: raise ValueError('改变允许插入位置必须由用户明确确认。')
        allowed = result['permissions'].setdefault(mid,[])
        if sid not in allowed: allowed.append(sid)
    elif operation == 'insert':
        position = next(i for i,e in enumerate(result['placements']) if e['kind']=='slot' and e['slot_id']==sid) + 1
        while position < len(result['placements']) and result['placements'][position]['kind']=='insert': position += 1
        result['placements'].insert(position, dict(id=uid(),kind='insert',after_slot=sid,material_id=mid))
    elif operation == 'remove_insert':
        index = next((i for i,e in enumerate(result['placements']) if e['id']==args.get('entry_id')), None)
        if index is None or result['placements'][index]['kind'] != 'insert': raise ValueError('只能移除插入项，原段不能删除。')
        result['placements'].pop(index)
    elif operation == 'add_transition':
        index=next((i for i,e in enumerate(result['placements']) if e['id']==args.get('entry_id')),None)
        if index is None or index+1>=len(result['placements']):raise ValueError('请选择有后续块的内容块。')
        left,right=result['placements'][index:index+2]
        if left['kind']=='transition' or right['kind']=='transition':raise ValueError('此处已有过渡块，请先移除。')
        result['placements'].insert(index+1,dict(id=uid(),kind='transition',left_entry=left['id'],right_entry=right['id'],
                                                bars=args.get('bars',1),generator='bridge-v1'))
    elif operation == 'remove_transition':
        index=next((i for i,e in enumerate(result['placements']) if e['id']==args.get('entry_id')),None)
        if index is None or result['placements'][index]['kind']!='transition':raise ValueError('请选择独立过渡块。')
        result['placements'].pop(index)
    elif operation == 'role':
        slots[sid]['role'] = args['role']
    else: raise ValueError('不支持此操作；骨架确认后不能自由重排。')
    validate(result)
    result['history'].append(dict(operation=operation, parameters=args))
    return result


def timeline(doc):
    validate(doc)
    items = {i['id']:i for i in doc['pool']['items']}
    cursor, rows = 0, []
    for entry in doc['placements']:
        item = entry_material(doc,entry)
        rows.append(dict(entry, name=item['name'], start_bar=cursor+1, bars=item['bars']))
        cursor += item['bars']
    return dict(rows=rows, bars=cursor, seconds=cursor*240/next(iter(items.values()))['bpm'],
                note='包含独立过渡块的结构时长；插入增加时长，后续顺延，尚需生成音频。')


def save(doc, path=None):
    validate(doc)
    if path is None:
        folder = ROOT/'structures'; folder.mkdir(exist_ok=True)
        path = folder/('structure-'+uid()+'.json')
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(doc,f,ensure_ascii=False,indent=2)
    return Path(path)


def load(path):
    path = Path(path)
    if path.stat().st_size > 12*1024*1024: raise ValueError('结构工程过大。')
    return validate(json.loads(path.read_text(encoding='utf-8')))
