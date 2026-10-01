"""Headless story planning/rendering, independent of the desktop frontend."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from emoblocks_bootstrap import configure
configure(include_frontend=False)
import default_melody
import emotion_input
import story_engine
from runtime_config import data_root

def main():
    parser=argparse.ArgumentParser(description='EmoBlocks headless backend')
    parser.add_argument('--project',type=Path,help='Story JSON (not a legacy studio envelope)')
    parser.add_argument('--output',type=Path,help='Plan JSON destination')
    parser.add_argument('--render',action='store_true',help='Render using native LMMS')
    args=parser.parse_args()
    if args.project:project=json.loads(args.project.read_text(encoding='utf-8-sig'))
    else:
        project=emotion_input.default_story();project['sources']=[default_melody.source()];project['continuous_intensity']=True
    project=emotion_input.normalize(project)
    if args.render:planned,report=story_engine.generate(project,progress=lambda msg:print(msg,file=sys.stderr))
    else:planned=story_engine.plan(project);report=None
    output=args.output or data_root()/'cli'/'story-plan.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(planned,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(plan=str(output),report=report),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
