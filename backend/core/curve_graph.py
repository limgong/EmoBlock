"""Lossless acyclic JSON storage: equal containers stored once, copies on read."""
import json
import math

import curve_frozen
import curve_json

SCHEMA = 'emoblocks.json-graph.v1'
MAX_NODES = 262144
MAX_BYTES = 128 * 1024 * 1024


def pack(value):
    with curve_frozen.scope():
        frozen = curve_frozen.freeze(value)
        nodes = []; seen = {}
        def edge(v):
            if not isinstance(v, (dict, list, tuple)):
                return [0, v]
            if id(v) in seen:
                return [1, seen[id(v)]]
            node = ([0, [[k, edge(item)] for k, item in v.items()]] if isinstance(v, dict)
                    else [1, [edge(item) for item in v]])
            index = len(nodes); nodes.append(node); seen[id(v)] = index
            if len(nodes) > MAX_NODES:
                raise ValueError('Too many JSON graph nodes')
            return [1, index]
        root = edge(frozen)
        if root[0] == 0 or len(nodes) < 64:
            return value
        return dict(schema=SCHEMA, root=root[1], nodes=nodes)


def _inspect(value):
    """Validate before allocating expanded containers or writing a saved graph."""
    if set(value) != {'schema', 'root', 'nodes'}:
        raise ValueError('Invalid JSON graph envelope')
    nodes = value['nodes']; root = value['root']
    if (type(nodes) is not list or not 0 < len(nodes) <= MAX_NODES
            or type(root) is not int or root != len(nodes)-1):
        raise ValueError('Invalid JSON graph root or size')
    sizes = []; depths = []; children = []
    def scalar_size(v):
        if v is not None and type(v) not in (str, int, float, bool):
            raise ValueError('Invalid graph scalar')
        if type(v) is float and not math.isfinite(v):
            raise ValueError('Non-finite graph scalar')
        return len(json.dumps(v, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    def inspect_edge(v, current, refs):
        if type(v) is not list or len(v) != 2 or type(v[0]) is not int:
            raise ValueError('Invalid graph edge')
        if v[0] == 0:
            return scalar_size(v[1]), 0
        index = v[1]
        if v[0] != 1 or type(index) is not int or not 0 <= index < current:
            raise ValueError('Graph references must point backwards')
        refs.append(index)
        return sizes[index], depths[index]
    for i, node in enumerate(nodes):
        if (type(node) is not list or len(node) != 2 or type(node[0]) is not int
                or node[0] not in (0, 1) or type(node[1]) is not list):
            raise ValueError('Invalid graph node')
        refs = []; size = 2; depth = 0; keys = set()
        for j, item in enumerate(node[1]):
            if j: size += 1
            if node[0] == 0:
                if type(item) is not list or len(item) != 2 or type(item[0]) is not str or item[0] in keys:
                    raise ValueError('Invalid or duplicate graph key')
                keys.add(item[0]); size += scalar_size(item[0]) + 1
                item = item[1]
            count, height = inspect_edge(item, i, refs)
            size += count; depth = max(depth, height)
        if size > MAX_BYTES or depth+1 > 200:
            raise ValueError('Expanded JSON graph exceeds size/depth limit')
        sizes.append(size); depths.append(depth+1); children.append(refs)
    reachable = set(); pending = [root]
    while pending:
        index = pending.pop()
        if index not in reachable:
            reachable.add(index); pending.extend(children[index])
    if len(reachable) != len(nodes):
        raise ValueError('Unreachable JSON graph nodes')
    return sizes[root]


def unpack(value):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        return value
    _inspect(value)
    nodes = value['nodes']; root = value['root']
    native = curve_json._native
    if native is not None and hasattr(native, 'expand_graph'):
        return native.expand_graph(nodes, root)
    def expand_edge(v):
        return v[1] if v[0] == 0 else expand(v[1])
    def expand(index):
        kind, items = nodes[index]
        return ({k: expand_edge(v) for k, v in items} if kind == 0
                else [expand_edge(v) for v in items])
    return expand(root)


def dumps(value):
    try:
        packed = pack(value)
    except (TypeError, ValueError, RecursionError):
        packed = value
    if packed is not value:
        _inspect(packed)
    return curve_json.dumps_text(packed)


def loads(text):
    return unpack(json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON'))))
