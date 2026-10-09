"""Finding things worth walking to: geocoding, OpenStreetMap places, Wikipedia facts, foot routing."""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from .lang import LANGS

UA = "pocket-walk-narrator/0.1 (open-source hackathon project)"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
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


def compass(deg, L):
    return L["dirs"][round(deg / 45) % 8]


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
    return ""


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
    s += 2 if "historic" in tags or "heritage" in tags or "start_date" in tags else 0
    return s


def find_places(start, radius, lang="en"):
    """Named points of interest within `radius` metres, best first, named in `lang` where the map has it."""
    around = f"(around:{int(radius)},{start['lat']},{start['lon']})"
    # Searching relations is slow and only big parks need it, so only the park line uses nwr.
    query = f"""[out:json][timeout:40];
(
  nw{around}[tourism~"^(artwork|attraction|viewpoint|museum|gallery)$"][name];
  nw{around}[historic][name];
  nwr{around}[leisure~"^(park|garden|nature_reserve)$"][name];
  nw{around}[natural~"^(tree|spring|water|peak|wood|beach)$"][name];
  nw{around}[amenity~"^(fountain|place_of_worship|library|theatre)$"][name];
  nw{around}[man_made~"^(bridge|lighthouse|tower|windmill)$"][name];
);
out center tags 2000;"""
    errors = []
    # The public servers are shared and often busy, so go round them three times, waiting a
    # little longer each round, before giving up.
    for attempt, url in enumerate(OVERPASS_URLS * 3):
        try:
            elements = get_json(url, data={"data": query}, timeout=70)["elements"]
            break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            errors.append(f"{url.split('/')[2]}: {e}")
            if (attempt + 1) % len(OVERPASS_URLS) == 0:
                time.sleep(3 * (attempt + 1) // len(OVERPASS_URLS))
    else:
        raise RuntimeError("OpenStreetMap lookup failed. The public map servers are busy; try again in a minute. ("
                           + "; ".join(errors[-len(OVERPASS_URLS):]) + ")")

    places, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        pos = el if "lat" in el else el.get("center")
        name = tags.get(f"name:{lang}") or tags.get("name")
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


def fmt_distance(m, units="metric", L=LANGS["en"]):
    def decimal(x):
        return f"{x:.1f}".replace(".", L["dec"])

    if units == "imperial":
        if m < 300:
            return f"{max(50, round(m * 3.281 / 50) * 50)} {L['ft']}"
        return f"{decimal(m / 1609.34)} {L['mi']}"
    if m < 1000:
        return f"{max(10, round(m / 10) * 10)} {L['m']}"
    return f"{decimal(m / 1000)} {L['km']}"


def describe_leg(leg, a, b, units="metric", L=LANGS["en"], max_turns=4):
    """Spoken directions from a to b. Written by code, not the model, so they can't be invented."""
    n = max(1, round(leg["distance"] / WALK_SPEED))
    text = L["away"].format(
        name=b["name"],
        dist=fmt_distance(leg["distance"], units, L),
        dir=compass(bearing(a, b), L),
        min=L["minute"] if n == 1 else L["minutes"].format(n=n),
    )
    text = text[0].upper() + text[1:]
    turns = []
    for step in leg.get("steps", []):
        man = step["maneuver"]
        way = step.get("name") or L["path"]
        mod = man.get("modifier", "")
        if man["type"] == "arrive":
            continue
        if step["distance"] < 25:
            # Too short to be worth saying; a jog like this is obvious on the ground.
            if turns:
                turns[-1][2] += step["distance"]
            continue
        if not turns:
            action = L["head"].format(dir=compass(man.get("bearing_after", 0), L), way=way)
        elif mod == "uturn":
            action = L["uturn"]
        elif mod in L["turns"]:
            action = L["turns"][mod].format(way=way)
        elif turns[-1][1] == way:
            # Still the same street going straight: fold it into the previous instruction.
            turns[-1][2] += step["distance"]
            continue
        else:
            action = L["straight"].format(way=way)
        turns.append([action, way, step["distance"]])
    if turns:
        said = [L["for"].format(action=action, dist=fmt_distance(d, units, L)) for action, _, d in turns[:max_turns]]
        said[0] = said[0][0].upper() + said[0][1:]
        text += " " + L["then"].join(said) + "."
        if len(turns) > max_turns:
            text += L["more"].format(name=b["name"])
    return text


def _wiki(lang, params):
    return get_json(f"https://{lang}.wikipedia.org/w/api.php", {"action": "query", "format": "json", **params})


def wikipedia_extract(tags, want="en", limit=3000):
    """The start of the place's Wikipedia article, in the walk's language when there is one."""
    try:
        lang, title = None, None
        if ":" in tags.get("wikipedia", ""):
            lang, title = tags["wikipedia"].split(":", 1)
        elif tags.get("wikidata"):
            r = get_json(
                "https://www.wikidata.org/w/api.php",
                {"action": "wbgetentities", "ids": tags["wikidata"], "props": "sitelinks",
                 "sitefilter": f"{want}wiki|enwiki", "format": "json"},
            )
            links = r["entities"][tags["wikidata"]]["sitelinks"]
            lang = want if f"{want}wiki" in links else "en"
            title = links[f"{lang}wiki"]["title"]
        if not title:
            return ""
        if lang != want:
            # The map usually links the local-language article; look for the listener's version.
            r = _wiki(lang, {"prop": "langlinks", "lllang": want, "redirects": 1, "titles": title})
            links = next(iter(r["query"]["pages"].values())).get("langlinks")
            if links:
                lang, title = want, links[0]["*"]
        r = _wiki(lang, {"prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title})
        page = next(iter(r["query"]["pages"].values()))
        return page.get("extract", "").strip()[:limit]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, StopIteration):
        return ""


def facts(tags):
    return {k: tags[k] for k in FACT_TAGS if k in tags}
