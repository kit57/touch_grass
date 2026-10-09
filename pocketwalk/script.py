"""Writing the narration with a local open-weight model served by Ollama."""

import json
import os
import re
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("POCKETWALK_MODEL", "gemma3:4b")

SYSTEM = """You write narration for an audio walking tour. The listener hears it through earbuds \
while standing outside, with their phone in their pocket.

Rules:
- Write everything in LANGUAGE
- Write plain spoken prose only. No markdown, headings, lists, emojis, stage directions or quotation marks around the whole text.
- Tell the story of the place. History and people come first: who made it and when, why it is \
here, what happened on this spot, how it has changed, and one telling detail a passer-by would miss.
- Use only the facts you are given. Never invent dates, names, numbers or events. If the \
reference text is in another language, carry its facts over faithfully.
- Do not pad with remarks about the weather, the light, the leaves or the season. At most one \
short sentence may point the listener at something specific to look at.
- If you are given almost no facts, keep it short: say what kind of place this is and what to \
look for, and do not fill the gap with atmosphere.
- Do not give walking directions, and do not say hello or goodbye unless asked to.
- Warm and curious, like a friend who knows the place. Natural, flowing sentences of varied \
length that are easy to follow by ear. Do not write in clipped fragments."""

cpu_only = os.environ.get("POCKETWALK_CPU") == "1"


def chat(prompt, L, model=DEFAULT_MODEL, words=140):
    """`L` is the language block from lang.py that the answer should be written in."""
    global cpu_only
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM.replace("LANGUAGE", L["name"] + "." + L["address"])},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.3, "num_ctx": 4096, "num_predict": words * 4},
    }
    if cpu_only:
        body["options"]["num_gpu"] = 0
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return clean(json.load(r)["message"]["content"])
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if "CUDA" in detail and not cpu_only:
            # An old graphics driver can crash the GPU runner. Slower on the CPU, but it works.
            cpu_only = True
            return chat(prompt, L, model, words)
        raise RuntimeError(f"Ollama refused the request ({detail}). Try: ollama pull {model}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Ollama at {OLLAMA_URL}. Is it running?") from e


def clean(text):
    """Strip anything a text-to-speech voice would stumble over."""
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"\((?:pause|beat|music)[^)]*\)", "", text, flags=re.I)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Small models like to announce what they are about to write.
    if len(lines) > 1 and lines[0].endswith(":") and len(lines[0]) < 80:
        lines = lines[1:]
    return re.sub(r"\s+", " ", " ".join(lines)).strip().strip('"')


def intro(area, stops, minutes, L, model):
    names = ", ".join(s["name"] for s in stops)
    return chat(
        f"Write a welcome of about 60 words for a {minutes}-minute walk through the history of {area}. "
        f"There are {len(stops)} stops: {names}. Mention only one or two of them. "
        "Tell the listener to put their phone in their pocket and look up, "
        "and that each stop ends with directions to the next one.",
        L,
        model,
        words=80,
    )


def stop(place, k, n, extract, L, model):
    tag_facts = "\n".join(f"- {key.replace('_', ' ')}: {value}" for key, value in place["facts"].items())
    return chat(
        f"Stop {k} of {n}: {place['name']} (a {place['kind']}).\n\n"
        f"Facts from the map:\n{tag_facts or '- none'}\n\n"
        f"Reference text:\n{extract or 'none'}\n\n"
        "Write the narration for this stop in 130 to 170 words. The listener has just arrived and "
        "is looking at it. Spend most of it on the history and the people behind this place.",
        L,
        model,
        words=190,
    )


def outro(area, stops, L, model):
    return chat(
        f"Write a closing of about 45 words for a walk around {area} that visited "
        f"{', '.join(s['name'] for s in stops)}. The listener is back where they started. "
        "Say goodbye and nudge them to stay outside a little longer.",
        L,
        model,
        words=70,
    )
