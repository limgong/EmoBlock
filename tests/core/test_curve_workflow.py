"""P1 data behavior; hand-built future records are NOT algorithm/music evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import assembly
import curve_project as m
import curve_session
import curve_store
import default_melody
import story_engine
import studio_model
from runtime_config import ASSETS


def note(ident='n1', length=240, start=0):
    return dict(id=ident, pitch=60, start_tick=start, duration_tick=length, velocity=80,
        origin=dict(source_id='S', track_id='t1', source_note_id='n1'), lineage=[], slice=None)


def material(ident='A1', length=240, kind='block'):
    return dict(id=ident, label='中文长名称 English ' + ident, kind=kind, length_ticks=length, notes=[note(length=length)],
        provenance=dict(source_id='S', original_path='missing original.mid'), generation=None, phrase_id=None, children=[])


def project():
    p = m.new_project()
    p = m.edit(p, 'add_source', source=dict(id='S', label='来源', length_ticks=1920, notes=[note(length=1920)], provenance=dict(file_fingerprint='abc')))
    return m.edit(p, 'add_material', material=material())


def manual_bridge():
    p = m.edit(project(), 'add_material', material=material('bridge', 1920, 'bridge'))
    return m.edit(p, 'place', material_id='bridge', start_tick=1920, placement_id='P')


def connection(p):
    plan = p['records'][-1]
    return dict(id='connection', kind='connection_plan', version=1, status='LOCKED', input_fingerprint=plan['input_fingerprint'],
        dependencies=[dict(id=plan['id'], version=plan['version'])], payload=dict(bridge_plan_id=plan['id'], bridge_plan_version=plan['version'],
        bridge_layout_fingerprint='actual-layout', protection_summary_fingerprint=m.protection_summary(p['protections']), endpoint_refs=[], windows=[], decisions=[]))


class TimelineTests(unittest.TestCase):
    def test_default_and_short_tail(self):
        p = m.new_project(); m.validate(p)
        self.assertEqual((p['bpm'], p['ppq'], p['total_ticks']), (120, 480, 15360))
        self.assertEqual(p['placements'], []); self.assertEqual(m.intensity_at(p, 888), .25)
        p = m.edit(project(), 'place', material_id='A1', start_tick=1200, placement_id='one')
        self.assertEqual(p['placements'][0]['length_ticks'], 240)
        self.assertEqual(m.gaps(p)[0], dict(start_tick=0, end_tick=1200))

    def test_delete_and_move_do_not_pack_or_carry_intensity(self):
        p = m.edit(project(), 'place', material_id='A1', start_tick=1200, placement_id='one')
        p = m.edit(p, 'place', material_id='A1', start_tick=1920, placement_id='two')
        points = [dict(tick=0, level=.2), dict(tick=1920, level=.9), dict(tick=15360, level=.3)]
        p = m.edit(p, 'set_intensity', points=points)
        moved = m.edit(p, 'move', placement_id='one', start_tick=480)
        deleted = m.edit(moved, 'delete', placement_id='one')
        self.assertEqual(deleted['placements'][0]['start_tick'], 1920)
        self.assertEqual(deleted['intensity_points'], points)
        self.assertEqual(deleted['total_ticks'], 15360)
        self.assertNotEqual(m.intensity_at(p, 1200), m.intensity_at(moved, 480))

    def test_overlap_bounds_shrink_atomic(self):
        p = m.edit(project(), 'place', material_id='A1', start_tick=1920, placement_id='one')
        original = copy.deepcopy(p)
        for action, args in [('place', dict(material_id='A1', start_tick=1921)), ('move', dict(placement_id='one', start_tick=15359)), ('resize', dict(grid_count=1))]:
            with self.subTest(action=action), self.assertRaises(m.ProjectError):
                m.edit(p, action, **args)
            self.assertEqual(p, original)
        self.assertEqual(m.edit(p, 'resize', grid_count=10)['total_ticks'], 19200)

    def test_shrink_exact_control_point_keeps_it_as_endpoint(self):
        p = m.edit(project(), 'set_intensity', points=[dict(tick=0, level=.25), dict(tick=3840, level=.8), dict(tick=15360, level=.25)])
        p = m.edit(p, 'resize', grid_count=2)
        self.assertEqual(p['intensity_points'], [dict(tick=0, level=.25), dict(tick=3840, level=.8)])

    def test_intensity_internal_points_not_silently_truncated(self):
        p = m.edit(project(), 'set_intensity', points=[dict(tick=0, level=.2), dict(tick=4000, level=.8), dict(tick=15360, level=.3)])
        with self.assertRaises(m.ProjectError):m.edit(p, 'resize', grid_count=2)
        q = m.edit(p, 'resize', grid_count=3)
        self.assertEqual(q['intensity_points'][1]['tick'], 4000)
        for tick in range(0, 5761, 60):self.assertTrue(0 <= m.intensity_at(q, tick) <= 1)

    def test_explicit_blank_not_gap_and_conflict(self):
        p = m.edit(project(), 'mark_blank', start_tick=0, end_tick=480, blank_id='silence', reason='主动留白')
        self.assertEqual(m.gaps(p), [dict(start_tick=480, end_tick=15360)])
        with self.assertRaises(m.ProjectError):m.edit(p, 'place', material_id='A1', start_tick=240)
        self.assertEqual(m.gaps(m.edit(p, 'delete_blank', blank_id='silence'))[0]['start_tick'], 0)

    def test_repeat_use_independent_emotion_and_snapshot(self):
        p = m.edit(project(), 'place', material_id='A1', start_tick=0, placement_id='one')
        p = m.edit(p, 'place', material_id='A1', start_tick=480, placement_id='two')
        before = copy.deepcopy(p['materials'])
        changed = m.edit(p, 'set_emotion', placement_ids=['two'], emotion='hope')
        self.assertEqual([v['emotion'] for v in changed['placements']], ['calm', 'hope'])
        self.assertEqual(changed['materials'], before)
        self.assertEqual(changed['placements'][1]['base_snapshot'], p['placements'][1]['base_snapshot'])
        self.assertNotEqual(m.placed_notes(changed['placements'][0])[0]['id'], m.placed_notes(changed['placements'][1])[0]['id'])

    def test_nested_combo_actual_notes_and_order(self):
        p = project(); leaf = material(); combo = material('C', 480, 'combination')
        combo['children'] = [dict(occurrence_id='first', offset_tick=0, snapshot=copy.deepcopy(leaf)), dict(occurrence_id='repeat', offset_tick=240, snapshot=copy.deepcopy(leaf))]
        combo['notes'] = [note('c1'), note('c2', start=240)]
        nested = material('D', 720, 'combination')
        nested['children'] = [dict(occurrence_id='combo', offset_tick=0, snapshot=combo), dict(occurrence_id='end', offset_tick=480, snapshot=leaf)]
        nested['notes'] = [note('d1'), note('d2', start=240), note('d3', start=480)]
        p = m.edit(p, 'add_material', material=nested)
        p = m.edit(p, 'place', material_id='D', start_tick=100, placement_id='combo-use')
        self.assertEqual(p['placements'][0]['length_ticks'], 720)
        bad = copy.deepcopy(nested); bad['children'][1]['offset_tick'] = 479
        with self.assertRaises(m.ProjectError):m.edit(project(), 'add_material', material=bad)
        bad = copy.deepcopy(nested); bad['notes'][1]['pitch'] = 70
        with self.assertRaises(m.ProjectError):m.edit(project(), 'add_material', material=bad)

    def test_invalid_data_types_sources_versions(self):
        p = project()
        for key, value in [('grid_count', True), ('bpm', 119), ('spec_rev', 'old'), ('total_ticks', 99), ('selected', 'UI')]:
            bad = copy.deepcopy(p); bad[key] = value
            with self.subTest(key=key), self.assertRaises(m.ProjectError):m.validate(bad)
        bad = copy.deepcopy(p); bad['materials'][0]['notes'][0]['origin']['source_id'] = 'missing'
        with self.assertRaises(m.ProjectError):m.validate(bad)
        bad = copy.deepcopy(p); bad['intensity_points'][0]['level'] = float('nan')
        with self.assertRaises(m.ProjectError):m.validate(bad)
        with self.assertRaises(m.ProjectError):m.edit(p, 'move', placement_id='absent', start_tick=0)
        with self.assertRaises(m.ProjectError):m.edit(p, 'place', material_id='A1')
        with self.assertRaises(m.ProjectError):m.edit(p, 'set_melody_only', value=0)

    def test_new_schema_never_enters_legacy_pipeline(self):
        p = project(); story_engine.validate(p, require_source=False)
        with patch.object(story_engine, 'compile_score', side_effect=AssertionError('old compiler')):
            for call in (story_engine.plan, story_engine.generate):
                with self.assertRaises(m.ProjectError) as exc:call(p)
                self.assertEqual(exc.exception.code, 'PIPELINE_NOT_AVAILABLE')


class SessionTests(unittest.TestCase):
    def test_saved_fingerprint_undo_noop_redo_and_isolation(self):
        s = curve_session.ProjectSession(project()); self.assertFalse(s.is_saved)
        s.mark_saved(); saved = s.project; self.assertTrue(s.is_saved)
        s.edit('place', material_id='A1', start_tick=0, placement_id='one'); self.assertFalse(s.is_saved)
        self.assertTrue(s.undo()); self.assertTrue(s.is_saved); self.assertTrue(s.can_redo)
        self.assertFalse(s.edit('set_melody_only', value=False)); self.assertTrue(s.can_redo)
        token = s.capture()['token']
        with self.assertRaises(m.ProjectError):s.edit('place', material_id='A1', start_tick=-1)
        self.assertEqual(s.project, saved); self.assertTrue(s.accepts(token))
        exported = s.project; exported['sources'].clear(); self.assertEqual(s.project, saved)
        s.redo(); self.assertFalse(s.is_saved)

    def test_old_request_invalid_after_edit_undo_or_finish(self):
        s = curve_session.ProjectSession(project()); snap = s.capture('r'); token = snap['token']
        self.assertTrue(s.accepts(token))
        with self.assertRaises(m.ProjectError):s.capture('r')
        tampered = dict(token, spec_rev='old'); self.assertFalse(s.accepts(tampered))
        snap['project']['materials'].clear(); self.assertTrue(s.project['materials'])
        s.edit('set_melody_only', value=True); s.undo(); self.assertFalse(s.accepts(token))
        new = s.capture('r')['token']; self.assertNotEqual(token['edit_revision'], new['edit_revision'])
        self.assertTrue(s.finish(new)); self.assertFalse(s.finish(new)); self.assertFalse(s.accepts(new))
        self.assertFalse(curve_session.ProjectSession(project()).accepts(new))

    def test_all_fields_change_fingerprint_but_capture_does_not(self):
        s = curve_session.ProjectSession(project()); before = m.fingerprint(s.project)
        s.capture(); self.assertEqual(m.fingerprint(s.project), before); self.assertFalse(s.can_undo)
        for action, args in [('place', dict(material_id='A1', start_tick=0)), ('mark_blank', dict(start_tick=480, end_tick=720)), ('set_melody_only', dict(value=True))]:
            before = m.fingerprint(s.project); s.edit(action, **args); self.assertNotEqual(m.fingerprint(s.project), before)


class ProtectionTests(unittest.TestCase):
    def test_manual_bridge_moves_deletes_undo_with_historical_references(self):
        p = manual_bridge(); c = connection(p); c['payload']['windows'] = [dict(start_tick=6000, end_tick=7000)]; p['records'].append(c); m.validate(p)
        s = curve_session.ProjectSession(p); token = s.capture()['token']
        old = s.project['protections'][0]; s.edit('move', placement_id='P', start_tick=4800)
        moved = s.project; lock = moved['protections'][0]
        self.assertEqual((lock['start_tick'], lock['plan_version']), (4800, 2))
        self.assertEqual(moved['records'][0]['payload']['audit_context']['protections'][0], old)
        first_history = copy.deepcopy(moved['records'][0]['payload']['audit_context'])
        s.edit('delete', placement_id='P'); self.assertFalse(s.project['protections'])
        self.assertEqual(s.project['records'][0]['payload']['audit_context'], first_history)
        m.validate(s.project)
        shrunk = m.edit(s.project, 'resize', grid_count=1)
        m.validate(shrunk)
        with tempfile.TemporaryDirectory() as tmp:
            path = curve_store.save(curve_store.new_bundle(s.project), Path(tmp)/'deleted.json')
            self.assertEqual(curve_store.load(path)['bundle']['project'], s.project)
        s.undo(); self.assertEqual(s.project, moved); s.undo(); self.assertEqual(s.project, p)
        self.assertFalse(s.accepts(token)); s.redo(); m.validate(s.project)

    def test_structure_and_summary_vectors(self):
        p = manual_bridge(); lock = p['protections'][0]
        self.assertEqual(m.protection_summary([]), '2cf0a485a17a17a09bc172687a4418b1b6bb09e2acbd7ae175e5560dd98a2837')
        louder = copy.deepcopy(lock); louder['notes'][0]['velocity'] = 120
        self.assertEqual(m.structure_fingerprint(lock), m.structure_fingerprint(louder))
        self.assertEqual(m.protection_summary([lock]), m.protection_summary([louder]))
        other = copy.deepcopy(lock); other['id'] = 'other'
        self.assertEqual(m.protection_summary([lock, other]), m.protection_summary([other, lock]))
        for field in ('pitch', 'start_tick', 'duration_tick'):
            bad = copy.deepcopy(lock); bad['notes'][0][field] += 1
            self.assertNotEqual(m.structure_fingerprint(lock), m.structure_fingerprint(bad))
        bad = copy.deepcopy(p); bad['protections'][0]['notes'][0]['pitch'] += 1
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_ready_requires_real_content_and_full_notes_no_intrusion(self):
        p = manual_bridge(); lock = p['protections'][0]
        m.validate_protected_notes([lock], lock['notes'])
        for actual in ([], lock['notes'] + [dict(lock['notes'][0], id='added')], [dict(lock['notes'][0], start_tick=1919, duration_tick=1921)]):
            with self.assertRaises(m.ProjectError):m.validate_protected_notes([lock], actual)
        louder = [dict(lock['notes'][0], velocity=60)]; m.validate_protected_notes([lock], louder)
        bad = copy.deepcopy(p); bad['protections'][0]['notes'] = []
        bad['protections'][0]['structure_fingerprint'] = m.structure_fingerprint(bad['protections'][0])
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_future_failed_lock_roundtrip_and_interrupted_attempt(self):
        p = manual_bridge(); bundle = curve_store.new_bundle(project())
        snap = dict(id='input', spec_rev=m.SPEC_REV, contract_rev=m.CONTRACT_REV, content_fingerprint=m.fingerprint(p), project=p)
        bundle['project']['project_id'] = p['project_id']; bundle['snapshots'] = [snap]
        lock = copy.deepcopy(p['protections'][0]); lock.update(origin='automatic', status='RANGE_LOCKED', notes=[], structure_fingerprint=None)
        plan = copy.deepcopy(p['records'][0]); plan.update(status='FAILED')
        plan['payload'].update(automatic_decision='selected', bridge_ids=['P'], manual_bridge_ids=[], ranges=[dict(start_tick=1920, end_tick=3840)])
        attempt = dict(id='candidate', snapshot_id='input', input_fingerprint=snap['content_fingerprint'], state='RUNNING',
            records=[plan], protections=[lock], staged_materials=[], error=dict(code='BRIDGE_GENERATION_FAILED'))
        bundle['attempts'] = [attempt]
        with tempfile.TemporaryDirectory() as tmp:
            path = curve_store.save(bundle, Path(tmp)/'locked.json'); loaded = curve_store.load(path)['bundle']
            self.assertEqual(loaded['attempts'][0]['state'], 'INTERRUPTED')
            self.assertEqual(loaded['attempts'][0]['protections'], [lock]); self.assertEqual(bundle['attempts'][0]['state'], 'RUNNING')
            again = curve_store.save(loaded, Path(tmp)/'again.json'); self.assertEqual(curve_store.load(again)['bundle'], loaded)
        bad = copy.deepcopy(bundle); bad['attempts'][0]['input_fingerprint'] = 'stale'
        with self.assertRaises(m.ProjectError):curve_store.validate_bundle(bad)

    def test_automatic_ready_content_roundtrip_and_missing_result_rejected(self):
        p = manual_bridge(); plan = p['records'][0]; lock = p['protections'][0]
        lock['origin'] = 'automatic'
        plan['payload'].update(automatic_decision='selected', bridge_ids=['P'], manual_bridge_ids=[], ranges=[dict(start_tick=1920, end_tick=3840)])
        with self.assertRaises(m.ProjectError):m.validate(p)
        result = dict(id='bridge-result', kind='bridge_result', version=1, status='READY', input_fingerprint=plan['input_fingerprint'],
            dependencies=[dict(id=plan['id'], version=plan['version'])], payload=dict(bridge_id='P', plan_id=plan['id'], plan_version=plan['version'],
            protection_id=lock['id'], material_snapshot=copy.deepcopy(p['placements'][0]['base_snapshot']), validation=dict(valid=True)))
        p['records'].append(result); m.validate(p)
        with tempfile.TemporaryDirectory() as tmp:
            path = curve_store.save(curve_store.new_bundle(p), Path(tmp)/'actual-ready-fixture.json')
            self.assertEqual(curve_store.load(path)['bundle']['project'], p)
        bad = copy.deepcopy(p); bad['records'][1]['payload']['material_snapshot']['notes'][0]['pitch'] += 1
        with self.assertRaises(m.ProjectError):m.validate(bad)
        bad = copy.deepcopy(p); bad['records'][1]['dependencies'][0]['version'] = 99
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_nonbridge_protection_not_silently_discarded_by_edit(self):
        p = m.edit(project(), 'place', material_id='A1', start_tick=0, placement_id='one')
        lock = copy.deepcopy(manual_bridge()['protections'][0])
        lock.update(id='memory', kind='memory', owner_id='one', placement_id='one', start_tick=0, end_tick=240,
            plan_id=None, plan_version=None, notes=m.placed_notes(p['placements'][0]))
        lock['structure_fingerprint'] = m.structure_fingerprint(lock); p['protections'] = [lock]; m.validate(p)
        s = curve_session.ProjectSession(p)
        for action, args in [('delete', dict(placement_id='one')), ('move', dict(placement_id='one', start_tick=480)), ('set_emotion', dict(placement_ids=['one'], emotion='hope'))]:
            with self.assertRaises(m.ProjectError):s.edit(action, **args)
            self.assertEqual(s.project, p); self.assertFalse(s.can_undo)

    def test_failed_range_lock_blocks_place_blank_move_and_preserves_session(self):
        p = manual_bridge(); p['placements'] = []
        lock = p['protections'][0]
        lock.update(origin='automatic', placement_id=None, status='RANGE_LOCKED', notes=[], structure_fingerprint=None)
        plan = p['records'][0]; plan['status'] = 'FAILED'
        plan['payload'].update(automatic_decision='selected', bridge_ids=['P'], manual_bridge_ids=[], ranges=[dict(start_tick=1920, end_tick=3840)])
        p = m.edit(p, 'place', material_id='A1', start_tick=0, placement_id='safe')
        s = curve_session.ProjectSession(p); before = s.project
        for action, args in [('place', dict(material_id='A1', start_tick=1920)), ('mark_blank', dict(start_tick=1920, end_tick=2160)), ('move', dict(placement_id='safe', start_tick=2160))]:
            with self.assertRaises(m.ProjectError):s.edit(action, **args)
            self.assertEqual(s.project, before); self.assertFalse(s.can_undo)
        m.edit(p, 'place', material_id='A1', start_tick=3840)  # half-open boundary

    def test_payload_reference_cannot_bypass_state_or_summary_with_empty_dependencies(self):
        p = manual_bridge(); plan = connection(p); plan['status'] = 'FAILED'; p['records'].append(plan)
        row = dict(id='connection-result', kind='connection_result', version=1, status='READY', input_fingerprint='input', dependencies=[],
            payload=dict(plan_id=plan['id'], plan_version=1, original_notes=copy.deepcopy(p['protections'][0]['notes']),
                output_notes=copy.deepcopy(p['protections'][0]['notes']), actual_impact_ranges=[], validation={}))
        p['records'].append(row)
        with self.assertRaises(m.ProjectError):m.validate(p)
        plan['status'] = 'LOCKED'; plan['payload']['protection_summary_fingerprint'] = 'stale'
        with self.assertRaises(m.ProjectError):m.validate(p)

    def test_payload_required_array_types_rejected_before_save(self):
        for field in ('endpoint_refs', 'windows', 'decisions'):
            p = manual_bridge(); row = connection(p); row['payload'][field] = 'not-an-array'; p['records'].append(row)
            with self.subTest(field=field), self.assertRaises(m.ProjectError):curve_store.new_bundle(p)
        p = manual_bridge(); p['records'][0]['payload']['reasons'] = 42
        with self.assertRaises(m.ProjectError):m.validate(p)

    def test_connection_data_gate_and_three_intrusions(self):
        p = manual_bridge(); c = connection(p)
        for start, end in [(0, 7680), (1800, 2040), (3000, 4200)]:
            bad = copy.deepcopy(p); row = copy.deepcopy(c); row['payload']['windows'] = [dict(start_tick=start, end_tick=end)]; bad['records'].append(row)
            with self.assertRaises(m.ProjectError):m.validate(bad)
        p['records'].append(c); m.validate(p)
        p['records'][-1]['payload']['windows'] = [dict(start_tick=1440, end_tick=1920)]; m.validate(p)
        for change in ('version', 'not_ready', 'summary'):
            bad = copy.deepcopy(p)
            if change == 'version':bad['records'][-1]['payload']['bridge_plan_version'] = 99
            elif change == 'not_ready':bad['protections'][0].update(status='RANGE_LOCKED', structure_fingerprint=None)
            else:bad['records'][-1]['payload']['protection_summary_fingerprint'] = 'wrong'
            with self.assertRaises(m.ProjectError):m.validate(bad)


class StoreTests(unittest.TestCase):
    def test_accepted_reference_requires_ready_score_real_snapshot_and_acyclic_input(self):
        base = project(); snap = dict(id='input', spec_rev=m.SPEC_REV, contract_rev=m.CONTRACT_REV, content_fingerprint=m.fingerprint(base), project=base)
        p = copy.deepcopy(base)
        score = dict(id='final', kind='final_score', version=1, status='FAILED', input_fingerprint=snap['content_fingerprint'], dependencies=[],
            payload=dict(total_ticks=p['total_ticks'], notes=[], protection_summary_fingerprint=m.protection_summary([]), validation={}))
        accepted = dict(id='accepted', kind='accepted_candidate', version=1, status='READY', input_fingerprint=snap['content_fingerprint'], dependencies=[],
            payload=dict(final_score_id='final', transaction_id='txn', input_snapshot_id='input'))
        p['records'] = [score, accepted]; p['accepted_candidate_id'] = 'accepted'
        with self.assertRaises(m.ProjectError):m.validate(p)
        score['status'] = 'READY'; bundle = curve_store.new_bundle(p)
        with self.assertRaises(m.ProjectError):curve_store.validate_bundle(bundle)
        bundle['snapshots'] = [snap]; curve_store.validate_bundle(bundle)
        with tempfile.TemporaryDirectory() as tmp:
            path = curve_store.save(bundle, Path(tmp)/'accepted-fixture.json'); self.assertEqual(curve_store.load(path)['bundle'], bundle)
        bundle['snapshots'][0]['content_fingerprint'] = 'wrong'
        with self.assertRaises(m.ProjectError):curve_store.validate_bundle(bundle)

    def test_history_metadata_without_report_does_not_break_bundle_roundtrip(self):
        bundle = curve_store.new_bundle(project()); bundle['results'] = [dict(report=None), dict(report=dict(output_directory=''))]
        with tempfile.TemporaryDirectory() as tmp:
            path = curve_store.save(bundle, Path(tmp)/'metadata.json')
            loaded = curve_store.load(path)
            self.assertEqual(loaded['bundle'], bundle)
            self.assertEqual(loaded['capabilities']['history'], [dict(wav=False, midi=False, mmp=False)] * 2)

    def test_two_snapshots_unicode_no_overwrite_and_reopen(self):
        p = m.edit(project(), 'place', material_id='A1', start_tick=1921, placement_id='one')
        p['placements'][0]['base_snapshot']['notes'][0]['duration_tick'] = 239
        # The base length includes a one-tick internal rest. No output quantization.
        bundle = curve_store.new_bundle(p)
        with tempfile.TemporaryDirectory() as tmp:
            first = curve_store.save(bundle, Path(tmp)/'中文 空格 one.json'); old = first.read_bytes()
            second = curve_store.save(bundle, Path(tmp)/'second.json')
            self.assertNotEqual(first, second); self.assertEqual(first.read_bytes(), old)
            self.assertEqual(curve_store.load(second)['bundle'], bundle)
            with self.assertRaises(FileExistsError):curve_store.save(bundle, first)
            self.assertEqual(first.read_bytes(), old)

    def test_write_fault_preserves_old_files_and_session_history(self):
        s = curve_session.ProjectSession(project()); s.mark_saved(); s.edit('place', material_id='A1', start_tick=0)
        before = s.project
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp)/'old.json'; old.write_bytes(b'keep old')
            target = Path(tmp)/'new.json'
            with patch('curve_store.os.fsync', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):curve_store.save(curve_store.new_bundle(s.project), target)
            self.assertFalse(target.exists()); self.assertEqual(old.read_bytes(), b'keep old')
            with self.assertRaises(FileNotFoundError):curve_store.save(curve_store.new_bundle(s.project), Path(tmp)/'absent'/'new.json')
        self.assertEqual(s.project, before); self.assertFalse(s.is_saved); self.assertTrue(s.can_undo)

    def test_bad_load_does_not_mutate_active_session(self):
        s = curve_session.ProjectSession(project()); s.edit('set_melody_only', value=True); before = s.project
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.json'
            for text in ('{broken', '[]', '{"schema":"unknown"}', '{"value":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError):curve_store.load(path)
            self.assertEqual(s.project, before); self.assertTrue(s.can_undo)

    def test_legacy_routes_preserve_payload_and_per_format_availability(self):
        old = assembly.new_project(default_melody.source())
        legacy_story = story_engine.new_project()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'composition.mid').write_bytes(b'midi')
            for item in (old, legacy_story):
                path = root/'raw.json'; path.write_text(json.dumps(item))
                loaded = curve_store.load(path)
                self.assertEqual(loaded['legacy'], item); self.assertEqual(loaded['access_mode'], 'legacy_readonly')
                self.assertFalse(loaded['capabilities']['edit']); self.assertFalse(loaded['capabilities']['plan'])
            pool = studio_model.materials.new_pool()
            report = dict(mode='story', report=dict(output_directory=str(root), duration_seconds=1, bars=1))
            path = studio_model.save_project(pool, None, [dict(emotion='calm', start=.3, end=.5)], [report], settings=dict(story=old), path=root/'studio.json')
            raw = json.loads(path.read_text()); loaded = curve_store.load(path)
            self.assertEqual(loaded['legacy'], raw)
            self.assertEqual(loaded['capabilities']['history'], [dict(wav=False, midi=True, mmp=False)])
            doc = studio_model.quick_document(studio_model.materials.import_theme(ASSETS/'theme-c.mid', name='theme'), [dict(emotion='calm', start=.2, end=.3)])
            structure_path = root/'structure.json'; structure_path.write_text(json.dumps(doc))
            self.assertEqual(curve_store.load(structure_path)['legacy'], doc)
            pool_path = root/'pool.json'; pool_path.write_text(json.dumps(pool)); self.assertEqual(curve_store.load(pool_path)['legacy'], pool)


if __name__ == '__main__':
    unittest.main()
