"""Static platform contract and frontend/backend dependency checks."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def signatures(path,cls=None):
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    if cls:tree=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    return {n.name:ast.dump(n.args,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

def check():
    errors=[]
    contracts={'ui_platform.py':(None,('create_root','font_family','wheel_units','setup_window','prepare_process','configure_scaling','taskbar','work_area','edit_shortcut','open_folder')),
               'audio_player.py':('WavePlayer',('play','status','pause','resume','close')),
               'file_drop.py':('FileDrop',('__init__','close'))}
    for filename,(cls,names) in contracts.items():
        win=signatures(ROOT/'frontend/windows'/filename,cls);mac=signatures(ROOT/'frontend/macos'/filename,cls)
        for name in names:
            if name not in win or name not in mac or win[name]!=mac[name]:errors.append(filename+': incompatible '+name)
    for folder in ('backend','frontend/shared','frontend/macos'):
        forbidden={'winsound','ctypes'}
        if folder=='backend':forbidden.update({'tkinter','unified_ui','story_ui','ui_platform','audio_player','file_drop'})
        for path in (ROOT/folder).rglob('*.py'):
            tree=ast.parse(path.read_text(encoding='utf-8-sig'))
            imports={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
            imports.update(n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module)
            bad=imports&forbidden
            if bad:errors.append(str(path.relative_to(ROOT))+': forbidden dependencies '+','.join(sorted(bad)))
    for platform in ('windows','macos'):
        if (ROOT/'frontend'/platform/'app.py').exists():errors.append('UI must remain shared, not duplicated: '+platform)
    return errors

if __name__=='__main__':
    errors=check()
    print('\n'.join(errors) if errors else 'PASS: shared UI, paired platform contracts, isolated backend')
    raise SystemExit(bool(errors))
