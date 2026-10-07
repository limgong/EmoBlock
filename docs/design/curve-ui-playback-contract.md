# UI bounded playback facts — FROZEN interface

RUN_ID=ui-visual-20261008-07fca4c0 TASK_ID=UI0-PLAYBACK-CONTRACT ROUND=1
INTERFACE_REV=curve-ui-playback-v1 STATUS=FROZEN
BASE_SHA=03f2191d586970da0e8fa7a4d597aa905cb39867

No musical/project/asset schema or P7 algorithm changes. Add pure, bounded public getters on existing Controller:

`recommendation_playback(candidate_id, kind='final', mode=None) -> dict`
`history_playback(result_id, mode=None) -> dict`

Return detached JSON-compatible `schema='emoblocks.ui-playback.v1'`, `target` (kind, id, comparison/final, explicit resolved mode), `asset` (existing authenticated asset copy), `score_ref` (exact existing reference or None), `bpm`, `total_ticks`, `notes` (exact selected logical FinalScore notes or None), `segments`, `mapping_available`, `mapping_reason`.

For P7 requests first resolve exact candidate member and mode/kind, call existing recommendation_asset/hash/profile validation and resolve its exact `*_score_ref` and original BoundaryRequest through authenticated final_facts. Independently validate selected FinalScore against its saved BoundaryRequest/BoundaryPlan using existing pure final.validate_final_score. Getter must not decide/compose/arrange/render or alter any store/session/cache-authority. notes and score_ref belong to the selected comparison/final and mode, never top-level default candidate preview. Segments are detached output of existing final._segments(request,kind): for final actual authoritative arrangement segments including genuine bridge/connection/blank ownership; for comparison captured original placements and blanks before processing. Comparison rows may lack owner id: getter attaches the matching original placement/blank id by exact saved range/kind (placements cannot overlap). No live project lookup. No time/name/ID guessing for musical reconstruction; matching only identifies the already-authoritative captured row, not sound or timing.

For accepted P7 history resolve result_id -> candidate_id + persisted mode, delegate same pure authenticated getter and replace target with history result identity. Optional mode must have a ready member, never borrow another mode's cache. Post-accept/edit/undo does not change historical playback facts. Missing asset, changed score ref or mismatched files rejects before playback/navigation; returning a ready cache never authorizes automatic play.

Legacy history with valid existing audio retains playback and format export. No authenticated score/mapping means notes=None, score_ref/bpm/total_ticks=None, segments=[], mapping_available=False and clear reason. Do not invent mappings from live project or acoustic waveform. Legacy mode switching remains rejected. Waveform and clock use actual file only; previous/next disabled with direct explanation.

UI retains immutable copy of capture_job target+BPM for source/material/placement/combo auditions tied to cache identity and asset hash; these do not need the score getter. Their component mapping comes from the captured material snapshot, not current selected/editor. Known missing exact mapping is an honest disabled capability, not fabricated musical data.

UI waveform cached by authenticated content hash, asset identity/version/profile/mode/kind; cache bounded and refreshed on changes. Every seek/navigation revalidates the same original captured asset (neutral `_ready_asset` with old key, P7 exact getter target and score_ref), refusing changed identity, rather than substituting newly-selected audio. Play intent lifecycle and old request token gate stay unchanged. Capture/no-capture cannot manufacture play permission. Timeline highlighter only if displayed snapshot fingerprint matches captured playback snapshot; otherwise player alone shows old object.

Getter reads existing versioned registries, no migrations, persistence or new music IDs. Music saved/dirty/staging/undo/redo/task state unchanged, return mutation detached. Source/notes identities retained. Exact tick integers preserved; mapping uses seconds=tick*60/(480*bpm) plus explicit body/tail distinction, no rescale to audio tail. No public Tk objects/threads/handles.

Tests: selected comparison vs final exact note/ref identity; history A while edit/selection B; mode separation/missing mode; detached return edits; no project/undo/saved/staging mutation; patched decide/generate/arrange/render forbidden; invalid asset rejected; legacy unmapped fallback and invalid mode; unknown candidate/result clear failure. Synthetic renderer fixtures cover getter tests, not real sound quality. Independent integration rechecks genuine file render already accepted, actual Tk/audio separate.

Ownership lead-only backend/core/curve_recommendations.py + focused tests/core/test_curve_playback_facts.py. frontend uses frozen getter only, no private registry reads. Existing signature/return structures and adapters stay compatible. Before front player hookup lead sends exact reviewed doc + implementation commit for fast-forward into own worktree.

# Addendum to playback-interface-v1 — FROZEN ROUND2

RUN_ID=ui-visual-20261008-07fca4c0 TASK_ID=UI0-PLAYBACK-CONTRACT ROUND=2
INTERFACE_REV=curve-ui-playback-v1 STATUS=FROZEN
BASE_SHA=03f2191d586970da0e8fa7a4d597aa905cb39867

R1 F1 correction: no undefined new "playback snapshot fingerprint" field. Matching uses exact existing music identity plus the actual note data displayed; project fingerprint alone NEVER establishes processed music equality.

Target exact structure:
- recommendation: `{kind:'recommendation', id:candidate_id, side:kind_argument, mode:resolved_mode}`
- history: `{kind:'history', id:result_id, side:'final', mode:resolved_mode}`
- legacy history: `{kind:'history', id:result_id, side:'final', mode:None}`.
Returned score_ref is the full existing `{id,version,fingerprint}` Ref, tied to asset.score_ref and the independently validated selected score. notes returns actual score.notes. It is not the base Project fingerprint and no new persistent field.

Canvas playing highlighting requires ALL of the following:
1. An immutable playback context with exact target+side+mode and authenticated asset identity/score_ref, never merely cached readiness.
2. The displayed object is an authenticated score view carrying the SAME score_ref (candidate selected member[side+'_score_ref']; historical exact getter; ACTIVE accepted_state().score_ref only for editor accepted score), with the same side and explicit mode. If editor lacks explicit side/mode identity no score highlight.
3. Actual displayed notes, total_ticks and bpm equal the playback getter's detached notes/ticks/BPM. If currently public recommendation preview only exposes default final notes while another mode/side was selected, do not claim correspondence: use the selected getter notes for readonly view or disable playing highlight. Comparison and final must not borrow each other's preview.
4. If drawing editor placement geometry, playback segment owner/performance must have an explicit matching genuine placement/overlay identity in that same view. Otherwise only waveform/time/block navigation in player, no canvas highlight. A selected source/material audition has no full-score identity and does not highlight editor blocks merely because material id occurs there. It may highlight only the corresponding captured audition/card identity; no highlighting newly edited music.

Neutral audition context stays immutable captured target snapshot + exact captured BPM + existing audition fingerprint/key+authenticated file hash. Matching any source/material card must compare the FULL captured target snapshot against currently displayed target (not just id); audition at engineering placement can highlight only when the entire captured project input fingerprint and placement snapshot still match, not current id/time guess. After editing disable highlight, preserve valid playback itself. No extra persisted schema or synthetic parent identities.

Explicit adversarial tests: same base project but changed bridge/connection/final notes; comparison vs final; mode change; accepted ACTIVE->STALE; history A while editing B; same id modified material; same music after undo doesn't revive expired PlayIntent. Any unavailable identity disables highlight with honest fallback while valid actual waveform/time remain.

Additional concrete UI gap from frontend: add minimal pure `Controller.preview_edit(action, **args) -> {allowed, changed, error}` using SAME model.edit on detached current Project with SAME official recompute service, without committing returned Project or touching Session revision/undo/requests/staging/asset/cache. allowed=True only complete formal transaction validation succeeded; changed indicates result differs. error is existing ProjectError.as_dict shape (code,message,details), no invented ranges/music. READ_ONLY/invalid action errors return allowed=False. UI uses for drop-preview validity only; release still repeats formal Controller.edit so late state changes cannot bypass gate. Pure means no store/files/threads/render, deterministic official protection/emotion recompute allowed exactly as formal transaction. It must not weaken/replace formal validation or delete locks. Expose no future Project or private registry to UI. Lead owns method in curve_workflow plus tests. Test successful and refused move/insert/resize, protection and memory rejection, nonmutation of project/saved/staging/undo/redo/revision/live requests, actual release rejection after intervening edit. Performance measured before assuming usable on motion; cache UI exact snapped target + edit fingerprint only, never across changed inputs.

All other v1 proposal constraints remain. Please independently review combined docs; exact baseline remains frozen during this contract review. Implementation starts only after PASS, no early getter code.
