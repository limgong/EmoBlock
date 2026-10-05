"""macOS WAV audition with click-free pause, resume, and replay."""
import math
from pathlib import Path
import threading
import wave

import numpy as np


def _sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        raise RuntimeError('Mac 音频播放需要安装 requirements-macos.txt。') from exc
    return sounddevice


def playback_range(duration,start=0.,end=None):
    end=duration if end is None else end
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in (duration,start,end)) or not 0<=start<end<=duration+.002:
        raise ValueError('试听范围无效或超出音频长度。')
    a,b=round(start*1000),min(round(end*1000),round(duration*1000))
    if b<=a:raise ValueError('试听范围过短。')
    return a,b


def _pcm_samples(source,first,last):
    """Read the selected PCM frames as normalized float32 samples."""
    width=source.getsampwidth();channels=source.getnchannels()
    if width not in (1,2,3,4) or channels not in (1,2):
        raise ValueError('仅支持单声道或双声道 PCM WAV 试听。')
    source.setpos(first)
    raw=source.readframes(last-first)
    if width==3:
        octets=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.int32)
        value=octets[:,0] | (octets[:,1]<<8) | (octets[:,2]<<16)
        value=np.where(value&0x800000,value-0x1000000,value).astype(np.float32)/8388608
    else:
        dtype={1:np.uint8,2:'<i2',4:'<i4'}[width]
        value=np.frombuffer(raw,dtype=dtype).astype(np.float32)
        value=(value-128)/128 if width==1 else value/(1<<(8*width-1))
    return value.reshape(-1,channels)


class WavePlayer:
    def __init__(self):
        self.opened=False;self.stream=None;self.samples=None;self.paused=False;self.sd=None
        self.start=0.;self.end=0.;self.rate=0;self.frame=0;self.gain=0.;self.fade_frames=1
        self.finished=False;self.quiet=threading.Event()

    def play(self,path,start=0.,end=None):
        self.close();path=Path(path).resolve()
        if not path.is_file():raise ValueError('试听文件已移动或缺失。')
        with wave.open(str(path),'rb') as source:
            self.rate=source.getframerate();duration=source.getnframes()/self.rate
            a,b=playback_range(duration,start,end)
            first=round(a*self.rate/1000);last=min(source.getnframes(),round(b*self.rate/1000))
            self.samples=_pcm_samples(source,first,last)
            self.start=first/self.rate;self.end=last/self.rate
        if not len(self.samples):raise ValueError('试听范围过短。')
        self.frame=0;self.gain=0.;self.fade_frames=max(1,round(.012*self.rate))
        self.paused=False;self.finished=False;self.quiet.clear()
        try:
            self.sd=_sounddevice()
            self.stream=self.sd.OutputStream(samplerate=self.rate,channels=self.samples.shape[1],dtype='float32',
                                             latency='high',callback=self._output,finished_callback=self._finished)
            self.stream.start();self.opened=True
        except Exception:
            self.close();raise
        return duration

    def _output(self,outdata,frames,time_info,status):
        outdata.fill(0)
        samples=self.samples
        if samples is None:return
        remaining=len(samples)-self.frame
        count=min(frames,remaining) if not self.paused or self.gain>0 else 0
        if count:
            outdata[:count]=samples[self.frame:self.frame+count]
            step=(1 if not self.paused else -1)/self.fade_frames
            gains=np.clip(self.gain+step*np.arange(1,count+1,dtype=np.float32),0,1)
            # A segment can begin or end between nonzero samples.
            tail=np.minimum(1,(len(samples)-self.frame-np.arange(count,dtype=np.float32))/self.fade_frames)
            outdata[:count]*=(gains*tail)[:,None]
            self.gain=float(gains[-1]);self.frame+=count
        if self.paused and self.gain==0:self.quiet.set()
        if self.frame>=len(samples):raise self.sd.CallbackStop

    def _finished(self):
        self.finished=True;self.quiet.set()

    def status(self):
        if not self.opened:return 0.,'closed'
        if self.finished:return self.end,'stopped'
        return min(self.end,self.start+self.frame/self.rate),'paused' if self.paused else 'playing'

    def pause(self):
        if self.opened and not self.finished:self.paused=True

    def resume(self):
        if self.opened and not self.finished:self.paused=False;self.quiet.clear()

    def close(self):
        if self.stream:
            if self.opened and not self.finished:
                self.paused=True;self.quiet.wait(timeout=.1)
            self.stream.close();self.stream=None
        self.samples=None;self.opened=False;self.paused=False;self.finished=False;self.sd=None
        self.quiet.clear()
