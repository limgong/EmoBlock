"""Atomic artifact copy shared by desktop and pure data services."""
import os
import hashlib
from pathlib import Path
import shutil
import stat
import tempfile


def atomic_export(source,target,protected,expected_sha256=None):
    source=Path(source);target=Path(target).absolute()
    protected=tuple(Path(p) for p in protected)+(source,)
    def guard():
        resolved=target.resolve()
        for path in protected:
            if resolved==path.resolve() or (target.exists() and path.exists() and target.samefile(path)):
                raise ValueError('目标是生成源文件，请选择其他文件名或目录。')
        return resolved
    destination=guard();temporary=None
    try:
        with source.open('rb') as incoming:
            before=os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode):raise ValueError('生成源文件不可用，请找回文件或重新生成。')
            with tempfile.NamedTemporaryFile(mode='wb',prefix='.emoblocks-export-',suffix='.tmp',dir=destination.parent,delete=False) as outgoing:
                temporary=Path(outgoing.name)
                shutil.copyfileobj(incoming,outgoing)
                outgoing.flush();os.fsync(outgoing.fileno())
                if outgoing.tell()!=before.st_size:raise OSError('复制不完整，请重试。')
            after=source.stat()
            identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
            if identity(before)!=identity(after):raise OSError('导出期间源文件发生变化，请找回文件或重新生成后重试。')
        if guard()!=destination:raise OSError('目标位置在导出期间发生变化，请重新选择位置。')
        if expected_sha256 is not None:
            with temporary.open('rb') as copied:
                digest=hashlib.file_digest(copied,'sha256').hexdigest()
            if digest!=expected_sha256:
                raise OSError('导出源文件已改变，请重新准备所选版本后重试。')
        os.replace(temporary,destination)
        temporary=None
        return destination
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
