"""Persisted library names, shared by backend transactions and presentation."""
import re

ATOM=r'(?:[ABCMS]\d+|#[\w-]{1,8})(?:′|\(\d+\))*'
SHORT=re.compile(r'^'+ATOM+r'(?:\+'+ATOM+r')*$')

def short_name(material):
    label=material['label']
    value=re.sub(r' · [MS]\d+$','',label)
    if SHORT.fullmatch(value):return value
    match=re.search(r' · ([MS]\d+)$',label)
    return match.group(1) if match else '#'+material['id'][:8]

def assign_material_names(project, additions, job_kind, target=None):
    """Name new objects only, before the single existing atomic commit."""
    counters=project['label_counters']
    library={m['id']:m for m in project['materials']}
    library.update({m['id']:m for m in additions})
    def category(material):
        generation=material.get('generation') or {}
        parent=library.get(material.get('phrase_id'))
        if parent:return category(parent)
        if generation.get('method') in ('bridge_phrase','bridge_emotion_once') or material['kind']=='bridge':return 'C'
        return 'B' if generation else 'A'
    def next_number(letter):
        key='ui-name:'+letter
        # Existing short labels are respected even if created by another compatible tool.
        largest=max((int(match.group(1)) for m in project['materials']
                     if (match:=re.fullmatch(letter+r'(\d+)',re.sub(r' · [MS]\d+$','',m['label'])))),default=0)
        counters[key]=max(counters.get(key,0),largest)+1
        return letter+str(counters[key])
    for material in additions:
        if job_kind=='COMBINE':
            name='+'.join(short_name(c['snapshot']) for c in material['children'])
        elif job_kind=='DERIVE' and target and material.get('phrase_id') is None:
            base=short_name(target)+'′'
            key='ui-derive:'+target['id']
            counters[key]=counters.get(key,0)+1
            name=base+('('+str(counters[key])+')' if counters[key]>1 else '')
        elif material.get('phrase_id') and not material['generation']:
            # Original phrase slices alias their visible standard block when
            # ranges match; hidden duplicates do not consume visible numbering.
            source=material['provenance'].get('source_id')
            start=material['provenance'].get('source_start_tick')
            standard=next((m for m in library.values() if m['kind']=='block' and not m['phrase_id']
                and not m['generation'] and m['provenance'].get('source_id')==source
                and m['provenance'].get('source_start_tick')==start and m['length_ticks']==material['length_ticks']),None)
            name=short_name(standard) if standard else next_number('A')
        elif material['kind']=='phrase':
            # Phrase containers are not cards and do not consume leaf numbering.
            name=material['label']
        else:
            name=next_number(category(material))
        material['label']=name
    return additions
