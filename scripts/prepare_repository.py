"""One-time migration: UI-v2 wins conflicts; preserve previous local files."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'EmoBlocks-Windows-20260926-UI-v2'/'EmoBlocks'
BACKUP=ROOT/'work'/'sync-backup-20261001'
if (ROOT/'backend'/'core'/'story_engine.py').exists():raise SystemExit('Migration already prepared; refusing to overwrite canonical files.')
BACKEND={'story_engine','flow_engine','structure_engine','local_engine','studio_model','emotion_input','intensity_curve','default_melody','block_editor','block_audition','audio_import','audio_import_worker'}
changes=[]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
for app in ('EmoBlocks','EmoBlocks-Step1','EmoBlocks-Step2'):
    for source in sorted((SOURCE/'app'/app).rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts:continue
        relative=source.relative_to(SOURCE/'app'/app)
        if source.suffix not in ('.py','.md','.txt','.mid','.mmp'):continue
        target=ROOT/'outputs'/app/relative
        if digest(source)!=digest(target):
            if target.exists():copy(target,BACKUP/'outputs'/app/relative)
            changes.append(dict(path=target.relative_to(ROOT).as_posix(),before=digest(target),after=digest(source),action='added' if not target.exists() else 'replaced'))
            copy(source,target)
        if source.suffix=='.py' and len(relative.parts)==1:
            if source.name.startswith(('test_','verify_')):
                suite={'EmoBlocks':'core','EmoBlocks-Step1':'step1','EmoBlocks-Step2':'step2'}[app]
                copy(source,ROOT/'tests'/suite/source.name)
            elif app=='EmoBlocks-Step1' and source.name=='engine.py':copy(source,ROOT/'backend'/'step1'/source.name)
            elif app=='EmoBlocks-Step2' and source.name=='material_engine.py':copy(source,ROOT/'backend'/'step2'/source.name)
            elif app=='EmoBlocks':
                destination=ROOT/'frontend'/'shared'
                if source.stem in BACKEND:destination=ROOT/'backend'/'core'
                elif source.stem in ('audio_player','file_drop'):destination=ROOT/'frontend'/'windows'
                copy(source,destination/source.name)
for source in (SOURCE/'docs').glob('*.md'):
    target=ROOT/'outputs'/source.name
    if digest(source)!=digest(target):
        if target.exists():copy(target,BACKUP/'outputs'/source.name)
        changes.append(dict(path=target.relative_to(ROOT).as_posix(),before=digest(target),after=digest(source),action='document-sync'))
        copy(source,target)
    copy(source,ROOT/'docs'/'design'/source.name)
for source in (SOURCE/'samples').glob('*'):
    if source.is_file() and source.suffix.lower() in ('.mid','.mmp','.md'):copy(source,ROOT/'assets'/'samples'/source.name)
for source in (SOURCE/'app'/'EmoBlocks-Step1'/'examples').glob('*.mid'):copy(source,ROOT/'assets'/'samples'/source.name)
copy(SOURCE/'README.md',ROOT/'docs'/'UI-v2-original-README.md')
report=dict(authority=SOURCE.relative_to(ROOT).as_posix(),backup=BACKUP.relative_to(ROOT).as_posix(),changes=changes,
            note='Release binaries/caches/user projects are preserved locally and excluded from Git. Canonical source follows UI-v2, with subsequent platform/path adaptations.')
(ROOT/'docs'/'sync-report-20261001.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(changed=len(changes),replaced=sum(c['before'] is not None for c in changes),report='docs/sync-report-20261001.json'),ensure_ascii=False))
