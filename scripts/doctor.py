"""Report native prerequisites; --render produces a real native smoke-test WAV."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from emoblocks_bootstrap import configure
configure(include_frontend=False)
from runtime_config import diagnostics
parser=argparse.ArgumentParser();parser.add_argument('--render',action='store_true');args=parser.parse_args()
report=diagnostics();report['python']=sys.version
try:
    import tkinter
    report['tk_version']=tkinter.TkVersion
except ImportError:report['tk_version']=None
print(json.dumps(report,ensure_ascii=False,indent=2))
if args.render:
    import story_engine,emotion_input,default_melody
    project=emotion_input.default_story();project['sources']=[default_melody.source()];project['continuous_intensity']=True
    planned,result=story_engine.generate(emotion_input.normalize(project))
    print(json.dumps(result,ensure_ascii=False,indent=2))
