"""Canonical JSON with an optional byte-compatible compiled accelerator."""
import json
import os

try:
    import emoblocks_json_native as _native
except (ImportError, OSError):
    _native = None


def encoder_name():
    return 'native' if _native is not None and os.environ.get('EMOBLOCKS_JSON_ENCODER') != 'stdlib' else 'stdlib'


def _native_bytes(value):
    if encoder_name() == 'native':
        try:
            return _native.dumps(value)
        except (ValueError, TypeError, RecursionError):
            # Custom types, deep structures, large integers and surrogate text
            # retain the original encoder's semantics and rejection behavior.
            pass
    return None


def dumps_text(value):
    encoded = _native_bytes(value)
    if encoded is not None:
        return encoded.decode('utf-8')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def dumps_bytes(value):
    encoded = _native_bytes(value)
    if encoded is not None:
        return encoded
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
