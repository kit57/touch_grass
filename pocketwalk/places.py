"""Finding things worth walking to: geocoding, OpenStreetMap places, Wikipedia facts, foot routing."""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "pocket-walk-narrator/0.1 (open-source hackathon project)"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OSRM_FOOT_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"

WALK_SPEED = 75  # metres per minute, an unhurried pace
DETOUR = 1.3  # streets are longer than straight lines

# Tags that are worth reading out to the model as facts about a place.
FACT_TAGS = [
    "description", "inscription", "start_date", "artist_name", "architect", "artwork_type",
    "memorial", "subject", "species", "genus", "leaf_type", "denomination", "religion",
    "heritage", "material", "height", "ele", "operator", "old_name", "alt_name",
]
KIND_KEYS = ["tourism", "historic", "leisure", "natural", "amenity", "man_made"]
OUTDOORSY = {"park", "garden", "nature_reserve", "viewpoint", "tree", "spring", "water", "peak", "wood", "beach"}


def get_json(url, params=None, data=None, timeout=60):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def dist(a, b):
    """Haversine distance in metres between two dicts with lat/lon."""
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    dla, dlo = la2 - la1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def bearing(a, b):
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlo = math.radians(b["lon"] - a["lon"])
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return math.degrees(math.atan2(y, x)) % 360


def compass(deg):
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[round(deg / 45) % 8]


def geocode(query):
    hits = get_json(
        "https://nominatim.openstreetmap.org/search",
        {"q": query, "format": "jsonv2", "limit": 1},
    )
    if not hits:
        raise ValueError(f"Could not find a place called {query!r}")
    h = hits[0]
    return {"lat": float(h["lat"]), "lon": float(h["lon"]), "label": h["display_name"].split(",")[0]}


def reverse_geocode(lat, lon):
    try:
        r = get_json(
            "https://nominatim.openstreetmap.org/reverse",
            {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 16},
        )
        a = r.get("address", {})
        for key in ("neighbourhood", "suburb", "quarter", "village", "town", "city"):
            if a.get(key):
                return a[key]
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass
    return "your neighbourhood"


def _kind(tags):
    for key in KIND_KEYS:
        v = tags.get(key)
        if v:
            return "historic site" if v == "yes" else v.replace("_", " ")
    return "place"


def _score(tags):
    s = 1
    s += 4 if "wikipedia" in tags else 0
    s += 2 if "wikidata" in tags else 0
    s += sum(1 for k in FACT_TAGS if k in tags)
    s += 2 if _kind(tags).replace(" ", "_") in OUTDOORSY else 0
    return s


def find_places(start, radius):
    """Named points of interest within `radius` metres, best first."""
    around = f"(around:{int(radius)},{start['lat']},{start['lon']})"
    query = f"""[out:json][timeout:40];
(
  nwr{around}[tourism~"^(artwork|attraction|viewpoint|museum|gallery)$"][name];
  nwr{around}[historic][name];
  nwr{around}[leisure~"^(park|garden|nature_reserve)$"][name];
  nwr{around}[natural~"^(tree|spring|water|peak|wood|beach)$"][name];
  nwr{around}[amenity~"^(fountain|place_of_worship|library|theatre)$"][name];
  nwr{around}[man_made~"^(bridge|lighthouse|tower|windmill)$"][name];
);
out center tags 800;"""
    last_error = None
    # The public servers are shared and often busy, so go round them twice before giving up.
    for attempt, url in enumerate(OVERPASS_URLS * 2):
        try:
            elements = get_json(url, data={"data": query}, timeout=70)["elements"]
            break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_error = e
            time.sleep(2 if attempt else 0)
    else:
        raise RuntimeError(f"OpenStreetMap lookup failed: {last_error}")

    places, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        pos = el if "lat" in el else el.get("center")
        name = tags.get("name:en") or tags.get("name")
        if not pos or not name or name.lower() in seen:
            continue
        place = {"name": name, "lat": pos["lat"], "lon": pos["lon"], "kind": _kind(tags), "tags": tags}
        # A big park can touch the search circle while its centre is far outside it.
        if dist(start, place) > radius * 1.2:
            continue
        seen.add(name.lower())
        place["score"] = _score(tags)
        places.append(place)
    places.sort(key=lambda p: -p["score"])
    return places


def plan_stops(start, places, n, budget_m):
    """Pick up to n stops forming a loop from `start` no longer than budget_m (cheapest insertion)."""

    def length(tour):
        pts = [start] + tour + [start]
        return sum(dist(a, b) for a, b in zip(pts, pts[1:])) * DETOUR

    tour = []
    for p in places:
        if len(tour) == n:
            break
        if any(dist(p, q) < 80 for q in tour):
            continue
        best = min((tour[:i] + [p] + tour[i:] for i in range(len(tour) + 1)), key=length)
        if length(best) <= budget_m:
            tour = best
    return tour


def route(points):
    """Walking route through points. Returns (legs, coords); falls back to straight lines offline."""
    path = ";".join(f"{p['lon']:.6f},{p['lat']:.6f}" for p in points)
    try:
        r = get_json(OSRM_FOOT_URL + path, {"steps": "true", "overview": "full", "geometries": "geojson"})
        rt = r["routes"][0]
        return rt["legs"], rt["geometry"]["coordinates"]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError):
        legs = [{"distance": dist(a, b) * DETOUR, "steps": []} for a, b in zip(points, points[1:])]
        return legs, [[p["lon"], p["lat"]] for p in points]


def fmt_distance(m, units="metric"):
    if units == "imperial":
        if m < 300:
            return f"{max(50, round(m * 3.281 / 50) * 50)} feet"
        return f"{m / 1609.34:.1f} miles"
    if m < 1000:
        return f"{max(10, round(m / 10) * 10)} metres"
    return f"{m / 1000:.1f} kilometres"


def describe_leg(leg, a, b, units="metric", max_turns=4):
    """Spoken directions from a to b. Written by code, not the model, so they can't be invented."""
    minutes = max(1, round(leg["distance"] / WALK_SPEED))
    name = b["name"][0].upper() + b["name"][1:]
    text = (
        f"{name} is about {fmt_distance(leg['distance'], units)} away, to the {compass(bearing(a, b))}. "
        f"That's roughly {minutes} minute{'s' if minutes != 1 else ''} on foot."
    )
    turns = []
    for step in leg.get("steps", []):
        man = step["maneuver"]
        way = step.get("name") or "the path"
        mod = man.get("modifier", "")
        if man["type"] == "arrive":
            continue
        if step["distance"] < 25:
            # Too short to be worth saying; a jog like this is obvious on the ground.
            if turns:
                turns[-1][2] += step["distance"]
            continue
        if not turns:
            action = f"head {compass(man.get('bearing_after', 0))} on {way}"
        elif mod == "uturn":
            action = "turn around"
        elif mod.startswith("slight"):
            action = f"bear {mod.split()[1]} onto {way}"
        elif mod.startswith("sharp"):
            action = f"turn sharply {mod.split()[1]} onto {way}"
        elif mod in ("left", "right"):
            action = f"turn {mod} onto {way}"
        elif turns and turns[-1][1] == way:
            # Still the same street going straight: fold it into the previous instruction.
            turns[-1][2] += step["distance"]
            continue
        else:
            action = f"continue onto {way}"
        turns.append([action, way, step["distance"]])
    if turns:
        said = [f"{action} for about {fmt_distance(d, units)}" for action, _, d in turns[:max_turns]]
        said[0] = said[0][0].upper() + said[0][1:]
        text += " " + ", then ".join(said) + "."
        if len(turns) > max_turns:
            text += f" From there, keep heading towards {b['name']}; the map on your phone has the rest."
    return text


def wikipedia_extract(tags, limit=1500):
    """Intro paragraph of the place's Wikipedia article, if OpenStreetMap links to one."""
    try:
        lang, title = None, None
        if ":" in tags.get("wikipedia", ""):
            lang, title = tags["wikipedia"].split(":", 1)
        elif tags.get("wikidata"):
            r = get_json(
                "https://www.wikidata.org/w/api.php",
                {"action": "wbgetentities", "ids": tags["wikidata"], "props": "sitelinks",
                 "sitefilter": "enwiki", "format": "json"},
            )
            title = r["entities"][tags["wikidata"]]["sitelinks"]["enwiki"]["title"]
            lang = "en"
        if not title:
            return ""
        r = get_json(
            f"https://{lang}.wikipedia.org/w/api.php",
            {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
             "redirects": 1, "titles": title, "format": "json"},
        )
        page = next(iter(r["query"]["pages"].values()))
        return page.get("extract", "").strip()[:limit]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, StopIteration):
        return ""


def facts(tags):
    return {k: tags[k] for k in FACT_TAGS if k in tags}
