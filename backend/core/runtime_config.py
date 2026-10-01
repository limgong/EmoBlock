"""Platform-neutral runtime paths and LMMS resource discovery."""
import os
import shutil
import sys
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[2]
ASSETS=PROJECT_ROOT/'assets'/'samples'
def data_root():
    path=Path(os.environ.get('EMOBLOCKS_DATA_DIR',str(PROJECT_ROOT/'data'))).expanduser().resolve()
    path.mkdir(parents=True,exist_ok=True)
    return path
def find_lmms(platform=None):
    name=platform or sys.platform
    explicit=os.environ.get('EMOBLOCKS_LMMS')
    if explicit:return Path(explicit).expanduser()
    candidates=[]
    if name=='darwin':
        candidates=[Path('/Applications/LMMS.app/Contents/MacOS/lmms'),Path('/Applications/LMMS.app/Contents/MacOS/LMMS'),Path.home()/'Applications/LMMS.app/Contents/MacOS/lmms']
    elif name=='win32':
        candidates=[PROJECT_ROOT/'runtime/LMMS/lmms.exe',PROJECT_ROOT/'work/release-20260926/EmoBlocks/runtime/LMMS/lmms.exe',Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'LMMS/lmms.exe',Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'LMMS/lmms.exe']
    found=shutil.which('lmms')
    if found:candidates.append(Path(found))
    return next((p for p in candidates if p.is_file()),candidates[0] if candidates else Path('lmms'))
def sample_path(executable,filename):
    executable=Path(executable);explicit=os.environ.get('EMOBLOCKS_LMMS_DATA')
    directories=[Path(explicit).expanduser()] if explicit else []
    directories.extend([executable.parent/'data',executable.parent.parent/'Resources',executable.parent.parent/'Resources/data',executable.parent.parent/'share/lmms',Path('/usr/share/lmms')])
    for directory in directories:
        for relative in (Path('samples/drums')/filename,Path('drums')/filename):
            sample=directory/relative
            if sample.is_file():return sample
    raise ValueError('找不到 LMMS 鼓采样 '+filename+'；请设置 EMOBLOCKS_LMMS_DATA 为包含 samples 的资源目录。')
def diagnostics():
    executable=find_lmms();samples={}
    for name in ('bassdrum01.ogg','snare01.ogg','hihat_closed01.ogg'):
        try:samples[name]=str(sample_path(executable,name))
        except ValueError:samples[name]=None
    return dict(platform=sys.platform,lmms=str(executable),lmms_found=executable.is_file(),samples=samples,data_directory=str(data_root()))
