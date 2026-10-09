"""Independent JSON snapshots, with standard deepcopy for other Python objects."""
import copy
import os

import curve_json


def _clone(value, memo, depth=0):
    kind=type(value)
    if kind in (str,int,float,bool) or value is None:return value
    if kind not in (dict,list) or depth>200:raise TypeError('Use standard deepcopy')
    identity=id(value)
    if identity in memo:return memo[identity]
    result={} if kind is dict else []
    memo[identity]=result
    if kind is dict:
        for key,item in value.items():result[_clone(key,memo,depth+1)]=_clone(item,memo,depth+1)
    else:
        result.extend(_clone(item,memo,depth+1) for item in value)
    return result


def deepcopy(value, memo=None):
    # Caller-supplied memo, subclasses and custom hooks keep CPython semantics.
    if memo is not None or os.environ.get('EMOBLOCKS_JSON_COPY')=='stdlib':
        return copy.deepcopy(value,memo)
    native=getattr(curve_json._native,'clone',None)
    try:return native(value) if native is not None else _clone(value,{})
    except (TypeError,ValueError,RecursionError):return copy.deepcopy(value)
