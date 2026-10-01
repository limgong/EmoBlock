import copy
import json
import tempfile
import unittest
from pathlib import Path

import material_engine as e
from runtime_config import ASSETS


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.parent = e.import_theme(ASSETS/'theme-c.mid', name='A')

    def test_source_immutable(self):
        before = copy.deepcopy(self.parent)
        e.generate_candidates(self.parent, 'variant'); e.generate_candidates(self.parent, 'answer')
        self.assertEqual(before, self.parent)

    def test_reproducible(self):
        for kind in ('variant', 'answer'):
            a = e.generate_candidates(self.parent, kind, 33)
            b = e.generate_candidates(self.parent, kind, 33)
            self.assertEqual([x['notes'] for x in a], [x['notes'] for x in b])

    def test_different_seeds(self):
        for kind in ('variant', 'answer'):
            a = e.generate_candidates(self.parent, kind, 1)
            b = e.generate_candidates(self.parent, kind, 2)
            self.assertNotEqual([x['notes'] for x in a], [x['notes'] for x in b])

    def test_unique_candidates_and_lineage(self):
        for kind in ('variant', 'answer'):
            items = e.generate_candidates(self.parent, kind, 22)
            self.assertEqual(len(items), 3)
            self.assertEqual(len({tuple(e.signature(e.notes_of(x))) for x in items}), 3)
            for item in items:
                self.assertEqual(item['parents'], [self.parent['id']])
                self.assertFalse(item['accepted']); e.validate(item)

    def test_preserve_variant_opening(self):
        opening = [n for n in self.parent['notes'] if n['start'] < e.BAR]
        for item in e.generate_candidates(self.parent, 'variant'):
            self.assertEqual(opening, [n for n in item['notes'] if n['start'] < e.BAR])

    def test_answer_cadence(self):
        for item in e.generate_candidates(self.parent, 'answer'):
            self.assertEqual(item['notes'][-1]['pitch'] % 12, item['tonic'])
            self.assertEqual(item['notes'][-1]['start'] + item['notes'][-1]['duration'], item['bars']*e.BAR)

    def test_copy_transpose_rejected(self):
        ns = e.notes_of(self.parent)
        with self.assertRaises(ValueError): e.quality(self.parent, ns)
        with self.assertRaises(ValueError): e.quality(self.parent, [e.Note(n.pitch+2,n.start,n.duration,n.velocity) for n in ns])

    def test_pool_roundtrip(self):
        pool = e.new_pool(); e.add_item(pool, self.parent)
        for item in e.generate_candidates(self.parent): e.add_item(pool, item)
        for item in e.generate_candidates(self.parent, 'answer'): e.add_item(pool, item)
        with tempfile.TemporaryDirectory() as tmp:
            path = e.save_pool(pool, Path(tmp)/'pool.json')
            self.assertEqual(pool, e.load_pool(path))
            with self.assertRaises(FileExistsError): e.save_pool(pool, path)

    def test_midi_handoff(self):
        for kind in ('variant', 'answer'):
            item = e.generate_candidates(self.parent, kind)[0]
            with tempfile.TemporaryDirectory() as tmp:
                folder, _ = e.export_material(item, tmp, render=False)
                source = e.music.load_source(folder/'melody.mid')
                melody, bars = e.music.select_melody(source)
                self.assertEqual(e.signature(melody.notes), e.signature(e.notes_of(item)))
                self.assertEqual(bars, item['bars'])
                arrangement = e.music.arrange(source, 0, e.music.Options(emotion='hope'))
                self.assertEqual(arrangement['total_ticks'], item['bars']*e.BAR)

    def test_three_sources(self):
        for path in sorted(ASSETS.glob('theme-*.mid')):
            source = e.music.load_source(path)
            _, bars = e.music.select_melody(source)
            parent = e.import_theme(path, bars=bars)
            for kind in ('variant', 'answer'):
                items = e.generate_candidates(parent, kind, 7)
                self.assertEqual(len(items), 3)
                for item in items: e.validate(item)

    def test_user_mmp_requires_explicit_polyphony_choice(self):
        path = ASSETS/'EmoBlocks-Calm.mmp'
        with self.assertRaises(ValueError): e.import_theme(path, trim_overlaps=True)
        item = e.import_theme(path, trim_overlaps=True, simultaneous='lower')
        self.assertEqual(item['import_report']['discarded_simultaneous_notes'], 1)
        self.assertEqual(len(e.generate_candidates(item, 'answer')), 3)

    def test_second_half_slice(self):
        item = e.import_theme(ASSETS/'EmoBlocks-Calm.mmp', start_bar=5, bars=4,
                              trim_overlaps=True, simultaneous='lower')
        self.assertEqual(item['notes'][0]['start'], 0)
        self.assertEqual(item['source']['start_bar'], 5)

    def test_invalid_ranges(self):
        path = ASSETS/'theme-c.mid'
        for start, bars in ((0,4), (1,3), (99,4), (1,9)):
            with self.assertRaises(ValueError): e.import_theme(path, start_bar=start, bars=bars)

    def test_pool_context_conflicts(self):
        pool = e.new_pool(); e.add_item(pool, self.parent)
        other = copy.deepcopy(self.parent); other['id'] = 'a'*32; other['bpm'] += 10
        with self.assertRaises(ValueError): e.add_item(pool, other)
        with self.assertRaises(ValueError): e.add_item(pool, self.parent)

    def test_missing_parent(self):
        child = e.generate_candidates(self.parent)[0]
        with self.assertRaises(ValueError): e.add_item(e.new_pool(), child)

    def test_unsafe_project_id(self):
        pool = e.new_pool(); pool['id'] = '../../outside'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.json'; e.write_json(path,pool)
            with self.assertRaises(ValueError): e.load_pool(path)

    def test_invalid_notes(self):
        for field, value in [('pitch', 200), ('start', -1), ('duration', 0)]:
            item = copy.deepcopy(self.parent); item['notes'][0][field] = value
            with self.assertRaises(ValueError): e.validate(item)

    def test_uniform_velocity(self):
        for kind in ('variant', 'answer'):
            for item in e.generate_candidates(self.parent, kind):
                self.assertEqual({n['velocity'] for n in item['notes']}, {80})


if __name__ == '__main__':
    unittest.main()
