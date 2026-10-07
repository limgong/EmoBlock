"""Ephemeral playback authorization, never part of a musical project."""
import copy


class PlayIntent:
    def __init__(self):
        self.serial=0
        self.current=None

    def invalidate(self):
        self.serial+=1
        self.current=None

    def begin(self, target, mode, input_key, asset_key):
        self.invalidate()
        self.current=dict(serial=self.serial,target=tuple(target),mode=mode,input_key=input_key,
                          asset_key=asset_key,token=None)
        return self.serial

    def bind(self, token, input_key):
        if self.current and self.current['input_key']==input_key:
            self.current['token']=copy.deepcopy(token)

    def accepts(self, token, target, mode, input_key, asset_key):
        value=self.current
        return bool(value and value['token']==token and value['target']==tuple(target)
                    and value['mode']==mode and value['input_key']==input_key and value['asset_key']==asset_key)

    def consume(self):
        self.invalidate()
