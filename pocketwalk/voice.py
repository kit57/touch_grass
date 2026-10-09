"""Turning the script into MP3s with Piper, an open text-to-speech model that runs on the CPU."""

import subprocess
import sys
from pathlib import Path

import lameenc
from piper import PiperVoice

DEFAULT_VOICE = "en_US-lessac-medium"
SENTENCE_GAP = 0.35  # seconds of silence between sentences


def load_voice(name=DEFAULT_VOICE, voices_dir="voices"):
    path = Path(voices_dir) / f"{name}.onnx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", name, "--data-dir", str(path.parent)], check=True
        )
    return PiperVoice.load(path)


def speak(voice, text):
    """Returns (mp3_bytes, seconds)."""
    rate = voice.config.sample_rate
    gap = b"\x00\x00" * int(rate * SENTENCE_GAP)
    pcm = gap.join(chunk.audio_int16_bytes for chunk in voice.synthesize(text))

    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(rate)
    enc.set_channels(1)
    enc.set_quality(2)
    enc.silence()
    mp3 = bytes(enc.encode(pcm)) + bytes(enc.flush())
    return mp3, len(pcm) / 2 / rate
