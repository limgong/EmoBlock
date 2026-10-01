"""Windowless Windows WAV playback with device-reported position."""
import ctypes
from pathlib import Path
import uuid
import math


def playback_range(duration,start=0.,end=None):
    end=duration if end is None else end
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in (duration,start,end)) or not 0<=start<end<=duration+.002:
        raise ValueError('试听范围无效或超出音频长度。')
    a,b=round(start*1000),min(round(end*1000),round(duration*1000))
    if b<=a:raise ValueError('试听范围过短。')
    return a,b


class WavePlayer:
    def __init__(self):
        self.alias='emo_'+uuid.uuid4().hex
        self.opened=False
        self.api=ctypes.windll.winmm

    def command(self,text):
        output=ctypes.create_unicode_buffer(512)
        error=self.api.mciSendStringW(text,output,512,None)
        if error:
            detail=ctypes.create_unicode_buffer(512)
            self.api.mciGetErrorStringW(error,detail,512)
            raise ValueError('音频播放失败：'+detail.value)
        return output.value

    def play(self,path,start=0.,end=None):
        self.close()
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('试听文件已移动或缺失。')
        if '"' in str(path):raise ValueError('音频路径包含无效字符。')
        self.command(f'open "{path}" type waveaudio alias {self.alias}')
        self.opened=True
        try:
            self.command(f'set {self.alias} time format milliseconds')
            duration=int(self.command(f'status {self.alias} length'))/1000
            a,b=playback_range(duration,start,end)
            self.command(f'play {self.alias} from {a} to {b}')
            return duration
        except Exception:
            self.close();raise

    def status(self):
        if not self.opened:return 0.,'closed'
        return int(self.command(f'status {self.alias} position'))/1000,self.command(f'status {self.alias} mode')

    def pause(self):
        if self.opened:self.command(f'pause {self.alias}')

    def resume(self):
        if self.opened:self.command(f'resume {self.alias}')

    def close(self):
        if self.opened:
            try:self.command(f'close {self.alias}')
            finally:self.opened=False
