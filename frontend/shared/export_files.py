"""Copy one generated artifact without risking the source or an existing export."""
import os
from pathlib import Path
import shutil
import stat
import tempfile

FORMATS={
    'wav':('WAV','preview.wav','用于播放、分享的成品音频。'),
    'mid':('MIDI','composition.mid','用于继续编辑的音符数据；音色取决于打开它的软件。'),
    'mmp':('MMP','composition.mmp','用于 LMMS 中继续编辑；可能依赖原有音色、插件和采样路径，并非自包含工程。'),
}


from export_safe import atomic_export
