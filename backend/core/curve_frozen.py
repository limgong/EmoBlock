"""Operation-local immutable JSON views; mutable callers are always re-read."""
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar

_CONTEXT = ContextVar('curve_frozen_json', default=None)
MAX_NODES = 131072
MAX_CACHED_BYTES = 64 * 1024 * 1024


def _readonly(*args, **kwargs):
    raise TypeError('Validation snapshots are read-only')


class _Frozen:
    __slots__ = ()

    def canonical_bytes(self):
        if self._bytes is not None:
            return self._bytes
        import curve_json
        value = dict(self) if isinstance(self, dict) else list(self)
        encoded = curve_json.dumps_bytes(value)
        context = _CONTEXT.get()
        if context is not None and context['bytes'] + len(encoded) <= MAX_CACHED_BYTES:
            self._bytes = encoded
            context['bytes'] += len(encoded)
        return encoded

    def digest(self, domain):
        if domain not in self._digests:
            self._digests[domain] = hashlib.sha256(domain.encode('utf-8') + b'\n' + self.canonical_bytes()).hexdigest()
        return self._digests[domain]

    def __deepcopy__(self, memo):
        import curve_json
        native = curve_json._native
        if native is not None and getattr(native, 'frozen_support', False):
            result = native.clone(self, TYPES)
        else:
            result = thaw(self)
        memo[id(self)] = result
        return result


class FrozenDict(_Frozen, dict):
    __slots__ = ('_bytes', '_digests')
    __init__ = __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly


class FrozenList(_Frozen, list):
    __slots__ = ('_bytes', '_digests')
    __init__ = __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _readonly


TYPES = (FrozenDict, FrozenList)


def contains_frozen(value):
    seen=set(); pending=[value]
    while pending:
        item=pending.pop()
        if type(item) in TYPES:return True
        if type(item) in (dict,list,tuple) and id(item) not in seen:
            seen.add(id(item))
            pending.extend(item.values() if type(item) is dict else item)
    return False


@contextmanager
def scope():
    if _CONTEXT.get() is not None:
        yield
        return
    token = _CONTEXT.set(dict(nodes={}, bytes=0))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def _signature(value):
    if type(value) in TYPES:
        return (type(value), id(value))
    if type(value) is tuple:
        return (tuple, tuple(_signature(v) for v in value))
    return (type(value), repr(value) if type(value) is float else value)


def freeze(value):
    """Intern by complete content, never by a mutable object's persistent id."""
    context = _CONTEXT.get()
    if context is None:
        return value
    memo = {}; active = set()
    def visit(v, depth=0):
        kind = type(v)
        if kind in TYPES or kind in (str, int, float, bool) or v is None:
            return v
        if kind not in (dict, list, tuple) or depth > 200:
            raise TypeError('Use ordinary validation for custom/deep data')
        identity = id(v)
        if identity in active:
            raise ValueError('Circular JSON structure')
        if identity in memo:
            return memo[identity]
        active.add(identity)
        try:
            if kind is dict:
                if any(type(k) is not str for k in v):
                    raise TypeError('Use ordinary validation for non-string keys')
                children = [(k, visit(v[k], depth+1)) for k in sorted(v)]
                key = (dict, tuple((k, _signature(item)) for k, item in children))
            else:
                children = [visit(item, depth+1) for item in v]
                if kind is tuple:
                    result = tuple(children); memo[identity] = result
                    return result
                key = (list, tuple(_signature(item) for item in children))
            result = context['nodes'].get(key)
            if result is None:
                if kind is dict:
                    result = dict.__new__(FrozenDict); dict.__init__(result, children)
                else:
                    result = list.__new__(FrozenList); list.__init__(result, children)
                result._bytes = None; result._digests = {}
                if len(context['nodes']) < MAX_NODES:
                    context['nodes'][key] = result
            memo[identity] = result
            return result
        finally:
            active.remove(identity)
    return visit(value)


def arguments(args, kwargs):
    try:
        return tuple(freeze(v) for v in args), {k: freeze(v) for k, v in kwargs.items()}
    except (TypeError, ValueError, RecursionError):
        return args, kwargs


def thaw(value):
    """Expand interned views independently; retain ordinary mutable aliases."""
    memo = {}
    def visit(v):
        if type(v) not in TYPES and type(v) not in (dict, list, tuple):
            return v
        frozen = type(v) in TYPES
        if not frozen and id(v) in memo:
            return memo[id(v)]
        if isinstance(v, dict):
            result = {}
            if not frozen:memo[id(v)] = result
            result.update((k, visit(item)) for k, item in v.items())
        elif isinstance(v, list):
            result = []
            if not frozen:memo[id(v)] = result
            result.extend(visit(item) for item in v)
        else:
            result = tuple(visit(item) for item in v)
        return result
    return visit(value)
