"""Real deployed-service acceptance over HTTP/SSH tunnel; no mocked music.

State with cookies is private. Run --prepare, restart the owned application,
then --after-restart against the same data volume.
"""
import argparse
import hashlib
import io
import json
import os
import time
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import mido
import numpy as np

URL = os.environ.get('SMOKE_URL', 'http://127.0.0.1:8876')
OUT = Path(os.environ.get('SMOKE_OUTPUT', 'data/cloud-acceptance'))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = []


def check(name, result):
    assert result, name
    REPORT.append(name)
    print('PASS', name, flush=True)


def post(client, path, data):
    response = client.post(path, json=data)
    response.raise_for_status()
    return response.json()


def wait_job(client, jid):
    started = time.monotonic()
    previous = None
    while time.monotonic() - started < 610:
        response = client.get('/api/jobs/' + jid)
        response.raise_for_status()
        job = response.json()
        phase = (job['status'], job.get('progress', {}).get('phase'))
        if phase != previous:
            print('JOB', phase, flush=True)
            previous = phase
        if job['status'] not in ('QUEUED', 'RUNNING'):
            return job
        time.sleep(2)
    raise AssertionError('deployed generation timed out')


def arrange(client):
    project = post(client, '/api/session', {'sample': 'joy'})

    def edit(action, args):
        nonlocal project
        project = post(client, '/api/edit', dict(fingerprint=project['fingerprint'], action=action, args=args))

    edit('resize', {'grid_count': 8})
    edit('set_intensity', {'points': [{'tick': 0, 'level': .2}, {'tick': 9600, 'level': .9}, {'tick': 15360, 'level': .25}]})
    materials = [x['id'] for x in project['materials'] if x['kind'] == 'block']
    for index, source, emotion in [(0, 0, 'calm'), (1, 1, 'calm'), (4, 2, 'suspense'), (5, 0, 'crisis'), (7, 1, 'resolve')]:
        edit('place', {'material_id': materials[source], 'start_tick': index * 1920})
        if emotion != 'calm':
            edit('set_emotion', {'placement_ids': [project['placements'][-1]['id']], 'emotion': emotion})
    edit('mark_blank', {'start_tick': 11520, 'end_tick': 13440})
    return project


def prepare():
    states = []
    with httpx.Client(base_url=URL, timeout=90) as client, httpx.Client(base_url=URL, timeout=90) as other:
        check('healthy renderer', client.get('/api/health').json()['renderer_available'])
        check('anonymous project inaccessible', other.get('/api/project').status_code == 401)
        project = arrange(client)
        stranger = post(other, '/api/session', {'sample': 'joy'})
        check('independent session projects', stranger['fingerprint'] != project['fingerprint'])
        check('cross-origin mutation rejected', client.post('/api/edit', json={}, headers={'Origin': 'https://untrusted.example'}).status_code == 403)
        check('oversized body rejected', client.post('/api/edit', content=b'x' * 131073).status_code == 413)
        check('overlap rejected', client.post('/api/edit', json=dict(fingerprint=project['fingerprint'], action='place', args={'material_id': project['materials'][0]['id'], 'start_tick': 0})).status_code == 422)
        cancelled = post(client, '/api/generate', dict(fingerprint=project['fingerprint'], mode='melody_only'))['id']
        check('other session cannot read task', other.get('/api/jobs/' + cancelled).status_code == 404)
        post(client, '/api/jobs/' + cancelled + '/cancel', {})
        check('owned task cancellation', wait_job(client, cancelled)['status'] == 'CANCELLED')

        for mode in ('melody_only', 'arranged'):
            if mode == 'arranged':
                project = arrange(client)
            else:
                project = client.get('/api/project').json()
            jid = post(client, '/api/generate', dict(fingerprint=project['fingerprint'], mode=mode))['id']
            check(mode + ' real generation', wait_job(client, jid)['status'] == 'SUCCEEDED')
            project = client.get('/api/project').json()
            check(mode + ' valid candidates', len(project['candidates']) >= 1 and all(x['ready'] for x in project['candidates']))
            cid = project['candidates'][0]['id']
            hashes = {}
            folder = OUT / mode
            folder.mkdir(exist_ok=True)
            for kind in ('comparison', 'final'):
                for fmt in ('wav', 'mid', 'mmp'):
                    path = f'/api/assets/{cid}/{kind}/{fmt}'
                    check(mode + ' foreign download rejected ' + kind + fmt, other.get(path).status_code in (404, 422))
                    response = client.get(path)
                    response.raise_for_status()
                    content = response.content
                    hashes[kind + '.' + fmt] = hashlib.sha256(content).hexdigest()
                    (folder / (kind + '.' + fmt)).write_bytes(content)
                    if fmt == 'wav':
                        with wave.open(io.BytesIO(content)) as wav:
                            check(mode + kind + ' WAV format', wav.getframerate() == 44100 and wav.getsampwidth() == 2)
                            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
                            check(mode + kind + ' actual audible samples', np.any(samples))
                    elif fmt == 'mid':
                        midi = mido.MidiFile(file=io.BytesIO(content))
                        check(mode + kind + ' MIDI notes', any(m.type == 'note_on' and m.velocity for tr in midi.tracks for m in tr))
                    else:
                        root = ET.fromstring(content)
                        check(mode + kind + ' MMP XML', root.tag == 'lmms-project')
                        if kind == 'final':
                            melody_notes = []
                            for track in root.findall('.//trackcontainer/track'):
                                if track.get('name', '').startswith('melody:'):
                                    for pattern in track.findall('pattern'):
                                        for note in pattern.findall('note'):
                                            start = (int(pattern.get('pos', 0)) + int(note.get('pos', 0))) * 10
                                            end = start + int(note.get('len', 0)) * 10
                                            melody_notes.append((start, end))
                            check(mode + ' exported main melody identified', bool(melody_notes))
                            check(mode + ' intentional blank has no main melody overlap', all(end <= 11520 or start >= 13440 for start, end in melody_notes))
            project = post(client, '/api/confirm', dict(fingerprint=project['fingerprint'], candidate_id=cid))
            accepted = project['fingerprint']
            check(mode + ' one candidate applied', sum(bool(x['applied']) for x in project['candidates']) == 1)
            check(mode + ' memory and silence retained', bool(project['blanks']) and bool(project['memory']['placement_id']))
            project = post(client, '/api/edit', dict(fingerprint=project['fingerprint'], action='undo', args={}))
            check(mode + ' undo confirmation', project['fingerprint'] != accepted and not any(x['applied'] for x in project['candidates']))
            project = post(client, '/api/edit', dict(fingerprint=project['fingerprint'], action='redo', args={}))
            check(mode + ' redo exact snapshot', project['fingerprint'] == accepted)
            check(mode + ' applied audio is preview audio', hashlib.sha256(client.get(f'/api/assets/{cid}/final/wav').content).hexdigest() == hashes['final.wav'])
            states.append(dict(mode=mode, cookies=dict(client.cookies), fingerprint=project['fingerprint'], candidate_id=cid, hashes=hashes))
        state_file = OUT / 'private-restart-state.json'
        state_file.write_text(json.dumps(states))
        state_file.chmod(0o600)


def after_restart():
    for state in json.loads((OUT / 'private-restart-state.json').read_text()):
        with httpx.Client(base_url=URL, cookies=state['cookies'], timeout=90) as client:
            response = client.get('/api/project')
            response.raise_for_status()
            check(state['mode'] + ' restart project fingerprint', response.json()['fingerprint'] == state['fingerprint'])
            for file, digest in state['hashes'].items():
                kind, fmt = file.split('.')
                response = client.get(f'/api/assets/{state["candidate_id"]}/{kind}/{fmt}')
                response.raise_for_status()
                check(state['mode'] + ' restart download ' + file, hashlib.sha256(response.content).hexdigest() == digest)


def music_check():
    evidence = []
    for state in json.loads((OUT / 'private-restart-state.json').read_text()):
        mode = state['mode']
        with httpx.Client(base_url=URL, cookies=state['cookies'], timeout=90) as client:
            project = client.get('/api/project').json()
            def notes(content):
                root = ET.fromstring(content)
                result = []
                for track in root.findall('.//trackcontainer/track'):
                    if track.get('name', '').startswith('melody:'):
                        for pattern in track.findall('pattern'):
                            for note in pattern.findall('note'):
                                result.append(((int(pattern.get('pos', 0))+int(note.get('pos', 0)))*10,
                                               int(note.get('key'))+12,int(note.get('len'))*10))
                return sorted(result), root
            final, xml = notes((OUT / mode / 'final.mmp').read_bytes())
            memory = project['memory']
            placement = next(p for p in project['placements'] if p['id'] == memory['placement_id'])
            region = memory['range']
            expected = [(placement['start_tick']+n['start_tick'], n['pitch'], n['duration_tick'])
                        for n in placement['base_snapshot']['notes']
                        if placement['start_tick']+n['start_tick'] < region['end_tick'] and
                           placement['start_tick']+n['start_tick']+n['duration_tick'] > region['start_tick']]
            actual = [n for n in final if n[0] < region['end_tick'] and n[0]+n[2] > region['start_tick']]
            check(mode+' memory exported pitch and rhythm preserved', sorted(expected)==actual)
            check(mode+' bridge protection retained', any(p['kind']=='bridge' for p in project['protections']))
            melodies = []
            for candidate in project['candidates']:
                response = client.get(f'/api/assets/{candidate["id"]}/final/mmp')
                response.raise_for_status()
                melodies.append(notes(response.content)[0])
            check(mode+' candidates have actual music differences', len(melodies)>=2 and len({tuple(n) for n in melodies})==len(melodies))
            drums = xml.findall('.//audiofileprocessor')
            if mode=='arranged':
                check('arranged real drum layers', len(drums)>=3)
            else:
                check('melody only has no accompaniment', len(xml.findall('.//trackcontainer/track'))==1 and not drums)
            evidence.append(dict(mode=mode,candidate_count=len(melodies),memory_notes=len(expected),
                                 bridge_regions=[p for p in project['protections'] if p['kind']=='bridge'],
                                 drum_layers=len(drums)))
    (OUT / 'music-evidence.json').write_text(json.dumps(evidence,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--after-restart', action='store_true')
    parser.add_argument('--music-check', action='store_true')
    args = parser.parse_args()
    if args.music_check:
        music_check()
    elif args.after_restart:
        after_restart()
    else:
        prepare()
    report = 'music-report.json' if args.music_check else 'restart-report.json' if args.after_restart else 'acceptance-report.json'
    (OUT / report).write_text(json.dumps({'checks': REPORT}, indent=2))
    print('DEPLOYMENT_ACCEPTANCE_PASS', len(REPORT), flush=True)
