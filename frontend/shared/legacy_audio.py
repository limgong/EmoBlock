"""Legacy audition calls backed by the platform WavePlayer."""
from audio_player import WavePlayer
SND_FILENAME=1
SND_ASYNC=2
_player=None
def PlaySound(path,flags=0):
    global _player
    if _player:_player.close()
    if path is not None:
        _player=WavePlayer();_player.play(path)
