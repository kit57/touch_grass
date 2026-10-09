# Pocket Walk

A narrated walk around wherever you are, written and voiced on your own computer.

Tell it where you're starting and how long you have. It finds parks, monuments, old trees and
artworks nearby, plans a loop, writes a short story for each stop, and records the whole thing
as audio. Then you put your earbuds in, your phone in your pocket, and go outside. One tap
starts the walk; after that the screen is done.

Built for the Hacktoberfest Open-Source AI Challenge, week 1: *Touch Grass*.

## How it works

| Step | What does it | Where it runs |
| --- | --- | --- |
| Find places and a walking route | OpenStreetMap (Nominatim, Overpass, OSRM) and Wikipedia | Public open-data servers |
| Write the narration | Gemma 3 4B, an open-weight model, through Ollama | Your computer |
| Speak it | Piper, an open text-to-speech model (ElevenLabs optional) | Your computer |
| Play it | One self-contained HTML page with the audio inside | Your phone, no signal needed |

Walking directions are written by plain code from the route data, never by the model, so the
model cannot invent a turn. The model is told to use only the facts it is handed (map tags and
the Wikipedia intro) and to describe what you can see when there are few.

Each stop is its own track. When a track ends, the player cues up the next one and waits.
You walk in silence, and press play on your earbuds when you arrive.

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

Or from the terminal:

```
.venv\Scripts\python -m pocketwalk walk "Jardin du Luxembourg, Paris" --minutes 45
```

Every walk lands in `walks/<date>-<place>/`:

- `walk.html`: the player, with audio, a route sketch and the script embedded
- `00-welcome.mp3`, `01-….mp3`, …: the same tracks for any music app
- `route.gpx`: the route for a maps app or watch
- `walk.json`: stops, route and script

## Get it onto your phone

Run `python -m pocketwalk serve --lan` and open the address it prints on your phone while both
are on the same Wi-Fi. Open the walk and leave the tab open (or use the browser's download
button); the audio is inside the page, so it keeps working once you're out of range. You can
also just copy the MP3s over.

## Make it yours

- **Another model:** `--model <anything in ollama list>`, or set `POCKETWALK_MODEL`.
- **Another voice or language:** `--voice de_DE-thorsten-medium` (any
  [Piper voice](https://huggingface.co/rhasspy/piper-voices)).
- **A cloud voice:** `--voice-engine elevenlabs` (or the Voice menu on the page) records with
  [ElevenLabs](https://elevenlabs.io) instead. Set `ELEVENLABS_API_KEY` first. It sounds more
  natural and handles names in other languages, but it sends the script to their servers and
  uses credits, so Piper stays the default.
- **Another tone:** the whole personality of the guide is the `SYSTEM` prompt in
  [pocketwalk/script.py](pocketwalk/script.py).
- **Miles and feet:** `--units imperial`.

## Troubleshooting

- **"CUDA error" from Ollama:** your NVIDIA driver is older than Ollama's GPU build expects.
  Pocket Walk falls back to the CPU on its own (slower). To keep the GPU, update the driver, or
  on Windows run `.\start.ps1`, which starts Ollama on its Vulkan backend instead.
- **"OpenStreetMap lookup failed":** the public map servers are busy. Try again in a minute.
- **Few or no stops:** OpenStreetMap has little mapped near you. Try a longer walk.

## Honest limits

- Making a walk needs the internet once, to fetch map data, and those lookups send your start
  point to OpenStreetMap and Wikipedia servers. The model, the voice and the finished walk stay
  on your machine, and the walk itself needs no connection.
- A 4B model sometimes blurs a detail from its source text. Treat the stories as a friendly
  guide, not a reference.
- The default voice is English and will mangle names in other languages; pick a matching voice.
- Directions describe the first few turns of each leg. On a twisty leg, the route sketch in
  the player or the GPX file has the rest.

## Credits

Map data © OpenStreetMap contributors (ODbL). Place summaries from Wikipedia (CC BY-SA).
Routing by OSRM on the FOSSGIS server. Gemma by Google, Piper by the Open Home Foundation,
Ollama, and LAME via `lameenc`.
