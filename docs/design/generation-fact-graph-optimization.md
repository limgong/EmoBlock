# Generation fact compaction

## Scope

This change preserves the musical rules, request/result schemas, canonical JSON
bytes, domain fingerprints, deterministic IDs and the existing decision that
`none` is a valid transition. It does not enable the experimental C++ composer.

An empty Bridge plan without inherited Bridges, or an empty connection plan,
can register an authenticated empty raw result directly. Plan validation,
finish-result validation, protection registration and ordinary boundary
processing still run. A nonempty plan or inherited Bridge must use the existing
composer. Cancellation remains a terminal result rather than fake success.

## Operation-local validation views

Pure validators receive private read-only snapshots interned by complete
content. Mutable inputs are traversed again on every call, so nested edits get a
new snapshot and cache key. Canonical bytes and domain digests can be reused only
on these immutable snapshots. The operation scope is released on success,
cancellation and exception; interning and byte caching have explicit budgets.
Live audio/asset file authentication is not cached by these data validators.

Snapshots never become editable project objects. Copying interned containers
expands each occurrence independently, including equal empty lists. Ordinary
mutable inputs retain their existing deepcopy alias, cycle and custom-hook
behavior. The optional native codec and standard Python fallback produce the
same canonical bytes and musical fingerprints.

## Storage and worker transport

Large current P7 saved bundles, Web session files and worker result files can use
the private `emoblocks.json-graph.v1` envelope. Equal dictionaries and arrays are
stored once as a backward-reference DAG. Small values remain ordinary JSON.
The API's public project and candidate responses remain ordinary objects.

Reading validates the entire envelope, references, key uniqueness, finite
scalars, reachability, expanded size and depth before expansion. Expansion
restores independent editable dictionaries/lists, then the existing project,
source, musical protection and result validators run. Saving validates the
graph's expansion bounds before writing it. The decoder accepts existing plain
current-format JSON. Older application releases without this codec cannot read
new compact envelopes; MIDI/MMP/WAV exports are unchanged.

## Verification

Regression tests cover canonical byte equality, original-input edits within a
validation scope, returned-copy independence, ordinary deepcopy behavior,
compacted/plain round trips, malformed graphs, expansion limits, empty-plan
registration/cancellation, positive-plan rejection and continued boundary
processing. Existing musical/transaction tests remain enabled, including
memory, blank regions, source closure, acceptance, undo/redo, persistence,
stale results and actual asset validation.

The performance comparison must replay the same frozen 32-beat input, with two
candidate pipelines, identical CPU/memory limits, alternating order and three
pairs. Compare complete request hashes, score notes/layers and exported MIDI
hashes. Measure the renderer separately from progress-tag intervals, which also
include validation/copying/encoding. No profiler may run during these timings.
Actual listening and Windows device acceptance are separate manual checks.

A mapped desktop regression exposed a tooltip refresh race: rebinding an
unchanged hint cancelled the pending focus/hover timer and destroyed an already
visible tip. Shared UI refresh now preserves that timer and updates an existing
tip in place, with the same palette and bounded geometry. Tests explicitly
check timer/window identity and that passive tips do not alter persistent
details; both platform adapter contracts remain unchanged.
