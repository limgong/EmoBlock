"""Explicit allowlist: no git metadata, user songs, models, keys, or environments."""
from pathlib import Path
import tarfile,hashlib,json,sys
root=Path(__file__).resolve().parents[2]
output=Path(sys.argv[1]).resolve();output.parent.mkdir(parents=True,exist_ok=True)
files=[]
for folder in ('backend','assets/samples','web_demo/api','web_demo/deploy','web_demo/client/src'):
 for p in (root/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc',) and p.name!='.env':files.append(p)
for name in ('pyproject.toml','setup.py','emoblocks_json_native.pyx'):
 files.append(root/'native/json_codec'/name)
for name in ('web_demo/README.md','web_demo/requirements.lock.txt','web_demo/client/package.json','web_demo/client/package-lock.json','web_demo/client/tsconfig.json','web_demo/client/vite.config.ts','web_demo/client/index.html'):
 files.append(root/name)
with tarfile.open(output,'w:gz') as tar:
 for p in sorted(files):tar.add(p,arcname=str(p.relative_to(root)),recursive=False)
output.with_suffix('.manifest.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},indent=2))
print(output,output.stat().st_size,len(files))
