"""The whole pipeline: a start point and a duration in, a folder of audio and one offline page out."""

import base64
import datetime
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from . import places, script, voice

PRESS_PLAY = " Press play when you get there."
TEMPLATE = Path(__file__).with_name("player.html")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "walk"


def build_walk(start, minutes=30, units="metric", model=script.DEFAULT_MODEL,
               voice_name=voice.DEFAULT_VOICE, out_root="walks", progress=print):
    """`start` is a dict with lat, lon and optionally label. Returns a summary of what was written."""
    n = max(2, min(8, round(minutes / 8)))
    budget = max(300, (minutes - n * 1.5 - 1) * places.WALK_SPEED)
    radius = max(300, min(2000, budget / 2.5))

    progress("Looking for places nearby")
    found = places.find_places(start, radius)
    stops = places.plan_stops(start, found, n, budget)
    if not stops:
        raise RuntimeError(
            "OpenStreetMap has no named parks, landmarks or artworks close enough to that spot. "
            "Try a longer walk or a different start."
        )

    progress("Planning the route")
    home = {**start, "name": "your starting point"}
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

    area = start.get("label") or places.reverse_geocode(start["lat"], start["lon"])
    season_name = script.season(start["lat"], datetime.date.today().month)
    directions = [places.describe_leg(leg, a, b, units) for leg, a, b in zip(legs, points, points[1:])]

    progress(f"Writing the welcome with {model}")
    if legs[0]["distance"] < 40:
        first = " Your first stop is right where you're standing. Press play when you're ready."
    else:
        first = " Here's the way to your first stop. " + directions[0] + PRESS_PLAY
    tracks = [{"title": "Welcome", "text": script.intro(area, stops, minutes, season_name, model) + first}]
    for k, place in enumerate(stops, 1):
        progress(f"Writing stop {k} of {len(stops)}: {place['name']}")
        place["facts"] = places.facts(place["tags"])
        text = f"Stop {k}. {place['name']}. "
        text += script.stop(place, k, len(stops), season_name, places.wikipedia_extract(place["tags"]), model)
        if k < len(stops):
            text += f" When you're ready, here's the way to stop {k + 1}. " + directions[k] + PRESS_PLAY
        elif legs[k]["distance"] < 40:
            text += " That brings you back to where you started. Press play for a short goodbye."
        else:
            text += (" When you're ready, here's the way back. " + directions[k]
                     + " Press play when you're back for a short goodbye.")
        tracks.append({"title": place["name"], "text": text})
    progress("Writing the goodbye")
    tracks.append({"title": "Welcome back", "text": script.outro(area, stops, model)})

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(out_root) / f"{stamp}-{slug(area)}-{minutes}min"
    out.mkdir(parents=True, exist_ok=True)

    speaker = voice.load_voice(voice_name)
    audio = []
    for i, track in enumerate(tracks):
        progress(f"Recording track {i + 1} of {len(tracks)}")
        mp3, seconds = voice.speak(speaker, track["text"])
        track["file"] = f"{i:02d}-{slug(track['title'])}.mp3"
        track["seconds"] = round(seconds)
        (out / track["file"]).write_bytes(mp3)
        audio.append(base64.b64encode(mp3).decode())

    walk = {
        "title": f"{area}: a {minutes}-minute walk",
        "area": area,
        "minutes": minutes,
        "distance": places.fmt_distance(total, units),
        "model": model,
        "voice": voice_name,
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
