"""Generate real neutral previews and verify Step 2 -> Step 1 handoffs."""
import hashlib
import uuid
from pathlib import Path
import material_engine as e


def run():
    from runtime_config import ASSETS, data_root
    root = data_root()/'step2/demo'/uuid.uuid4().hex[:10]; root.mkdir(parents=True)
    paths = [ASSETS/'EmoBlocks-Calm.mmp'] + list(ASSETS.glob('theme-*.mid'))
    results = []
    for i, path in enumerate(paths):
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        source = e.music.load_source(path)
        _, bars = e.music.select_melody(source)
        parent = e.import_theme(path, bars=bars, name='A', trim_overlaps=True,
                                simultaneous='lower' if i == 0 else 'reject')
        variant = e.generate_candidates(parent, 'variant', 31)[0]; variant['name'] = 'A_c1'
        answer = e.generate_candidates(parent, 'answer', 31)[0]; answer['name'] = 'E'
        # These demo candidates remain unaccepted until the user listens.
        pool = e.new_pool()
        for item in (parent, variant, answer): e.add_item(pool,item)
        pool_path = e.save_pool(pool, root/f'pool-{i+1}.json')
        entry = dict(source=str(path), pool=str(pool_path), materials=[])
        for item in pool['items']:
            folder, report = e.export_material(item, root/f'source-{i+1}')
            assert report['audio']['peak'] > .001
            assert report['audio']['clipped_samples'] == 0
            assert report['audio']['dry_clipped_samples'] == 0
            entry['materials'].append(dict(name=item['name'], kind=item['kind'], folder=str(folder), audio=report['audio']))
            print(f"Rendered {i+1}: {item['name']}", flush=True)
        if i < 2:
            # Exact same MIDI handoff that the combined UI exports.
            exported = Path(entry['materials'][-1]['folder'])/'melody.mid'
            received = e.music.load_source(exported)
            assert e.signature(received.tracks[0].notes) == e.signature(e.notes_of(answer))
            report = e.music.generate(received, 0, e.music.Options(emotion='hope', variation=0, seed=31))
            assert report['audio']['peak'] > .001
            assert report['audio']['clipped_samples'] == 0
            entry['step1_handoff'] = report['output_directory']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        results.append(entry)
    summary = dict(status='technical_checks_passed', neutral_renders=12, emotion_handoffs=2,
                   human_listening_accepted=False, demo_root=str(root), results=results)
    e.write_json(e.ROOT/'verification.json', summary)
    print(str(root), flush=True)


if __name__ == '__main__': run()
