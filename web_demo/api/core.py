"""Backend-only entrypoint. Does not configure or import the desktop UI."""
import sys
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for part in ('backend/step1', 'backend/step2', 'backend/core'):
    sys.path.insert(0, str(ROOT / part))
import curve_project as model
import curve_workflow as workflow
import curve_recommendations as recommendations
import curve_store
from curve_material_names import short_name
SAMPLE_CATALOG = json.loads((ROOT / 'assets/samples/classical-catalog.json').read_text(encoding='utf-8'))
SAMPLES = {item['id']: (item['label'], item['file']) for item in SAMPLE_CATALOG}

def controller(sample='joy'):
    value = workflow.Controller(model.new_project(16))
    job = value.capture_job('IMPORT')
    value.apply_batch(workflow.prepare_import(ROOT / 'assets/samples' / SAMPLES[sample][1]), job['token'])
    return value
