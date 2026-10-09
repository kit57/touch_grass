"""Turning the script into MP3s.

The default engine is Piper, an open text-to-speech model that runs on the CPU. ElevenLabs is
an optional cloud engine for when you want a more natural or multilingual voice.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENGINES = ["piper", "elevenlabs"]
DEFAULT_VOICE = "en_US-lessac-medium"
SENTENCE_GAP = 0.35  # seconds of silence between sentences

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/"
ELEVENLABS_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George", one of the stock voices
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_KBPS = 64


def make_speaker(engine="piper", voice_name=None, voices_dir="voices"):
    """Returns a function text -> (mp3_bytes, seconds)."""
    if engine == "elevenlabs":
        return _elevenlabs(voice_name or ELEVENLABS_VOICE)
    return _piper(voice_name or DEFAULT_VOICE, voices_dir)


def _piper(name, voices_dir):
    import lameenc
    from piper import PiperVoice

    path = Path(voices_dir) / f"{name}.onnx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", name, "--data-dir", str(path.parent)], check=True
        )
    voice = PiperVoice.load(path)
    rate = voice.config.sample_rate
    gap = b"\x00\x00" * int(rate * SENTENCE_GAP)

    def speak(text):
        pcm = gap.join(chunk.audio_int16_bytes for chunk in voice.synthesize(text))
        enc = lameenc.Encoder()
        enc.set_bit_rate(64)
        enc.set_in_sample_rate(rate)
        enc.set_channels(1)
        enc.set_quality(2)
        enc.silence()
        mp3 = bytes(enc.encode(pcm)) + bytes(enc.flush())
        return mp3, len(pcm) / 2 / rate

    return speak


def _elevenlabs(voice_id):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("Set the ELEVENLABS_API_KEY environment variable to use the ElevenLabs voice.")

    def speak(text):
        req = urllib.request.Request(
            f"{ELEVENLABS_URL}{voice_id}?output_format=mp3_44100_{ELEVENLABS_KBPS}",
            data=json.dumps({"text": text, "model_id": ELEVENLABS_MODEL}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                mp3 = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"ElevenLabs refused the request ({e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError("Could not reach ElevenLabs. Use the Piper voice to stay offline.") from e
        # Constant bitrate, so the length follows from the size.
        return mp3, len(mp3) * 8 / (ELEVENLABS_KBPS * 1000)

    return speak
