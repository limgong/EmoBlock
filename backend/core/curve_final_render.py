"""P7 same-score exports and actual LMMS audio. No planning or UI imports."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import wave
import uuid
import xml.etree.ElementTree as ET

import curve_project as m
import curve_final as final
from curve_audition import _RENDER_LOCK
from runtime_config import data_root, find_lmms

RENDERER = 'curve-final-lmms-v1'
FIELDS = 'schema spec_rev contract_rev id version candidate_ref score_ref kind mode renderer_version files body_ticks body_seconds audio_seconds tail_policy asset_fingerprint'


def asset_fingerprint(asset):
    return m.digest('emoblocks.final-asset.v1', {k:v for k,v in asset.items() if k not in ('id','asset_fingerprint')})


def _cancel(check):
    if check and check(): m.reject('已取消准备试听；工程和历史结果已保留。', 'CANCELLED')


def output_arrangement(score):
    import engine
    if score['total_ticks'] % 10 or any(n['start_tick']%10 or n['duration_tick']%10 for n in score['notes'] + score['emitted_notes'] + [n for layer in score['layers'] for n in layer['notes']]):
        m.reject('当前输出器不能无损表达这组精确 tick，原乐谱已保留。', 'OUTPUT_TIME_UNREPRESENTABLE')
    layers = []
    for layer in score['layers']:
        layers.append({k: copy.deepcopy(layer[k]) for k in ('name','preset','volume','pan','drum')} | dict(
            notes=[engine.Note(n['pitch'],n['start_tick'],n['duration_tick'],n['velocity']) for n in layer['notes']]))
    return dict(bpm=score['bpm'],total_ticks=score['total_ticks'],layers=layers)


def _file(path):
    data = Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))


def export_score(score, folder):
    """Keep existing encoders; add truthful same-score binding metadata."""
    import engine
    import mido
    folder=Path(folder);arrangement=output_arrangement(score)
    engine.export_midi(arrangement,folder/'composition.mid')
    engine.export_mmp(arrangement,folder/'composition.mmp')
    binding=json.dumps(dict(score_fingerprint=score['score_fingerprint'],mode=score['mode'],body_ticks=score['total_ticks']),sort_keys=True)
    midi=mido.MidiFile(folder/'composition.mid')
    midi.tracks[0].insert(0,mido.MetaMessage('text',text=binding));midi.save(folder/'composition.mid')
    xml=ET.parse(folder/'composition.mmp')
    xml.find('.//projectnotes').text=binding+'\nWAV uses this LMMS arrangement with the existing one-second tail; MIDI timbres depend on the receiving software.'
    xml.write(folder/'composition.mmp',encoding='utf-8',xml_declaration=True)


def validate_outputs(score, files):
    """Read actual encoded notes, not just the exporter's manifest."""
    import mido
    import engine
    native = mido.MidiFile(files['mid']['path'])
    expected = [sorted((n['start_tick'],n['pitch'],n['duration_tick'],max(1,min(127,round(n['velocity']*layer['volume']/35)))) for n in layer['notes']) for layer in score['layers']]
    if len(native.tracks)!=1+len(score['layers']):m.reject('MIDI声部数量与乐谱不符。','OUTPUT_BINDING_MISMATCH')
    tempos=[];meters=[]
    for index,track in enumerate(native.tracks):
        tick=0
        for event in track:
            tick+=event.time
            if event.type=='set_tempo':tempos.append((index,tick,event.tempo))
            if event.type=='time_signature':meters.append((index,tick,event.numerator,event.denominator))
            if not event.is_meta and event.type not in ('note_on','note_off','program_change'):
                m.reject('MIDI包含未规划的演奏控制。','OUTPUT_BINDING_MISMATCH')
            if index==0 and not event.is_meta:m.reject('MIDI主轨包含未规划的演奏。','OUTPUT_BINDING_MISMATCH')
    if tempos!=[(0,0,mido.bpm2tempo(score['bpm']))] or meters!=[(0,0,4,4)]:m.reject('MIDI速度或拍号与乐谱不符。','OUTPUT_BINDING_MISMATCH')
    actual = []
    channels=iter([channel for channel in range(16) if channel!=9])
    for index,track in enumerate(native.tracks[1:]):
        layer=score['layers'][index];channel=9 if layer['drum'] else next(channels)
        program_tick=0;programs=[]
        for event in track:
            program_tick+=event.time
            if event.type=='program_change':programs.append((program_tick,event.channel,event.program))
        if programs!=[(0,channel,engine.PRESETS[layer['preset']][4])]:m.reject('MIDI音色、起始程序或通道绑定不符。','OUTPUT_BINDING_MISMATCH')
        tick = 0; active = {}; notes = []; selected_program = None
        for event in track:
            tick += event.time
            if not event.is_meta and event.channel!=channel:m.reject('MIDI音符被路由到另一乐器或鼓通道。','OUTPUT_BINDING_MISMATCH')
            if event.type == 'program_change':selected_program = event.program
            if event.type == 'note_on' and event.velocity:
                if selected_program!=engine.PRESETS[layer['preset']][4]:m.reject('MIDI起音前尚未设置所选音色。','OUTPUT_BINDING_MISMATCH')
                key=(event.channel,event.note)
                if key in active: m.reject('MIDI重复起音未正确关闭。','OUTPUT_BINDING_MISMATCH')
                active[key]=(tick,event.velocity)
            elif event.type in ('note_off','note_on'):
                key=(event.channel,event.note)
                if key in active:
                    start,velocity=active.pop(key); notes.append((start,event.note,tick-start,velocity))
                else:m.reject('MIDI存在无对应起音的结束事件。','OUTPUT_BINDING_MISMATCH')
        if active: m.reject('MIDI包含未结束音符。','OUTPUT_BINDING_MISMATCH')
        if tick!=score['total_ticks']:m.reject('MIDI总时长与乐谱不符。','OUTPUT_BINDING_MISMATCH')
        actual.append(sorted(notes))
    if native.ticks_per_beat != m.PPQ or actual != expected: m.reject('MIDI与所选乐谱不一致。','OUTPUT_BINDING_MISMATCH')
    xml = ET.parse(files['mmp']['path']); tracks = xml.findall('.//trackcontainer/track')
    if len(tracks)!=len(score['layers']) or float(xml.find('head').get('bpm'))!=score['bpm']:m.reject('LMMS声部或速度不符。','OUTPUT_BINDING_MISMATCH')
    actual = []
    for index,track in enumerate(tracks):
        layer=score['layers'][index];instrument=track.find('instrumenttrack')
        if (float(instrument.get('vol')),float(instrument.get('pan')))!=(layer['volume'],layer['pan']):m.reject('LMMS音量或声像不符。','OUTPUT_BINDING_MISMATCH')
        drum = track.find('.//audiofileprocessor') is not None
        if drum!=bool(layer['drum']):m.reject('LMMS乐器角色不符。','OUTPUT_BINDING_MISMATCH')
        if drum:
            if Path(track.find('.//audiofileprocessor').get('src')).name!=layer['drum']:m.reject('LMMS鼓采样不符。','OUTPUT_BINDING_MISMATCH')
        else:
            oscillator=track.find('.//tripleoscillator');envelope=track.find('.//elvol')
            wave_type,attack,release,sustain,_,_=engine.PRESETS[layer['preset']]
            if oscillator is None or int(oscillator.get('wavetype0'))!=wave_type or (float(envelope.get('att')),float(envelope.get('rel')),float(envelope.get('sustain')))!=(attack,release,sustain):m.reject('LMMS音色与乐谱不符。','OUTPUT_BINDING_MISMATCH')
        notes=[]
        for pattern in track.findall('pattern'):
            offset=int(pattern.get('pos','0'))*10
            notes.extend((offset+int(n.get('pos'))*10,int(n.get('key')),
                          int(n.get('len'))*10,int(n.get('vol'))) for n in pattern.findall('note'))
        actual.append(sorted(notes))
    expected = [sorted((n['start_tick'],57 if layer['drum'] else n['pitch']-12,n['duration_tick'],n['velocity']) for n in layer['notes']) for layer in score['layers']]
    if actual != expected: m.reject('LMMS工程与所选乐谱不一致。','OUTPUT_BINDING_MISMATCH')
    binding=json.dumps(dict(score_fingerprint=score['score_fingerprint'],mode=score['mode'],body_ticks=score['total_ticks']),sort_keys=True)
    if binding not in [event.text for event in native.tracks[0] if event.type=='text'] or not (xml.find('.//projectnotes').text or '').startswith(binding+'\n'):
        m.reject('输出缺少所选乐谱与模式绑定。','OUTPUT_BINDING_MISMATCH')


def render(score, candidate_ref, version=1, should_cancel=None, on_progress=None):
    import engine
    import flow_engine
    _cancel(should_cancel); arrangement=output_arrangement(score)
    executable=find_lmms()
    if not executable.is_file(): m.reject('找不到已有 LMMS，请恢复安装后重试。','RENDERER_UNAVAILABLE')
    folder=data_root()/'recommendations'/uuid.uuid4().hex;folder.mkdir(parents=True)
    export_score(score,folder)
    (folder/'score.json').write_text(json.dumps(score,ensure_ascii=False,indent=2),encoding='utf-8')
    files={key:_file(folder/name) for key,name in [('mid','composition.mid'),('mmp','composition.mmp')]}
    validate_outputs(score,files)
    acquired=False
    try:
        while not acquired:
            _cancel(should_cancel);acquired=_RENDER_LOCK.acquire(timeout=.1)
        _cancel(should_cancel)
        with (folder/'render.log').open('wb') as log:
            proc=subprocess.Popen([str(executable),'render',str(folder/'composition.mmp'),'-o',str(folder/'dry.wav'),'-s','44100'],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+240
            try:
                while proc.poll() is None:
                    _cancel(should_cancel)
                    if time.monotonic()>deadline: m.reject('试听渲染超时，请查看日志后重试。','RENDER_TIMEOUT')
                    time.sleep(.05)
            except BaseException:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()
                raise
        if proc.returncode or not (folder/'dry.wav').is_file(): m.reject('真实渲染失败，日志：'+str(folder/'render.log'),'RENDER_FAILED')
        _cancel(should_cancel)
        body=score['total_ticks']/m.PPQ*60/score['bpm']
        info=flow_engine.finish_audio(folder/'dry.wav',folder/'preview.wav',body,wet=0)
        if info['peak']<.0001: m.reject('试听音频没有可听见的声音，请查看渲染日志。','RENDER_FAILED')
    finally:
        if acquired: _RENDER_LOCK.release()
    with wave.open(str(folder/'preview.wav'),'rb') as stream:
        seconds=stream.getnframes()/stream.getframerate()
    asset=dict(final.header('emoblocks.audio-asset.v1'),version=version,candidate_ref=copy.deepcopy(candidate_ref),score_ref=final.ref(score),
        kind=score['kind'],mode=score['mode'],renderer_version=RENDERER,files=dict(files,wav=_file(folder/'preview.wav')),
        body_ticks=score['total_ticks'],body_seconds=body,audio_seconds=seconds,tail_policy='fixed-1s-existing-finish-audio')
    asset['asset_fingerprint']=asset_fingerprint(asset);asset['id']=asset['asset_fingerprint']
    validate_asset(asset,score,candidate_ref)
    (folder/'asset.json').write_text(json.dumps(asset,ensure_ascii=False,indent=2),encoding='utf-8')
    return asset


def validate_asset(asset, score, candidate_ref=None, files=True, required_formats=None):
    m.shape(asset,FIELDS);final.version(asset,'emoblocks.audio-asset.v1');m.integer(asset['version'],1)
    if (asset['asset_fingerprint']!=asset_fingerprint(asset) or asset['id']!=asset['asset_fingerprint']
            or asset['score_ref']!=final.ref(score) or asset['kind']!=score['kind'] or asset['mode']!=score['mode']
            or asset['renderer_version']!=RENDERER or asset['body_ticks']!=score['total_ticks']
            or asset['body_seconds']!=score['total_ticks']/m.PPQ*60/score['bpm']
            or asset['tail_policy']!='fixed-1s-existing-finish-audio'
            or (candidate_ref is not None and asset['candidate_ref']!=candidate_ref)):
        m.reject('音频版本与所选乐谱不一致。','OUTPUT_BINDING_MISMATCH')
    m.shape(asset['files'],'wav mid mmp')
    physical=set(required_formats or ('wav','mid','mmp')) if files else set()
    if not physical<=set(asset['files']):m.reject('未知输出用途。')
    for key,row in asset['files'].items():
        m.shape(row,'path sha256 bytes');m.text(row['path']);m.ident(row['sha256']);m.integer(row['bytes'],1)
        if key in physical and _file(row['path'])!=row: m.reject('试听或输出文件已移动或改变，请重新计算。','OUTPUT_FILE_UNAVAILABLE')
    if 'wav' in physical:
        with wave.open(asset['files']['wav']['path'],'rb') as stream:
            if stream.getnchannels() not in (1,2) or stream.getsampwidth()!=2 or abs(stream.getnframes()/stream.getframerate()-asset['audio_seconds'])>1/stream.getframerate() or abs(asset['audio_seconds']-asset['body_seconds']-1)>1/stream.getframerate():
                m.reject('实际音频与结果信息不一致。','OUTPUT_BINDING_MISMATCH')
            import numpy as np
            remaining=stream.getnframes();peak=0
            while remaining:
                count=min(65536,remaining);pcm=stream.readframes(count)
                if len(pcm)!=count*stream.getnchannels()*stream.getsampwidth():
                    m.reject('试听音频数据不完整，请重新准备。','OUTPUT_AUDIO_INCOMPLETE')
                peak=max(peak,int(np.abs(np.frombuffer(pcm,dtype='<i2').astype(np.int32)).max()))
                remaining-=count
            if peak/32768<.0001:m.reject('试听音频没有有效声音，请重新准备。','OUTPUT_AUDIO_SILENT')
    if {'mid','mmp'}<=physical:validate_outputs(score,asset['files'])
    return True
