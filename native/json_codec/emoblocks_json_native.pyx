"""Preserve CPython float spelling before Rust JSON encoding. No persistent cache."""
from libc.math cimport isfinite
import orjson

cdef object prepare(object value, dict memo, set active, int depth):
    cdef object kind = type(value)
    cdef object key, item, result, identity
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
                result[key] = prepare(item, memo, active, depth + 1)
        else:
            result = [prepare(item, memo, active, depth + 1) for item in value]
        memo[identity] = result
        return result
    finally:
        active.remove(identity)

def dumps(value):
    """Return canonical UTF-8 bytes or request the standard encoder fallback."""
    return orjson.dumps(prepare(value, {}, set(), 0), option=orjson.OPT_SORT_KEYS)


cdef object clone_value(object value, dict memo, int depth):
    cdef object kind=type(value)
    cdef object identity, result, key, item
    if kind is str or kind is int or kind is float or kind is bool or value is None:
        return value
    if kind is not dict and kind is not list or depth>200:
        raise TypeError('Use standard deepcopy for custom/deep data')
    identity=id(value)
    if identity in memo:return memo[identity]
    if kind is dict:
        result={};memo[identity]=result
        for key,item in (<dict>value).items():
            result[clone_value(key,memo,depth+1)]=clone_value(item,memo,depth+1)
    else:
        result=[];memo[identity]=result
        for item in value:result.append(clone_value(item,memo,depth+1))
    return result


def clone(value):
    """Copy exact JSON containers, preserving aliases/cycles, never retaining memo."""
    return clone_value(value,{},0)
