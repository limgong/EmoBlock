"""macOS WAV audition via afplay, with segment playback and pause/resume."""
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import wave
def playback_range(duration,start=0.,end=None):
    end=duration if end is None else end
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in (duration,start,end)) or not 0<=start<end<=duration+.002:
        raise ValueError('试听范围无效或超出音频长度。')
    a,b=round(start*1000),min(round(end*1000),round(duration*1000))
    if b<=a:raise ValueError('试听范围过短。')
    return a,b
class WavePlayer:
    def __init__(self):
        self.opened=False;self.process=None;self.temp=None;self.paused=False;self.offset=0.;self.started=0.;self.start=0.;self.end=0.
    def play(self,path,start=0.,end=None):
        self.close();path=Path(path).resolve()
        if not path.is_file():raise ValueError('试听文件已移动或缺失。')
        with wave.open(str(path),'rb') as source:
            duration=source.getnframes()/source.getframerate();a,b=playback_range(duration,start,end)
            self.start=a/1000;self.end=b/1000;source.setpos(round(self.start*source.getframerate()))
            handle=tempfile.NamedTemporaryFile(prefix='emoblocks-',suffix='.wav',delete=False);handle.close();self.temp=Path(handle.name)
            try:
                with wave.open(str(self.temp),'wb') as target:
                    target.setparams(source.getparams());remaining=round((self.end-self.start)*source.getframerate())
                    while remaining>0:
                        count=min(65536,remaining);target.writeframes(source.readframes(count));remaining-=count
                self.process=subprocess.Popen(['/usr/bin/afplay',str(self.temp)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except Exception:
                self.close();raise
        self.offset=self.start;self.started=time.monotonic();self.opened=True;return duration
    def status(self):
        if not self.opened:return 0.,'closed'
        code=self.process.poll()
        if code is not None:
            if code:raise ValueError('macOS 音频播放失败（afplay 退出码 %s）。'%code)
            return self.end,'stopped'
        position=self.offset if self.paused else self.offset+time.monotonic()-self.started
        return min(self.end,position),'paused' if self.paused else 'playing'
    def pause(self):
        if self.opened and not self.paused and self.process.poll() is None:
            self.offset=self.status()[0];os.kill(self.process.pid,signal.SIGSTOP);self.paused=True
    def resume(self):
        if self.opened and self.paused and self.process.poll() is None:
            os.kill(self.process.pid,signal.SIGCONT);self.started=time.monotonic();self.paused=False
    def close(self):
        if self.process and self.process.poll() is None:
            if self.paused:os.kill(self.process.pid,signal.SIGCONT)
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        self.process=None;self.opened=False;self.paused=False
        if self.temp:self.temp.unlink(missing_ok=True);self.temp=None
