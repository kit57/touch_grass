"""The whole pipeline: a start point and a duration in, a folder of audio and one offline page out."""

import base64
import datetime
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from . import places, script, voice
from .lang import LANGS

TEMPLATE = Path(__file__).with_name("player.html")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "walk"


def build_walk(start, minutes=30, units="metric", model=script.DEFAULT_MODEL,
               voice_name=None, out_root="walks", progress=print, engine="piper", voice_settings=None,
               lang="en"):
    """`start` is a dict with lat, lon and optionally label. Returns a summary of what was written."""
    L = LANGS[lang]
    if engine == "piper" and not voice_name:
        voice_name = L["piper"]
    # Fail on a missing voice or key now, not after the script has been written.
    speak = voice.make_speaker(engine, voice_name, settings=voice_settings)

    n = max(2, min(8, round(minutes / 8)))
    budget = max(300, (minutes - n * 1.5 - 1) * places.WALK_SPEED)
    radius = max(300, min(2000, budget / 2.5))

    progress("Looking for places nearby")
    found = places.find_places(start, radius, lang)
    stops = places.plan_stops(start, found, n, budget)
    if not stops:
        raise RuntimeError(
            "OpenStreetMap has no named parks, landmarks or artworks close enough to that spot. "
            "Try a longer walk or a different start."
        )

    progress("Planning the route")
    home = {**start, "name": L["home"]}
    while True:
        points = [home] + stops + [home]
        legs, coords = places.route(points)
        total = sum(leg["distance"] for leg in legs)
        if total <= budget * 1.25 or len(stops) == 1:
            break
        # Real paths turned out longer than the estimate: drop the stop that costs the most
        # extra walking for how interesting it is.
        def cost(i):
            detour = legs[i]["distance"] + legs[i + 1]["distance"] - places.dist(points[i], points[i + 2])
            return detour / stops[i]["score"]
        stops.pop(max(range(len(stops)), key=cost))

    area = start.get("label") or places.reverse_geocode(start["lat"], start["lon"]) or L["area"]
    directions = [places.describe_leg(leg, a, b, units, L) for leg, a, b in zip(legs, points, points[1:])]

    # Each track is the story followed by the way onward. `leave` is how far through the text
    # the story ends, which the player's preview uses to time the dot setting off.
    def track(title, story, onward=""):
        return {"title": title, "text": story + onward, "leave": round(len(story) / len(story + onward), 3)}

    progress(f"Writing the welcome with {model}")
    if legs[0]["distance"] < 40:
        onward = L["first_here"]
    else:
        onward = L["first_way"] + directions[0] + L["press"]
    tracks = [track(L["welcome"], script.intro(area, stops, minutes, L, model), onward)]
    for k, place in enumerate(stops, 1):
        progress(f"Writing stop {k} of {len(stops)}: {place['name']}")
        place["facts"] = places.facts(place["tags"])
        story = L["stop"].format(k=k, name=place["name"])
        story += script.stop(place, k, len(stops), places.wikipedia_extract(place["tags"], lang), L, model)
        if k < len(stops):
            onward = L["next_way"].format(k=k + 1) + directions[k] + L["press"]
        elif legs[k]["distance"] < 40:
            onward = L["back_here"]
        else:
            onward = L["back_way"] + directions[k] + L["back_press"]
        tracks.append(track(place["name"], story, onward))
    progress("Writing the goodbye")
    tracks.append(track(L["goodbye"], script.outro(area, stops, L, model)))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(out_root) / f"{stamp}-{slug(area)}-{minutes}min"
    out.mkdir(parents=True, exist_ok=True)

    audio = []
    for i, track in enumerate(tracks):
        progress(f"Recording track {i + 1} of {len(tracks)}")
        mp3, seconds = speak(track["text"])
        track["file"] = f"{i:02d}-{slug(track['title'])}.mp3"
        track["seconds"] = round(seconds)
        (out / track["file"]).write_bytes(mp3)
        audio.append(base64.b64encode(mp3).decode())

    walk = {
        "title": L["title"].format(area=area, minutes=minutes),
        "lang": lang,
        "area": area,
        "minutes": minutes,
        "distance": places.fmt_distance(total, units, L),
        "model": model,
        "voice": f"{engine}: {voice_name or 'default'}",
        "start": {"lat": start["lat"], "lon": start["lon"]},
        "stops": [{"name": s["name"], "kind": s["kind"], "lat": s["lat"], "lon": s["lon"]} for s in stops],
        "route": [[round(lon, 5), round(lat, 5)] for lon, lat in coords],
        "tracks": tracks,
    }
    (out / "walk.json").write_text(json.dumps(walk, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "route.gpx").write_text(gpx(walk), encoding="utf-8")

    # One self-contained page with the audio embedded, so it still plays with no signal.
    embedded = {**walk, "tracks": [{**t, "audio": a} for t, a in zip(tracks, audio)]}
    data = json.dumps(embedded, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*WALK_DATA*/null", data)
    (out / "walk.html").write_text(html, encoding="utf-8")

    progress("Done")
    return {"dir": str(out), "id": out.name, "title": walk["title"], "distance": walk["distance"],
            "stops": [s["name"] for s in stops], "audio_minutes": round(sum(t["seconds"] for t in tracks) / 60, 1)}


def gpx(walk):
    wpts = "".join(
        f'<wpt lat="{s["lat"]}" lon="{s["lon"]}"><name>{escape(s["name"])}</name></wpt>' for s in walk["stops"]
    )
    trk = "".join(f'<trkpt lat="{lat}" lon="{lon}"/>' for lon, lat in walk["route"])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="pocket-walk-narrator" xmlns="http://www.topografix.com/GPX/1/1">'
        f"{wpts}<trk><name>{escape(walk['title'])}</name><trkseg>{trk}</trkseg></trk></gpx>"
    )
