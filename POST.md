---
title: "Pocket Walk: a history guide for your own street, made on your laptop"
published: false
tags: hf26challenge, devchallenge, opensource, ai
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05)*

## What I Built

Most of us have walked past the same statue a hundred times without knowing who it is. We know more about cities we visited once on holiday, where we paid for a tour, than about the street we live on.

**Pocket Walk** fixes that with a walk. You tell it where you are and how long you have. It finds the monuments, old buildings, parks and artworks around you, plans a loop on foot, writes the history of each stop as a short story, and records the whole thing as audio. Then you put your earbuds in, put your phone in your pocket, and go.

The screen is the shortest part by design:

- **One tap starts the walk.** After that you never need to look at the phone.
- **Each stop is its own track.** The guide tells you the story of where you're standing, then gives you directions to the next stop, then goes quiet.
- **The walk between stops is yours.** No audio, no notifications. When you arrive, you press play on your earbuds and the next story begins.

A 30-minute walk is around a kilometre and a half with three stops. You come home having moved your body and knowing who that statue is.

It's for two kinds of people: the ones who want a reason to go for a walk around their own neighbourhood, and travellers who would rather look at a city than at a map of it. It speaks English, Spanish, French, German and Italian, so the same tool works at home and away.

<!-- TODO (you): one or two sentences about your own walk. Where did you go, which stop surprised you, what went wrong? The challenge gives bonus points for this, and it's the part only you can write. -->

## Demo

{% youtube r1ChWMBtnxs %}

The player also has a "Preview it without walking" button, which plays the walk back to back while a dot follows the audio around the route. It's there for checking a walk before you leave (and for demo videos). On a real walk the dot isn't needed, and the player never reads your location.

## Code

{% github kit57/touch_grass %}

It's about 1,000 lines of Python with two dependencies (Piper and an MP3 encoder) and two HTML pages with no framework. The README covers setup, every option, and an "Honest limits" section.

## How I Built It

Three open pieces do the work, and each one has a single job.

| Job | What does it | Where it runs |
| --- | --- | --- |
| Find places and a route | OpenStreetMap data (Nominatim, Overpass, OSRM) and Wikipedia | Public open-data servers |
| Write the stories | **Gemma 3 4B**, an open-weight model, through **Ollama** | My laptop |
| Speak them | **Piper**, an open text-to-speech model | My laptop |
| Play them | One self-contained HTML page with the audio inside | The phone, no signal needed |

**The model only does what a model is good at.** Gemma gets the map's tags for a place and the start of its Wikipedia article, and is told to tell the story from those facts and nothing else. It never writes directions. "Turn left onto Calle Mayor for about 360 metres" comes from plain code reading the route data, so the model cannot invent a turn and send someone the wrong way. For the same reason, the directions in each language are hand-written templates, not translations by the model.

**The walk is a file, not a service.** The output is a folder: numbered MP3s, a GPX route, and one HTML page with the audio embedded in it. Open that page on your phone at home and it keeps working with no signal, because there is nothing left to download.

**It runs on old hardware.** My machine has a GTX 1060 from 2016. Gemma 3 4B fits in its 6 GB and writes at about 37 tokens per second, so a complete 30-minute walk takes roughly a minute to make.

Three things went wrong along the way, and they shaped the result:

1. **The GPU crashed on the first try.** Ollama's CUDA build rejected my NVIDIA driver. Because the stack is open, there was another door: Ollama also ships a Vulkan backend, and the same card runs the model fully on the GPU through it. The app also falls back to the CPU by itself if the GPU fails.
2. **The public map servers are busy.** A lookup failed during testing, so the app now retries across three mirrors.
3. **A small model gets facts wrong sometimes.** In a Madrid test walk, Gemma said a church's history began in the year 1002 where the source almost certainly says 1202. Feeding it more of the article and lowering its randomness helps, but I'd rather say it plainly: treat the stories as a friendly guide, not a reference.

I built it with Claude Code as a pair programmer

## Why Does Open Innovation Matter?

Here are the challenge's questions, answered honestly.

**Does it run on a laptop with no internet?**
Partly, and the split matters. The model and the voice need no internet at all. Making a walk needs the internet once, to fetch map data and Wikipedia text. The finished walk needs nothing: it plays in the park, on the trail, or abroad with roaming switched off. So the part of the experience that happens outside is fully offline.

**Does it keep your data off a server you don't control?**
Mostly. There is no account, no API key, and nothing is uploaded. Your walks live in a folder on your disk. The one thing that leaves your machine is the start point, which is sent to OpenStreetMap and Wikipedia servers to look up what's nearby. That matters here, because a walking app's data is a list of where you live and where you go. The stories about it, and the audio, are made at home.

**Can you swap models or change how it behaves?**
Yes, and this was the most useful part while building.

- **Models:** `--model` takes anything you've pulled in Ollama.
- **Behaviour:** the guide's whole personality is one prompt in one file. The first version talked mostly about leaves and light. Changing it to lead with history and people was a paragraph of text, with no vendor to ask.
- **Languages:** adding Spanish, French, German and Italian meant translating one block of phrases per language and naming a free Piper voice for each.

**Does it cost nothing to run?**
Yes. Once the model and voice are downloaded, every walk is free, however many you make. That changed how I worked: I could regenerate a whole walk after every prompt change, in different cities and languages, without thinking about a bill.

**Where did open work better than closed?**
I can compare directly, because the project also has an optional closed voice. You can switch the narration to ElevenLabs if you want a more natural sound.

- **Setup:** Piper worked immediately. The ElevenLabs key needed an account, then failed until I enabled the right permissions on it.
- **Cost:** a 30-minute walk is about 5,000 characters of script. With Piper that's free. With ElevenLabs it's credits, and even previewing a tuned voice spends some.
- **Privacy:** with ElevenLabs the script goes to their servers.
- **Quality:** ElevenLabs does sound better, and I've kept it as an option for people who want that.

So the closed voice is a nice extra, and the open one is the reason the project can exist as "free, private, and yours". If ElevenLabs disappeared tomorrow, nothing would break. If Gemma or Piper were closed APIs, there would be no project, only a subscription.

## Prize Categories

- **Best Use of Gemma:** Gemma 3 4B writes every story, running locally through Ollama on a ten-year-old consumer GPU.
- **Best Use of ElevenLabs:** an optional narration voice, with a voice picker, samples you can listen to, and pace, steadiness and drama controls.

A confession about that second one: I had so much fun turning the Drama slider up that I ran out of ElevenLabs credits before the final take of the demo video. The open-source voice, which has never once asked me for credits, stepped in without complaint. So if you'd like to hear the ElevenLabs voices at their best, put your own API key in `.env` and try them. Go easy on the Drama slider.
