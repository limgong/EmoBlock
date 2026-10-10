"""One owned process per generation, with cooperative cancellation."""
import json
import os
import sys
import time
from pathlib import Path
folder = Path(sys.argv[1]).resolve()
os.environ['EMOBLOCKS_DATA_DIR'] = str(folder / 'assets')
from .core import recommendations
from curve_json import encoder_name
import curve_graph
began = time.perf_counter()
cpu_began = time.process_time()
events = []

def write(name, data):
    target = folder / name
    temp = target.with_suffix('.part')
    temp.write_text(curve_graph.dumps(data) if name=='output.json' else
                    json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(target)

def progress(event):
    events.append(dict(seq=event['seq'], phase=event['phase'],
        elapsed_seconds=time.perf_counter()-began, cpu_seconds=time.process_time()-cpu_began))
    timing('RUNNING')
    write('progress.json', {key: event[key] for key in ('seq', 'phase', 'message')})
    return not (folder / 'cancel').exists()

def timing(status):
    try:
        write('timings.json', dict(encoder=encoder_name(), status=status, events=events,
            elapsed_seconds=time.perf_counter()-began, cpu_seconds=time.process_time()-cpu_began))
    except OSError:
        pass  # Optional telemetry must not turn a valid result into a failure.

try:
    data = json.loads((folder / 'input.json').read_text())
    result = recommendations.prepare_recommendations(data['request'], source_facts=data['source_facts'],
        should_cancel=lambda: (folder / 'cancel').exists(), on_progress=progress, include_stage_bundle=False)
    write('output.json', result)
    timing(result['status'])
except Exception as exc:
    write('error.json', {'code': getattr(exc, 'code', 'GENERATION_FAILED'), 'message': str(exc)})
    timing('FAILED')
    sys.exit(1)
