"""Human-readable source positions, not output-order numbers."""
VERSIONS=dict(original='原旋律',variant='变体',answer='回答句',secondary='副旋律')
BAR=1920


def labels(plan,block):
    if block.get('use_id'):
        parts=block.get('assembly_sources',[])
        origin='＋'.join(p['name'] for p in parts) or '连接'
        return dict(short=f'积木 {block["assembly_order"]+1} · '+origin,full=f'用户积木 {block["assembly_order"]+1} / '+origin+' / 内部'+block['kind'])
    sources={s['id']:(i+1,s['name']) for i,s in enumerate(plan['project']['sources'])}
    materials={m['id']:m for m in plan['materials']}
    if not block.get('source_spans'):
        kind='过渡＋结尾' if block['kind']=='transition_ending' else '旋律过渡' if block['kind']=='bridge' else '连接'
        return dict(short='新生成\n'+kind,full='新生成的'+kind+'；不是原旋律中的第几块。')
    short=[];full=[]
    for span in block['source_spans']:
        number,name=sources.get(span['source_id'],('?', '未知素材'))
        version=VERSIONS.get(materials.get(span['material_id'],{}).get('version'),'未知版本')
        first=span['start']//BAR+1;last=(span['end']-1)//BAR+1
        position=str(first) if first==last else str(first)+'–'+str(last)
        partial='（部分）' if span['start']%BAR or span['end']%BAR else ''
        short.append(f'M{number} · {version}\n第{position}块')
        full.append(f'M{number} · {name} / {version} / 第{position}块{partial} / 第{span["cycle"]+1}轮')
    suffix='；用于过渡起始，沿用已有旋律' if block['kind']=='transition_keep' else ''
    return dict(short=' → '.join(short),full=' → '.join(full)+suffix)
