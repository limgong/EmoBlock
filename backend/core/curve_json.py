"""Canonical JSON with an optional byte-compatible compiled accelerator."""
import json
import os
import curve_frozen

try:
    import emoblocks_json_native as _native
except (ImportError, OSError):
    _native = None


def encoder_name():
    return 'native' if _native is not None and os.environ.get('EMOBLOCKS_JSON_ENCODER') != 'stdlib' else 'stdlib'


def _native_bytes(value):
    if type(value) in curve_frozen.TYPES:
        try:
            return value.canonical_bytes()
        except UnicodeEncodeError:
            return None
    if encoder_name() == 'native':
        try:
            return (_native.dumps(value, curve_frozen.TYPES) if getattr(_native, 'frozen_support', False)
                    else _native.dumps(value))
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
