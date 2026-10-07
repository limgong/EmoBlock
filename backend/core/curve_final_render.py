"""P7 same-score exports and actual LMMS audio. No planning or UI imports."""
import copy
import os
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

LEGACY_RENDERER = 'curve-final-lmms-v1'
RENDERER = 'curve-final-lmms-v2'
# Identical official factory bytes in LMMS 1.2.2 and 1.3.0-alpha.2.
STOCK_RESOURCES = {
    'bassdrum01.ogg': (9922, 'e8abcb4d593262f08e7f12cf1c6fdcc4b83fa27175d5461fef6bbc2d205307a7'),
    'snare01.ogg': (7215, '64905d93d0941f3e02ef9f2fc7ee1e533b96308cc5c69eed3de27a1827e876a5'),
    'hihat_closed01.ogg': (5497, '703f80c3eff4a6a4b817b1d086c6c5eddd7edda8a4ebf50cec662750b1d59e54'),
}
FIELDS = 'schema spec_rev contract_rev id version candidate_ref score_ref kind mode renderer_version files body_ticks body_seconds audio_seconds tail_policy asset_fingerprint'


def _profile(profile):
    if profile not in (LEGACY_RENDERER, RENDERER):
        m.reject('输出profile不受支持，请重新准备所选版本。', 'OUTPUT_BINDING_MISMATCH')


def _resource_uri(drum):
    if drum not in STOCK_RESOURCES:
        m.reject('未规划的鼓采样。', 'OUTPUT_BINDING_MISMATCH')
    return 'data:/samples/drums/' + drum


def _fixed_resources(score):
    rows=[]
    for drum in sorted({layer['drum'] for layer in score['layers'] if layer['drum']}):
        uri=_resource_uri(drum);size,digest=STOCK_RESOURCES[drum]
        rows.append(dict(drum=drum,src=uri,sha256=digest,bytes=size))
    return rows


def _binding(score, profile):
    data=dict(score_fingerprint=score['score_fingerprint'],mode=score['mode'],body_ticks=score['total_ticks'])
    if profile==RENDERER:data.update(renderer_profile=profile,resources=_fixed_resources(score))
    return json.dumps(data,sort_keys=True)


def _authenticated_root(score):
    """One real resource root, authenticated against fixed official content."""
    import engine
    root=None
    for row in _fixed_resources(score):
        try:
            path=Path(engine.sample_path(engine.LMMS,row['drum'])).absolute()
            candidate=path.parent.parent.parent.resolve()
            expected=candidate/'samples'/'drums'/row['drum']
            # Reject legacy short layouts and links escaping the chosen root.
            if path.parent.name!='drums' or path.parent.parent.name!='samples' or path.resolve()!=expected:
                raise ValueError('factory resource layout or link differs')
            actual=_file(path)
        except (OSError,ValueError,RuntimeError):
            m.reject('LMMS工厂采样不可读或位置不匹配，请恢复匹配的安装资源。','OUTPUT_RESOURCE_UNAVAILABLE')
        if (actual['bytes'],actual['sha256'])!=(row['bytes'],row['sha256']):
            m.reject('LMMS工厂采样内容不匹配，请恢复原采样后重新准备。','OUTPUT_BINDING_MISMATCH')
        if root is not None and candidate!=root:
            m.reject('LMMS采样来自不同资源根，请恢复一致的安装资源。','OUTPUT_RESOURCE_UNAVAILABLE')
        root=candidate
    return root


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


def export_score(score, folder, profile=None):
    """Keep existing encoders; add truthful same-score binding metadata."""
    import engine
    import mido
    profile=RENDERER if profile is None else profile;_profile(profile)
    if profile==RENDERER:_authenticated_root(score)
    folder=Path(folder);arrangement=output_arrangement(score)
    engine.export_midi(arrangement,folder/'composition.mid')
    engine.export_mmp(arrangement,folder/'composition.mmp')
    binding=_binding(score,profile)
    midi=mido.MidiFile(folder/'composition.mid')
    midi.tracks[0].insert(0,mido.MetaMessage('text',text=binding));midi.save(folder/'composition.mid')
    xml=ET.parse(folder/'composition.mmp')
    if profile==RENDERER:
        for sampler in xml.findall('.//audiofileprocessor'):
            sampler.set('src',_resource_uri(Path(sampler.get('src')).name))
    xml.find('.//projectnotes').text=binding+'\nWAV uses this LMMS arrangement with the existing one-second tail; MIDI timbres depend on the receiving software.'
    xml.write(folder/'composition.mmp',encoding='utf-8',xml_declaration=True)


def _numeric_xml(element, expected, names=()):
    """Authenticate the exporter's concrete playback settings, including defaults."""
    try:
        valid = element is not None and set(element.attrib)==set(expected)|set(names) and all(float(element.get(key))==value for key,value in expected.items())
    except (ValueError,TypeError):
        valid = False
    if not valid:m.reject('LMMS播放参数与所选乐谱不符。','OUTPUT_BINDING_MISMATCH')


def _sample_resource(source, drum, profile=LEGACY_RENDERER):
    """Allow installed resources and byte-identical copies, never name-only matches."""
    import engine
    if profile==RENDERER:
        if source!=_resource_uri(drum):m.reject('LMMS鼓采样URI与所选输出profile不符。','OUTPUT_BINDING_MISMATCH')
        return
    try:
        actual=Path(source);expected=Path(engine.sample_path(engine.LMMS,drum))
        if not actual.is_absolute() or not actual.is_file() or not expected.is_file():
            raise FileNotFoundError('Unavailable planned drum resource')
        actual_file=_file(actual);expected_file=_file(expected)
    except (OSError,ValueError,RuntimeError):
        m.reject('鼓采样不可读，请恢复 LMMS 采样资源后重新准备。','OUTPUT_RESOURCE_UNAVAILABLE')
    if not actual_file['bytes'] or (actual_file['sha256'],actual_file['bytes'])!=(expected_file['sha256'],expected_file['bytes']):
        m.reject('鼓采样内容与所选音色不符，请恢复原采样后重新准备。','OUTPUT_BINDING_MISMATCH')


def _validate_midi(score, files, profile):
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
    binding=_binding(score,profile)
    texts=[e.text for e in native.tracks[0] if e.type=='text']
    if binding not in texts or (profile==RENDERER and (not native.tracks[0] or native.tracks[0][0].type!='text' or native.tracks[0][0].time!=0 or native.tracks[0][0].text!=binding)):
        m.reject('MIDI缺少所选乐谱、模式或输出profile绑定。','OUTPUT_BINDING_MISMATCH')


def _validate_mmp(score, files, profile):
    import engine
    xml = ET.parse(files['mmp']['path']); tracks = xml.findall('.//trackcontainer/track')
    if len(tracks)!=len(score['layers']):m.reject('LMMS声部数量不符。','OUTPUT_BINDING_MISMATCH')
    _numeric_xml(xml.find('head'),dict(bpm=score['bpm'],mastervol=62,masterpitch=0,timesig_numerator=4,timesig_denominator=4))
    _numeric_xml(xml.find('.//timeline'),dict(lp0pos=0,lp1pos=score['total_ticks']/10,lpstate=0))
    if xml.getroot().get('type')!='song' or len(xml.find('head')) or len(xml.find('.//timeline')) or [node.tag for node in xml.getroot()]!=['head','song'] or xml.find('song').attrib or [node.tag for node in xml.find('song')]!=['trackcontainer','timeline','projectnotes'] or any(node.tag!='track' for node in xml.find('.//trackcontainer')):
        m.reject('LMMS包含未规划的播放或自动化结构。','OUTPUT_BINDING_MISMATCH')
    if profile == RENDERER:_authenticated_root(score)
    actual = []
    for index,track in enumerate(tracks):
        layer=score['layers'][index];instrument=track.find('instrumenttrack')
        _numeric_xml(track,dict(type=0,muted=0,solo=0),('name',))
        _numeric_xml(instrument,dict(vol=layer['volume'],pan=layer['pan'],pitch=0,basenote=57,fxch=0,usemasterpitch=1))
        effects=instrument.find('fxchain');_numeric_xml(effects,dict(enabled=0,numofeffects=0))
        if len(effects):m.reject('LMMS包含未规划的音效。','OUTPUT_BINDING_MISMATCH')
        drum = track.find('.//audiofileprocessor') is not None
        if drum!=bool(layer['drum']):m.reject('LMMS乐器角色不符。','OUTPUT_BINDING_MISMATCH')
        plugin=instrument.find('instrument');plugin_name='audiofileprocessor' if drum else 'tripleoscillator'
        if plugin is None or plugin.attrib!={'name':plugin_name} or [node.tag for node in plugin]!=[plugin_name] or [node.tag for node in instrument]!=(['instrument','fxchain'] if drum else ['instrument','eldata','fxchain']):
            m.reject('LMMS包含未规划的乐器结构。','OUTPUT_BINDING_MISMATCH')
        if drum:
            if Path(track.find('.//audiofileprocessor').get('src')).name!=layer['drum']:m.reject('LMMS鼓采样不符。','OUTPUT_BINDING_MISMATCH')
            _sample_resource(plugin[0].get('src'),layer['drum'],profile)
            _numeric_xml(plugin[0],dict(amp=100,interp=1,sframe=0,eframe=1,lframe=0,reversed=0),('src',))
            if len(plugin[0]):m.reject('LMMS包含未规划的采样控制。','OUTPUT_BINDING_MISMATCH')
        else:
            oscillator=track.find('.//tripleoscillator');envelope=track.find('.//elvol')
            wave_type,attack,release,sustain,_,_=engine.PRESETS[layer['preset']]
            _numeric_xml(oscillator,dict(vol0=100,vol1=12 if layer['preset']=='brass' else 0,vol2=0,coarse0=0,coarse1=0,finel0=0,finer0=0,finel1=-4,finer1=4,pan0=0,wavetype0=wave_type,wavetype1=wave_type))
            env=instrument.find('eldata');_numeric_xml(env,dict(fwet=1 if layer['preset']=='dark' else 0,ftype=0,fcut=1500,fres=.5))
            if [node.tag for node in env]!=['elvol']:m.reject('LMMS包含未规划的包络。','OUTPUT_BINDING_MISMATCH')
            _numeric_xml(envelope,dict(amt=1,att=attack,hold=0,dec=.22,sustain=sustain,rel=release,pdel=0,lamt=0))
            if len(oscillator) or len(envelope):m.reject('LMMS包含未规划的音色控制。','OUTPUT_BINDING_MISMATCH')
        notes=[]
        if [node.tag for node in track]!=['instrumenttrack','pattern']:m.reject('LMMS包含未规划的音符或自动化。','OUTPUT_BINDING_MISMATCH')
        for pattern in track.findall('pattern'):
            _numeric_xml(pattern,dict(type=1,pos=0,len=score['total_ticks']/10,steps=16),('name',))
            if any(node.tag!='note' for node in pattern):m.reject('LMMS包含未规划的音符控制。','OUTPUT_BINDING_MISMATCH')
            offset=int(pattern.get('pos','0'))*10
            for note in pattern:
                _numeric_xml(note,{key:float(note.get(key)) for key in ('key','pos','len','vol')}|{'pan':0})
                if len(note):m.reject('LMMS包含未规划的音符控制。','OUTPUT_BINDING_MISMATCH')
            notes.extend((offset+int(n.get('pos'))*10,int(n.get('key')),
                          int(n.get('len'))*10,int(n.get('vol'))) for n in pattern.findall('note'))
        actual.append(sorted(notes))
    expected = [sorted((n['start_tick'],57 if layer['drum'] else n['pitch']-12,n['duration_tick'],n['velocity']) for n in layer['notes']) for layer in score['layers']]
    if actual != expected: m.reject('LMMS工程与所选乐谱不一致。','OUTPUT_BINDING_MISMATCH')
    binding=_binding(score,profile)
    if not (xml.find('.//projectnotes').text or '').startswith(binding+'\n'):
        m.reject('LMMS缺少所选乐谱、模式或资源profile绑定。','OUTPUT_BINDING_MISMATCH')


def validate_outputs(score, files, profile=None, required_formats=None):
    """Authenticate only the requested real formats, each independently."""
    profile=RENDERER if profile is None else profile
    _profile(profile)
    formats={'mid','mmp'} if required_formats is None else set(required_formats)
    if not formats or not formats<={'mid','mmp'}:
        m.reject('请选择有效的输出用途。','INVALID_PARAMETERS')
    try:
        if 'mid' in formats:_validate_midi(score,files,profile)
        if 'mmp' in formats:_validate_mmp(score,files,profile)
    except m.ProjectError:
        raise
    except (OSError,ValueError,ET.ParseError,EOFError):
        m.reject('输出文件无法读取或格式损坏，请重新准备所选版本。','OUTPUT_FILE_UNAVAILABLE')


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
    resource_root=_authenticated_root(score)
    child_env=dict(os.environ)
    if resource_root is None:child_env.pop('LMMS_DATA_DIR',None)
    else:child_env['LMMS_DATA_DIR']=str(resource_root)
    config=folder/'config.xml'
    config.write_text('<?xml version="1.0"?><lmms/>',encoding='utf-8')
    (folder/'renderer-context.json').write_text(json.dumps(dict(renderer_profile=RENDERER,
        executable=str(executable),config=str(config),resource_root=str(resource_root) if resource_root else None,
        LMMS_DATA_DIR=child_env.get('LMMS_DATA_DIR')),ensure_ascii=False,indent=2),encoding='utf-8')
    acquired=False
    try:
        while not acquired:
            _cancel(should_cancel);acquired=_RENDER_LOCK.acquire(timeout=.1)
        _cancel(should_cancel)
        with (folder/'render.log').open('wb') as log:
            proc=subprocess.Popen([str(executable),'-c',str(config),'render',str(folder/'composition.mmp'),'-o',str(folder/'dry.wav'),'-s','44100'],env=child_env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
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
        validate_outputs(score,files)
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
    _profile(asset['renderer_version'])
    if (asset['asset_fingerprint']!=asset_fingerprint(asset) or asset['id']!=asset['asset_fingerprint']
            or asset['score_ref']!=final.ref(score) or asset['kind']!=score['kind'] or asset['mode']!=score['mode']
            or asset['body_ticks']!=score['total_ticks']
            or asset['body_seconds']!=score['total_ticks']/m.PPQ*60/score['bpm']
            or asset['tail_policy']!='fixed-1s-existing-finish-audio'
            or (candidate_ref is not None and asset['candidate_ref']!=candidate_ref)):
        m.reject('音频版本与所选乐谱不一致。','OUTPUT_BINDING_MISMATCH')
    m.shape(asset['files'],'wav mid mmp')
    requested=set(('wav','mid','mmp') if required_formats is None else required_formats)
    if not requested or not requested<=set(asset['files']):m.reject('未知输出用途。','INVALID_PARAMETERS')
    physical=requested if files else set()
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
    encoded=physical&{'mid','mmp'}
    if encoded:validate_outputs(score,asset['files'],profile=asset['renderer_version'],required_formats=encoded)
    return True
