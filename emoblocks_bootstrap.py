"""Resolve one shared UI plus platform adapters and backend."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def configure(platform=None,include_frontend=True):
    name=platform or ('macos' if sys.platform=='darwin' else 'windows')
    if name not in ('windows','macos'):raise ValueError('Supported frontends: windows, macos')
    paths=[ROOT/'backend'/'core',ROOT/'backend'/'step2',ROOT/'backend'/'step1']
    if include_frontend:paths=[ROOT/'frontend'/name,ROOT/'frontend'/'shared']+paths
    for path in reversed(paths):
        if str(path) not in sys.path:sys.path.insert(0,str(path))
    return name
