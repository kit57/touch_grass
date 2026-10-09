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

ELEVENLABS_API = "https://api.elevenlabs.io/v1/"
# "George", one of the stock voices, unless .env names another.
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE", "JBFqnCBsd6RMkjVDRZzb")
# What can be tuned, with the range ElevenLabs accepts for each.
ELEVENLABS_SETTINGS = {"speed": (0.7, 1.2), "stability": (0.0, 1.0), "style": (0.0, 1.0)}
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_KBPS = 64


def make_speaker(engine="piper", voice_name=None, voices_dir="voices", settings=None):
    """Returns a function text -> (mp3_bytes, seconds). `settings` tunes the ElevenLabs voice."""
    if engine == "elevenlabs":
        return _elevenlabs(voice_name or ELEVENLABS_VOICE, settings or {})
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


def _elevenlabs_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("Put your ELEVENLABS_API_KEY in the .env file to use the ElevenLabs voice.")
    return key


def elevenlabs_voices():
    """The voices available to your ElevenLabs account, as a list of {id, name, about}."""
    req = urllib.request.Request(ELEVENLABS_API + "voices", headers={"xi-api-key": _elevenlabs_key()})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            voices = json.load(r)["voices"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs would not list voices ({e.code}). Check your API key.") from e
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach ElevenLabs.") from e
    out = []
    for v in voices:
        labels = v.get("labels") or {}
        about = ", ".join(labels[k] for k in ("gender", "accent", "descriptive", "description") if labels.get(k))
        out.append({"id": v["voice_id"], "name": v["name"], "about": about})
    return sorted(out, key=lambda v: v["name"].lower())


def _elevenlabs(voice_id, settings):
    key = _elevenlabs_key()
    body = {"model_id": ELEVENLABS_MODEL}
    # Only send what was asked for, clamped to the allowed range; the rest keeps the voice's own defaults.
    tuned = {
        name: max(low, min(high, float(settings[name])))
        for name, (low, high) in ELEVENLABS_SETTINGS.items()
        if settings.get(name) is not None
    }
    if tuned:
        body["voice_settings"] = tuned

    def speak(text):
        req = urllib.request.Request(
            f"{ELEVENLABS_API}text-to-speech/{voice_id}?output_format=mp3_44100_{ELEVENLABS_KBPS}",
            data=json.dumps({**body, "text": text}).encode(),
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
