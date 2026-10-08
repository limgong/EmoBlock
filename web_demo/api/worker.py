"""One owned process per generation, with cooperative cancellation."""
import json
import os
import sys
from pathlib import Path
folder = Path(sys.argv[1]).resolve()
os.environ['EMOBLOCKS_DATA_DIR'] = str(folder / 'assets')
from .core import recommendations

def write(name, data):
    target = folder / name
    temp = target.with_suffix('.part')
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(target)

def progress(event):
    write('progress.json', {key: event[key] for key in ('seq', 'phase', 'message')})
    return not (folder / 'cancel').exists()

try:
    data = json.loads((folder / 'input.json').read_text())
    result = recommendations.prepare_recommendations(data['request'], source_facts=data['source_facts'],
        should_cancel=lambda: (folder / 'cancel').exists(), on_progress=progress)
    write('output.json', result)
except Exception as exc:
    write('error.json', {'code': getattr(exc, 'code', 'GENERATION_FAILED'), 'message': str(exc)})
    sys.exit(1)
