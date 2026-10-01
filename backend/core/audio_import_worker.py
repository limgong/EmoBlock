"""Worker executed inside the dedicated Basic Pitch virtual environment."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pretty_midi
from basic_pitch.inference import predict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("midi")
    parser.add_argument("bpm", type=float)
    args = parser.parse_args()

    _, prediction, note_events = predict(args.audio)
    note_count = sum(len(instrument.notes) for instrument in prediction.instruments)
    if note_count == 0:
        raise RuntimeError("音频中没有识别到可导出的音符。")

    # Basic Pitch gives note positions in seconds. Rebuilding the container with
    # the user-supplied tempo preserves those times while giving EmoBlocks a
    # useful musical beat grid for its 4/4 bar selection.
    midi = pretty_midi.PrettyMIDI(initial_tempo=args.bpm)
    midi.instruments = copy.deepcopy(prediction.instruments)
    destination = Path(args.midi)
    destination.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(destination))
    print(json.dumps({
        "note_count": note_count,
        "duration_seconds": round(midi.get_end_time(), 3),
        "detected_events": len(note_events),
    }))


if __name__ == "__main__":
    main()
