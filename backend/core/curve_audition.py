"""Real neutral single-melody audition; never a completed composition or planner."""
import copy
import json
import os
from pathlib import Path
import subprocess
import threading
import wave

import curve_project as model
from runtime_config import data_root, find_lmms

RENDERER_VERSION = 'curve-neutral-lmms-v2'
_RENDER_LOCK = threading.Lock()


def audition_fingerprint(snapshot, bpm=120):
    model.integer(bpm, 40, 220)
    notes = playable_notes(snapshot)
    if not notes:
        model.reject('此片段只有休止，没有可试听的旋律。', 'EMPTY_MATERIAL')
    musical = []
    for n in notes:
        model.integer(n.get('pitch'), 12, 119)
        model.integer(n.get('velocity'), 1, 127)
        model.integer(n.get('start_tick')); model.integer(n.get('duration_tick'), 1)
        if n['start_tick'] + n['duration_tick'] > snapshot['length_ticks']:
            model.reject('试听快照音符超出素材。')
        musical.append({k: n[k] for k in ('pitch', 'start_tick', 'duration_tick', 'velocity')})
    return model.digest('emoblocks.audition.v2', dict(notes=sorted(musical, key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['velocity'])),
        length_ticks=snapshot['length_ticks'], bpm=bpm, tone='neutral-soft-velocity-preserved', renderer_version=RENDERER_VERSION))


def _owned_notes(snapshot, path=(), ancestors=()):
    """Resolve real occurrence ownership, preserving the root's opaque note IDs."""
    model.canonical(snapshot)
    if not isinstance(snapshot, dict): model.reject('试听快照必须是实际来源或素材。')
    kind = snapshot.get('kind')
    if kind is None:
        model.shape(snapshot, 'id label length_ticks notes provenance')
    else:
        model.shape(snapshot, 'id label kind length_ticks notes provenance generation phrase_id children')
        if kind not in ('block', 'phrase', 'combination', 'bridge'):
            model.reject('未知试听素材种类。')
        if snapshot['generation'] is not None and not isinstance(snapshot['generation'], dict):
            model.reject('试听素材生成记录无效。')
        if snapshot['phrase_id'] is not None: model.ident(snapshot['phrase_id'])
    model.ident(snapshot['id']); model.text(snapshot['label'])
    if len(ancestors) > 16 or snapshot['id'] in ancestors:
        model.reject('试听组合有环或超过16层。')
    if not isinstance(snapshot['provenance'], dict): model.reject('试听来源记录无效。')
    length = snapshot['length_ticks']; model.integer(length, 1)
    notes = model.objects(snapshot['notes']); model.indexed(notes)
    for n in notes:
        model.shape(n, 'id pitch start_tick duration_tick velocity origin lineage slice')
        model.ident(n['id']); model.integer(n['pitch'], 12, 119); model.integer(n['velocity'], 1, 127)
        model.integer(n['start_tick']); model.integer(n['duration_tick'], 1)
        if n['start_tick'] + n['duration_tick'] > length: model.reject('试听音符超出素材。')
        if n['origin'] is not None:
            model.shape(n['origin'], 'source_id track_id source_note_id')
            for value in n['origin'].values(): model.ident(value)
        for value in model.objects(n['lineage']): model.ident(value)
        if n['slice'] is not None:
            s = n['slice']; model.shape(s, 'parent_emission_id offset_tick parent_duration_tick')
            model.ident(s['parent_emission_id']); model.integer(s['offset_tick']); model.integer(s['parent_duration_tick'], 1)
            if s['offset_tick'] + n['duration_tick'] > s['parent_duration_tick']:
                model.reject('试听切片超出原发声。')
    notes = sorted(notes, key=lambda n: (n['start_tick'], n['pitch']))
    if any(a['start_tick'] + a['duration_tick'] > b['start_tick'] for a, b in zip(notes, notes[1:])):
        model.reject('试听素材必须是实际单旋律。', 'MONOPHONIC_IMPORT_REQUIRED')
    children = model.objects(snapshot.get('children', []))
    if kind != 'combination':
        if children: model.reject('非组合试听素材不能包含组件。')
        return [(copy.deepcopy(n), path) for n in notes]
    if not children: model.reject('试听组合缺少真实组件。')
    owners = {}; offset = 0; seen = set()
    for child in children:
        model.shape(child, 'occurrence_id offset_tick snapshot'); model.ident(child['occurrence_id'])
        model.integer(child['offset_tick'])
        if child['occurrence_id'] in seen or child['offset_tick'] != offset:
            model.reject('试听组件身份重复或范围不连续。')
        seen.add(child['occurrence_id'])
        for n, owner in _owned_notes(child['snapshot'], path + (child['occurrence_id'],), ancestors + (snapshot['id'],)):
            n['start_tick'] += offset
            key = model.canonical({k:v for k,v in n.items() if k != 'id'})
            if key in owners: model.reject('试听音符演奏归属有歧义。')
            owners[key] = owner
        offset += child['snapshot']['length_ticks']
    result = []
    for n in notes:
        key = model.canonical({k:v for k,v in n.items() if k != 'id'})
        if key not in owners: model.reject('试听音符与真实组件来源或范围不符。')
        result.append((copy.deepcopy(n), owners.pop(key)))
    if owners or offset != length: model.reject('试听组合音符或长度与组件不符。')
    return result


def playable_notes(snapshot):
    """Tie continuous source slices only within one actual performance."""
    result = []
    previous_owner = None
    for note, owner in _owned_notes(snapshot):
        if result:
            previous = result[-1]
            a, b = previous.get('slice'), note.get('slice')
            if (previous_owner == owner and a and b and previous['origin'] == note['origin'] and previous['pitch'] == note['pitch']
                and a['parent_emission_id'] == b['parent_emission_id']
                and a['parent_duration_tick'] == b['parent_duration_tick']
                and a['offset_tick'] + previous['duration_tick'] == b['offset_tick']
                and previous['start_tick'] + previous['duration_tick'] == note['start_tick']):
                previous['duration_tick'] += note['duration_tick']
                continue
        result.append(note)
        previous_owner = owner
    return result


def render_audition(snapshot, bpm=120):
    snapshot = copy.deepcopy(snapshot)
    fingerprint = audition_fingerprint(snapshot, bpm)
    notes = playable_notes(snapshot); total = snapshot['length_ticks']
    if total % 10 or any(n['start_tick'] % 10 or n['duration_tick'] % 10 for n in notes):
        model.reject('当前试听引擎无法无损表达这个精确节奏；素材已保留，请使用可表达节奏的片段试听。', 'OUTPUT_TIME_UNREPRESENTABLE')
    executable = find_lmms()
    if not executable.is_file():
        model.reject('找不到 LMMS。请恢复已有 LMMS 安装后重新准备试听。', 'RENDERER_UNAVAILABLE')
    import engine as music
    import flow_engine
    folder = data_root() / 'auditions' / model.uid()
    folder.mkdir(parents=True)
    arrangement = dict(bpm=bpm, total_ticks=total, layers=[dict(name='中性素材试听', preset='soft', volume=70, pan=0, drum=None,
        notes=[music.Note(n['pitch'], n['start_tick'], n['duration_tick'], n['velocity']) for n in notes])])
    music.export_midi(arrangement, folder / 'composition.mid')
    music.export_mmp(arrangement, folder / 'composition.mmp')
    (folder / 'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    # Multiple callers share one renderer slot; no simultaneous device/render work.
    with _RENDER_LOCK:
        proc = subprocess.run([str(executable), 'render', str(folder / 'composition.mmp'), '-o', str(folder / 'dry.wav'), '-s', '44100'],
            capture_output=True, timeout=240, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (folder / 'render.log').write_bytes(proc.stdout + proc.stderr)
    if proc.returncode or not (folder / 'dry.wav').is_file():
        model.reject('试听渲染失败，请查看日志后重试：' + str(folder / 'render.log'), 'AUDITION_RENDER_FAILED')
    body_seconds = total / model.PPQ * 60 / bpm
    audio = flow_engine.finish_audio(folder / 'dry.wav', folder / 'preview.wav', body_seconds, wet=0)
    if audio['peak'] < .0001:
        model.reject('试听结果没有可听见的声音，请检查旋律或更换片段。', 'AUDITION_RENDER_FAILED')
    with wave.open(str(folder / 'preview.wav'), 'rb') as stream:
        audio_seconds = stream.getnframes() / stream.getframerate()
    asset = dict(wav_path=str(folder / 'preview.wav'), midi_path=str(folder / 'composition.mid'), mmp_path=str(folder / 'composition.mmp'),
        body_ticks=total, body_seconds=body_seconds, audio_seconds=audio_seconds, fingerprint=fingerprint, renderer_version=RENDERER_VERSION)
    (folder / 'asset.json').write_text(json.dumps(asset, ensure_ascii=False, indent=2), encoding='utf-8')
    return asset
