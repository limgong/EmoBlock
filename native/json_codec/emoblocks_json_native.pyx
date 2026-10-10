"""Preserve CPython float spelling before Rust JSON encoding. No persistent cache."""
from libc.math cimport isfinite
import orjson
frozen_support = True

cdef object prepare(object value, dict memo, set active, int depth, tuple frozen_types):
    cdef object kind = type(value)
    cdef object key, item, result, identity
    if kind in frozen_types:
        return orjson.Fragment(value.canonical_bytes())
    if kind is float:
        if not isfinite(<double>value):
            raise ValueError('Non-finite JSON number')
        return orjson.Fragment(repr(value).encode('ascii'))
    if kind is str or kind is int or kind is bool or value is None:
        return value
    if kind is not dict and kind is not list and kind is not tuple:
        raise TypeError('Use the standard encoder for custom types')
    if depth > 200:
        raise ValueError('Use the standard encoder for deep structures')
    identity = id(value)
    if identity in active:
        raise ValueError('Circular JSON structure')
    if identity in memo:
        return memo[identity]
    active.add(identity)
    try:
        if kind is dict:
            result = {}
            for key, item in (<dict>value).items():
                if type(key) is not str:
                    raise TypeError('Use the standard encoder for non-string keys')
                result[key] = prepare(item, memo, active, depth + 1, frozen_types)
        else:
            result = [prepare(item, memo, active, depth + 1, frozen_types) for item in value]
        memo[identity] = result
        return result
    finally:
        active.remove(identity)

def dumps(value, tuple frozen_types=()):
    """Return canonical UTF-8 bytes or request the standard encoder fallback."""
    return orjson.dumps(prepare(value, {}, set(), 0, frozen_types), option=orjson.OPT_SORT_KEYS)


cdef object clone_value(object value, dict memo, int depth, tuple frozen_types):
    cdef object kind=type(value)
    cdef object identity, result, key, item
    if kind is str or kind is int or kind is float or kind is bool or value is None:
        return value
    if kind is not dict and kind is not list and kind not in frozen_types or depth>200:
        raise TypeError('Use standard deepcopy for custom/deep data')
    identity=id(value)
    # Interned immutable nodes may represent distinct original containers.
    # Expand each occurrence; memoization is only for ordinary mutable inputs.
    if kind not in frozen_types and identity in memo:return memo[identity]
    if kind is dict or (frozen_types and kind is frozen_types[0]):
        result={}
        if kind not in frozen_types:memo[identity]=result
        for key,item in (<dict>value).items():
            result[clone_value(key,memo,depth+1,frozen_types)]=clone_value(item,memo,depth+1,frozen_types)
    else:
        result=[]
        if kind not in frozen_types:memo[identity]=result
        for item in value:result.append(clone_value(item,memo,depth+1,frozen_types))
    return result


def clone(value, tuple frozen_types=()):
    """Copy exact JSON containers, preserving aliases/cycles, never retaining memo."""
    return clone_value(value,{},0,frozen_types)


cdef object expand_node(list nodes, int index, int depth):
    if depth>200 or index<0 or index>=len(nodes):
        raise ValueError('Invalid JSON graph expansion')
    cdef object node=nodes[index], item, edge, result
    if node[0]==0:
        result={}
        for item in node[1]:
            edge=item[1]
            result[item[0]]=edge[1] if edge[0]==0 else expand_node(nodes,edge[1],depth+1)
    else:
        result=[]
        for edge in node[1]:
            result.append(edge[1] if edge[0]==0 else expand_node(nodes,edge[1],depth+1))
    return result


def expand_graph(list nodes, int root):
    """Caller validates the complete bounded, backward-reference graph first."""
    return expand_node(nodes,root,0)
