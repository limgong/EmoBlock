"""Step 2: reference motifs -> bounded variations/answer phrases, no emotion model."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEP1 = ROOT.parent / 'step1'
MODULE = 'emoblocks_step1_engine'
if MODULE not in sys.modules:
    spec = importlib.util.spec_from_file_location(MODULE, STEP1 / 'engine.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(MODULE, None)
        raise
music = sys.modules[MODULE]
BAR, Note = music.BAR, music.Note
SCHEMA = 'emoblocks.material-pool.v1'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def notes_of(item):
    return [Note(**n) for n in item['notes']]


def signature(notes):
    return [(n.pitch, n.start, n.duration) for n in notes]


def validate(item):
    ns = notes_of(item)
    music._check_notes(ns)
    if type(item['bars']) is not int or not 4 <= item['bars'] <= 8:
        raise ValueError('素材必须为 4～8 小节。')
    if not math.isfinite(item['bpm']) or not 40 <= item['bpm'] <= 220:
        raise ValueError('BPM 无效。')
    if item['mode'] not in ('major', 'minor') or type(item['tonic']) is not int or not 0 <= item['tonic'] < 12:
        raise ValueError('调性参考无效。')
    if any(type(x) is not int for n in ns for x in (n.pitch, n.start, n.duration, n.velocity)):
        raise ValueError('音符事件必须使用整数。')
    if ns != sorted(ns, key=lambda n: (n.start, n.pitch)):
        raise ValueError('音符未排序。')
    if any(b.start < a.start + a.duration for a, b in zip(ns, ns[1:])):
        raise ValueError('首版内容生成使用单声部旋律，不能含重叠音符。')
    if max(n.start + n.duration for n in ns) > item['bars'] * BAR:
        raise ValueError('音符越过素材长度。')
    if max(n.start + n.duration for n in ns) <= (item['bars'] - 1) * BAR:
        raise ValueError('末小节必须含音符，以兼容步骤一的长度识别。')
    if item['kind'] not in ('theme', 'variant', 'answer'):
        raise ValueError('未知素材类型。')
    return item


def make_item(name, kind, ns, bars, bpm, tonic, mode, **extra):
    item = dict(id=uuid.uuid4().hex, name=name, kind=kind, notes=[asdict(n) for n in ns],
                bars=bars, bpm=bpm, tonic=tonic, mode=mode, parents=[], accepted=False,
                version=1, methods=[], **extra)
    return validate(item)


def import_theme(path, track=0, start_bar=1, bars=4, name='A', trim_overlaps=False, key=None, simultaneous='reject'):
    source = music.load_source(path)
    if not 0 <= track < len(source.tracks):
        raise ValueError('请选择有效旋律轨。')
    if type(start_bar) is not int or start_bar < 1 or type(bars) is not int or not 4 <= bars <= 8:
        raise ValueError('起始小节从 1 开始，截取长度为 4～8 小节。')
    start, end = (start_bar - 1) * BAR, (start_bar - 1 + bars) * BAR
    original = source.tracks[track].notes
    if end > math.ceil(max(n.start + n.duration for n in original) / BAR) * BAR:
        raise ValueError('所选小节超出旋律音符覆盖范围。')
    selected, clipped = [], 0
    for n in original:
        left, right = max(start, n.start), min(end, n.start + n.duration)
        if left < right:
            clipped += int(left != n.start or right != n.start + n.duration)
            selected.append(Note(n.pitch, left - start, right - left, 80))
    selected.sort(key=lambda n: (n.start, n.pitch))
    if simultaneous not in ('reject', 'lower', 'upper'):
        raise ValueError('未知同时起音处理方式。')
    discarded = 0
    if simultaneous != 'reject':
        grouped = {}
        for n in selected:
            grouped.setdefault(n.start, []).append(n)
        discarded = sum(len(group)-1 for group in grouped.values())
        selected = [(min if simultaneous == 'lower' else max)(group, key=lambda n:n.pitch)
                    for group in grouped.values()]
    trimmed = 0
    for i in range(len(selected) - 1):
        n, nxt = selected[i:i + 2]
        if nxt.start == n.start:
            raise ValueError('选区含同时起音的多声部；请在编辑器中分离主旋律，不自动猜测最高音。')
        if n.start + n.duration > nxt.start:
            if not trim_overlaps:
                raise ValueError('旋律含尾音重叠；可勾选“截短重叠尾音”后重试，或先手工分离声部。')
            selected[i] = Note(n.pitch, n.start, nxt.start - n.start, 80)
            trimmed += 1
    music._check_notes(selected)
    inferred = music.infer_key(selected)
    tonic, mode = key if key is not None else inferred[:2]
    item = make_item(name, 'theme', selected, bars, source.bpm, tonic, mode)
    item['accepted'] = True
    item['source'] = dict(path=source.path, sha256=source.sha256, track=track,
                          start_bar=start_bar, bars=bars)
    item['import_report'] = dict(clipped_boundary_notes=clipped, shortened_overlaps=trimmed,
                                  simultaneous_policy=simultaneous, discarded_simultaneous_notes=discarded,
                                  normalized_velocity=80, warnings=source.warnings,
                                  key_estimate=list(inferred), key_is_estimate=key is None)
    return item


def scale_for(item):
    steps = (0, 2, 4, 5, 7, 9, 11) if item['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    return [p for p in range(12, 120) if (p - item['tonic']) % 12 in steps]


def nearest(pitch, pitches):
    return min(pitches, key=lambda p: (abs(p - pitch), p))


def transpose_degree(pitch, shift, scale):
    i = scale.index(nearest(pitch, scale))
    return scale[max(0, min(len(scale) - 1, i + shift))]


def variant(parent, rng):
    original = notes_of(parent)
    ns = list(original)
    # Preserve the opening bar; develop a later one and redesign the ending.
    chosen = rng.randrange(1, parent['bars'] - 1)
    shift = rng.choice([-2, -1, 1, 2])
    scale = scale_for(parent)
    operation = rng.choice(['sequence', 'rhythm'])
    out = []
    developed = False
    for n in ns:
        if n.start // BAR == chosen and operation == 'sequence':
            out.append(Note(transpose_degree(n.pitch, shift, scale), n.start, n.duration, 80))
            developed = True
        elif n.start // BAR == chosen and operation == 'rhythm' and n.duration >= 480:
            cut = (n.duration // 240 // 2) * 240
            out.extend([Note(n.pitch, n.start, cut, 80),
                        Note(transpose_degree(n.pitch, rng.choice([-1, 1]), scale),
                             n.start + cut, n.duration - cut, 80)])
            developed = True
        else:
            out.append(n)
    # Alter up to three terminal notes; stable chord tones on the final note.
    indices = [i for i, n in enumerate(out) if n.start >= (parent['bars'] - 1) * BAR]
    for i in indices[-3:]:
        n = out[i]
        pitch = transpose_degree(n.pitch, rng.choice([-2, -1, 1, 2]), scale)
        out[i] = Note(pitch, n.start, n.duration, 80)
    if indices:
        i = indices[-1]; n = out[i]
        pcs = {(parent['tonic'] + v) % 12 for v in (0, 4 if parent['mode'] == 'major' else 3, 7)}
        out[i] = Note(nearest(n.pitch, [p for p in scale if p % 12 in pcs]), n.start, n.duration, 80)
    methods = [('调内动机模进' if operation == 'sequence' else '局部节奏拆分')] if developed else []
    return out, methods + ['句尾变奏'], {'development_bar': chosen + 1, 'development_applied': developed}


def answer(parent, rng):
    """Motif-derived rhythm + phrase contour + constrained beam-search pitches."""
    original = notes_of(parent)
    bars = parent['bars']
    scale = scale_for(parent)
    center = sorted(n.pitch for n in original)[len(original) // 2]
    low = max(12, min(n.pitch for n in original) - 3)
    high = min(119, max(n.pitch for n in original) + 5)
    pitches = [p for p in scale if low <= p <= high]
    groups = []
    for b in range(bars):
        group = [(n.start % BAR, min(n.duration, BAR - n.start % BAR))
                 for n in original if n.start // BAR == b]
        if group:
            groups.append(group)
    # Reuse source rhythmic vocabulary; final bar has an explicit cadence.
    motif = rng.choice(groups)
    slots = []
    for b in range(bars):
        if b == bars - 1:
            group = [(0, 480), (480, 480), (960, 960)]
        elif b % 2 == 0:
            group = motif
        else:
            base = rng.choice(groups)
            group = list(base)
            long = next((i for i, (_, d) in enumerate(group) if d >= 480), None)
            if long is not None:
                s, d = group.pop(long); cut = max(120, d // 240 * 120)
                group[long:long] = [(s, cut), (s + cut, d - cut)]
        slots.extend((b * BAR + s, d) for s, d in group)
    # Diatonic I / IV / ii / V vocabulary, with final dominant-to-tonic landing.
    steps = (0, 2, 4, 5, 7, 9, 11) if parent['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    degrees = [rng.choice([0, 3, 5]) for _ in range(bars)]
    degrees[0], degrees[-2], degrees[-1] = 0, 4, 0
    chords = [{(parent['tonic'] + steps[(degree + k) % 7]) % 12 for k in (0, 2, 4)}
              for degree in degrees]
    intervals = [max(-5, min(5, b.pitch - a.pitch)) for a, b in zip(original, original[1:])][:8] or [0, 2, -2]
    orientation = rng.choice([-1, 1])
    beam = [(0., [])]
    for i, (start, duration) in enumerate(slots):
        final = i == len(slots) - 1
        allowed = [p for p in pitches if p % 12 == parent['tonic']] if final else pitches
        if not allowed:
            allowed = [nearest(center, [p for p in scale if p % 12 == parent['tonic']])]
        new = []
        for score, path in beam:
            previous = path[-1] if path else original[0].pitch
            for p in allowed:
                leap = abs(p - previous)
                if path and leap > 9:
                    continue
                motif_delta = intervals[(i - 1) % len(intervals)] if i else 0
                target = center + orientation * 4 * math.sin(math.pi * i / max(1, len(slots) - 1))
                cost = .16 * leap + .10 * abs(p - target) + .15 * abs((p - previous) - motif_delta)
                if start % 480 == 0 and p % 12 not in chords[start // BAR]:
                    cost += 1.5
                if len(path) >= 2 and path[-1] == path[-2] == p:
                    cost += 1.5
                cost += rng.random() * 1.1
                new.append((score + cost, path + [p]))
        if not new:
            raise ValueError('没有满足音域和跳进约束的回答句候选。')
        beam = sorted(new, key=lambda entry: entry[0])[:10]
    chosen = rng.choice(beam[:3])[1]
    ns = [Note(p, start, duration, 80) for p, (start, duration) in zip(chosen, slots)]
    return ns, ['引用并重组节奏动机', '呼应式旋律发展', '属功能准备与主音收束'], {
        'harmony_degrees': [d + 1 for d in degrees], 'motif_rhythm': [list(slot) for slot in motif],
        'search': 'beam_width_10', 'cadence': 'tonic'}


def quality(parent, ns):
    src = notes_of(parent)
    exact = signature(src) == signature(ns)
    transpose_only = len(src) == len(ns) and len({a.pitch - b.pitch for a, b in zip(src, ns)}) == 1 and all(
        (a.start, a.duration) == (b.start, b.duration) for a, b in zip(src, ns))
    if exact or transpose_only:
        raise ValueError('候选只是复制或整体移调。')
    leaps = [abs(b.pitch - a.pitch) for a, b in zip(ns, ns[1:])]
    src_rhythm = {(n.start % BAR, n.duration) for n in src}
    rhythm = sum((n.start % BAR, n.duration) in src_rhythm for n in ns) / len(ns)
    smooth = sum(v <= 5 for v in leaps) / max(1, len(leaps))
    return dict(score=round(.55 * smooth + .45 * rhythm, 3),
                rhythm_vocabulary_overlap=round(rhythm, 3), stepwise_ratio=round(smooth, 3),
                max_leap=max(leaps, default=0), aesthetic_verified=False)


def generate_candidates(parent, kind='variant', seed=1, count=3):
    validate(parent)
    if kind not in ('variant', 'answer') or not 1 <= count <= 8:
        raise ValueError('生成类型或候选数量无效。')
    rng = random.Random(seed)
    seen, candidates = set(), []
    for attempt in range(40):
        try:
            ns, methods, plan = (variant if kind == 'variant' else answer)(parent, rng)
            key = tuple(signature(ns))
            if key in seen:
                continue
            metrics = quality(parent, ns)
            child = make_item(parent['name'] + ('_c' if kind == 'variant' else '_answer') + str(len(candidates) + 1),
                              kind, ns, parent['bars'], parent['bpm'], parent['tonic'], parent['mode'])
            child.update(parents=[parent['id']], methods=methods,
                         generation=dict(seed=seed, attempt=attempt, algorithm='motif-rules-v1', plan=plan),
                         metrics=metrics)
            seen.add(key); candidates.append(child)
            if len(candidates) >= count:
                break
        except ValueError:
            continue
    if not candidates:
        raise ValueError('未找到合格候选；原素材已保留。请换一段参考旋律或更换随机种子。')
    return sorted(candidates, key=lambda item: item['metrics']['score'], reverse=True)


def new_pool():
    return dict(schema=SCHEMA, id=uuid.uuid4().hex, items=[])


def add_item(pool, item):
    validate(item)
    if len(pool['items']) >= 200:
        raise ValueError('素材池最多保存 200 个素材，请新建素材池。')
    if any(it['id'] == item['id'] for it in pool['items']):
        raise ValueError('素材 ID 已存在。')
    if pool['items']:
        ref = pool['items'][0]
        if abs(ref['bpm'] - item['bpm']) > .01 or (ref['tonic'], ref['mode']) != (item['tonic'], item['mode']):
            raise ValueError('首版同一素材池需统一 BPM 与调性参考，请确认导入设置或新建素材池。')
    if any(p not in {it['id'] for it in pool['items']} for p in item['parents']):
        raise ValueError('缺少来源素材。')
    pool['items'].append(item)


def save_pool(pool, path=None):
    if path is None:
        from runtime_config import data_root
        folder = data_root() / 'step2' / 'projects' / pool['id']; folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('pool-' + uuid.uuid4().hex[:10] + '.json')
    path = Path(path)
    # Exclusive creation protects earlier snapshots even when called outside the UI.
    with path.open('x', encoding='utf-8') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    return path


def load_pool(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('素材池文件超过 8 MB。')
    pool = json.loads(path.read_text(encoding='utf-8'))
    if pool.get('schema') != SCHEMA or not isinstance(pool.get('items'), list) or len(pool['items']) > 200:
        raise ValueError('不是受支持的素材池文件，或素材数超过 200。')
    # Never use imported IDs as filesystem paths.
    if not isinstance(pool.get('id'), str) or len(pool['id']) != 32 or any(c not in '0123456789abcdef' for c in pool['id']):
        raise ValueError('项目 ID 无效。')
    rebuilt = new_pool(); rebuilt['id'] = pool['id']
    for item in pool['items']:
        if not isinstance(item.get('id'), str) or len(item['id']) != 32 or any(c not in '0123456789abcdef' for c in item['id']):
            raise ValueError('素材 ID 无效。')
        add_item(rebuilt, item)
    return rebuilt


def export_material(item, output_root=None, render=True):
    validate(item)
    from runtime_config import data_root
    folder = Path(output_root or data_root() / 'step2' / 'exports') / uuid.uuid4().hex
    folder.mkdir(parents=True)
    arrangement = dict(bpm=item['bpm'], total_ticks=item['bars'] * BAR,
        layers=[dict(name='Neutral melody', preset='soft', drum='', volume=30, pan=0, notes=notes_of(item))])
    music.export_midi(arrangement, folder / 'melody.mid')
    music.export_mmp(arrangement, folder / 'melody.mmp')
    report = dict(material=item, status='score_only', audio=None)
    try:
        if render:
            proc = subprocess.run([str(music.LMMS), 'render', str(folder / 'melody.mmp'),
                '-o', str(folder / 'dry.wav'), '-s', '44100'],
                capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (folder / 'render.log').write_bytes(proc.stdout + proc.stderr)
            if proc.returncode or not (folder / 'dry.wav').is_file():
                raise ValueError('渲染失败，已保留 MIDI 与工程：' + str(folder))
            report['audio'] = music.postprocess(folder / 'dry.wav', folder / 'preview.wav', item['bars'] * 240 / item['bpm'], 0)
            report['status'] = 'complete'
    except Exception as exc:
        report.update(status='failed', error=str(exc)); raise
    finally:
        write_json(folder / 'material.json', report)
    return folder, report
