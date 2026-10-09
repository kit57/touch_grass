# Pocket Walk

A narrated walk around wherever you are, written and voiced on your own computer.

Tell it where you're starting and how long you have. It finds monuments, historic buildings,
parks and artworks nearby, plans a loop, writes the history of each stop as a short story, and
records the whole thing as audio, in English, Spanish, French, German or Italian. Then you put your earbuds in, your phone in your pocket, and go outside. One tap
starts the walk; after that the screen is done.

Built for the Hacktoberfest Open-Source AI Challenge, week 1: *Touch Grass*.

## How it works

| Step | What does it | Where it runs |
| --- | --- | --- |
| Find places and a walking route | OpenStreetMap (Nominatim, Overpass, OSRM) and Wikipedia | Public open-data servers |
| Write the narration | Gemma 3 4B, an open-weight model, through Ollama | Your computer |
| Speak it | Piper, an open text-to-speech model | Your computer |
| Play it | One self-contained HTML page with the audio inside | Your phone, no signal needed |

Walking directions are written by plain code from the route data, never by the model, so the
model cannot invent a turn. The model is told to use only the facts it is handed (map tags and
the place's Wikipedia article) and to lead with history and people: who made the place, when,
why, and what happened there. When it has few facts it is told to say less, not to fill the
gap with atmosphere.

Each stop is its own track. When a track ends, the player cues up the next one and waits.
You walk in silence, and press play on your earbuds when you arrive.

Everything the walk needs is open and runs locally. ElevenLabs is offered as an optional
cloud voice for people who want it; nothing depends on it.

## Run it

You need Python 3.10 or newer and [Ollama](https://ollama.com).

```
ollama pull gemma3:4b
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # on macOS/Linux: .venv/bin/pip
.venv\Scripts\python -m pocketwalk serve
```

Open http://localhost:8000, type a starting place, and press **Make my walk**. The first walk
downloads a 60 MB voice. A 30-minute walk takes about a minute to make on a GTX 1060.

On Windows, `start.ps1` does the last step for you and starts Ollama first:

```
powershell -ExecutionPolicy Bypass -File .\start.ps1        # add -Lan to reach it from your phone
```

Settings and keys live in a `.env` file, which git ignores. Copy `.env.example` to `.env` to
start one. Restart the server after changing `.env` or any Python file.

Or from the terminal:

```
.venv\Scripts\python -m pocketwalk walk "Jardin du Luxembourg, Paris" --minutes 45
```

Every walk lands in `walks/<date>-<place>/`:

- `walk.html`: the player, with audio, a route map and the script embedded
- `00-welcome.mp3`, `01-….mp3`, …: the same tracks for any music app
- `route.gpx`: the route for a maps app or watch
- `walk.json`: stops, route and script

## Preview a walk without walking

Open a walk and press **Preview it without walking** under the map. The tracks play back to
back while a dot follows them round the route: it waits at each stop while the story plays,
sets off when the directions begin, and reaches the next stop as that stop's track starts.
It is a way to check or demo a walk from a chair. The dot is driven by the audio, not by GPS;
the player never reads your location.

## Get it onto your phone

Run `python -m pocketwalk serve --lan` and open the address it prints on your phone while both
are on the same Wi-Fi. Open the walk and leave the tab open (or use the browser's download
button); the audio is inside the page, so it keeps working once you're out of range. You can
also just copy the MP3s over.

## Languages

Choose **Language of the guide** on the page, or pass `--lang en|es|fr|de|it`. The whole walk
follows: the model writes the stories in that language, the directions come from hand-written
templates in [pocketwalk/lang.py](pocketwalk/lang.py), place names use the map's name in that
language where it has one, and the Wikipedia article in that language is used when it exists.

Both voices follow too. Piper switches to a voice for that language (downloaded on first use,
about 60 MB each), and the ElevenLabs multilingual model speaks whatever language the script
is in. To add a language, copy one block in `lang.py`, translate it, and name a Piper voice.

## Make it yours

- **Another model:** `--model <anything in ollama list>`, or set `POCKETWALK_MODEL`.
- **Another voice:** `--voice en_GB-alan-medium` (any
  [Piper voice](https://huggingface.co/rhasspy/piper-voices)).
- **Another tone:** the whole personality of the guide is the `SYSTEM` prompt in
  [pocketwalk/script.py](pocketwalk/script.py).
- **Miles and feet:** `--units imperial`.

## Optional: an ElevenLabs voice

Piper is the default and needs nothing. If you'd like a more natural voice, or one that
pronounces names in other languages properly, Pocket Walk can record with
[ElevenLabs](https://elevenlabs.io) instead. It is a closed cloud service: the script is sent
to their servers and each walk uses credits (about 5,000 characters for 30 minutes).

1. Create an API key at elevenlabs.io with the **Text to Speech** and **Voices: Read**
   permissions.
2. Put it in `.env` as `ELEVENLABS_API_KEY=...` and restart the server.
3. On the page, set **Voice** to ElevenLabs. A panel opens where you can:
   - pick any voice on your account, and press **Listen** to hear its sample (free; it plays
     ElevenLabs' own preview clip)
   - set **Pace** (0.7 to 1.2), **Steadiness** (lower is more expressive) and **Drama**

   A slider you leave alone keeps that voice's own setting, and your voice choice is
   remembered.

From the terminal:

```
.venv\Scripts\python -m pocketwalk voices
.venv\Scripts\python -m pocketwalk walk "Your start" --voice-engine elevenlabs --voice <id> --voice-speed 1.1 --voice-stability 0.4 --voice-style 0.2
```

`ELEVENLABS_VOICE=<id>` in `.env` changes the default voice.

## Troubleshooting

- **"CUDA error" from Ollama:** your NVIDIA driver is older than Ollama's GPU build expects.
  Pocket Walk falls back to the CPU on its own (slower). To keep the GPU, update the driver, or
  on Windows run `.\start.ps1`, which starts Ollama on its Vulkan backend instead.
- **"OpenStreetMap lookup failed":** the public map servers are busy. Try again in a minute.
- **Few or no stops:** OpenStreetMap has little mapped near you. Try a longer walk.
- **A new option is missing or greyed out:** the server is still running old code. Stop it
  with Ctrl+C and start it again.
- **The ElevenLabs voice list is empty:** the key lacks the Voices: Read permission. Walks
  still work with the default voice.

## Honest limits

- Making a walk needs the internet once, to fetch map data, and those lookups send your start
  point to OpenStreetMap and Wikipedia servers. The model, the voice and the finished walk stay
  on your machine, and the walk itself needs no connection.
- A 4B model sometimes gets a detail from its source text wrong, such as a date or a name.
  Treat the stories as a friendly guide, not a reference.
- A Piper voice reads everything in its own language, so foreign place names can come out
  oddly (a Spanish street read by the English voice). Pick the walk's language to match the
  place, or use the ElevenLabs option.
- The player's own buttons and hints are in English whatever the walk's language.
- The player doesn't know where you are. You tell it you've arrived by pressing play.
- Directions describe the first few turns of each leg. On a twisty leg, the route sketch in
  the player or the GPX file has the rest.

## Credits

Map data © OpenStreetMap contributors (ODbL). Place summaries from Wikipedia (CC BY-SA).
Routing by OSRM on the FOSSGIS server. Gemma by Google, Piper by the Open Home Foundation,
Ollama, and LAME via `lameenc`. Optional cloud voice by ElevenLabs.
