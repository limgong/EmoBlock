"""Independent JSON snapshots, with standard deepcopy for other Python objects."""
import copy
import os

import curve_json


def _clone(value, memo, depth=0):
    kind=type(value)
    if kind in (str,int,float,bool) or value is None:return value
    if kind in curve_json.curve_frozen.TYPES:return curve_json.curve_frozen.thaw(value)
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
    if memo is not None:return copy.deepcopy(value,memo)
    if os.environ.get('EMOBLOCKS_JSON_COPY')=='stdlib':
        plain=(curve_json.curve_frozen.thaw(value) if curve_json.curve_frozen.contains_frozen(value) else value)
        return copy.deepcopy(plain)
    native=getattr(curve_json._native,'clone',None)
    try:
        if native is not None:
            return (native(value,curve_json.curve_frozen.TYPES) if getattr(curve_json._native,'frozen_support',False)
                    else native(value))
        return _clone(value,{})
    except (TypeError,ValueError,RecursionError):
        # Older optional extensions and tuple/custom fallbacks must not turn
        # content-interned snapshots into shared editable children.
        plain=(curve_json.curve_frozen.thaw(value) if curve_json.curve_frozen.contains_frozen(value) else value)
        return copy.deepcopy(plain)
