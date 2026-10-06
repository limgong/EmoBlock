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

RENDERER_VERSION = 'curve-neutral-lmms-v1'
_RENDER_LOCK = threading.Lock()


def audition_fingerprint(snapshot, bpm=120):
    model.integer(bpm, 40, 220)
    notes = snapshot.get('notes')
    model.objects(notes); model.integer(snapshot.get('length_ticks'), 1)
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
    return model.digest('emoblocks.audition.v1', dict(notes=sorted(musical, key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['velocity'])),
        length_ticks=snapshot['length_ticks'], bpm=bpm, tone='neutral-soft-velocity-preserved', renderer_version=RENDERER_VERSION))


def playable_notes(snapshot):
    """Tie only continuous slices of the same source emission, never same pitch alone."""
    result = []
    for note in sorted(snapshot['notes'], key=lambda n: (n['start_tick'], n['pitch'])):
        note = copy.deepcopy(note)
        if result:
            previous = result[-1]
            a, b = previous.get('slice'), note.get('slice')
            if (a and b and previous['origin'] == note['origin'] and previous['pitch'] == note['pitch']
                and previous['velocity'] == note['velocity']
                and a['parent_emission_id'] == b['parent_emission_id']
                and a['parent_duration_tick'] == b['parent_duration_tick']
                and a['offset_tick'] + previous['duration_tick'] == b['offset_tick']
                and previous['start_tick'] + previous['duration_tick'] == note['start_tick']):
                previous['duration_tick'] += note['duration_tick']
                continue
        result.append(note)
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
