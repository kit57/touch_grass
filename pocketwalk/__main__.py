"""python -m pocketwalk serve            open the web page
python -m pocketwalk walk "Some Park"  make a walk from the terminal"""

import argparse
import sys

from . import places, script, voice
from .build import build_walk
from .server import serve


def main():
    parser = argparse.ArgumentParser(prog="pocketwalk", description="A narrated walk made on your own machine.")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the local web page")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--lan", action="store_true", help="let your phone reach it over Wi-Fi")

    w = sub.add_parser("walk", help="make one walk")
    w.add_argument("place", nargs="?", help="address or landmark to start from")
    w.add_argument("--lat", type=float)
    w.add_argument("--lon", type=float)
    w.add_argument("--minutes", type=int, default=30)
    w.add_argument("--units", choices=["metric", "imperial"], default="metric")
    w.add_argument("--model", default=script.DEFAULT_MODEL, help="any model you have pulled in Ollama")
    w.add_argument("--voice", default=voice.DEFAULT_VOICE, help="any Piper voice name")

    args = parser.parse_args()
    if args.command == "serve":
        return serve(args.port, args.lan)

    if args.place:
        start = places.geocode(args.place)
    elif args.lat is not None and args.lon is not None:
        start = {"lat": args.lat, "lon": args.lon}
    else:
        parser.error("give a place name, or --lat and --lon")
    try:
        result = build_walk(start, args.minutes, args.units, args.model, args.voice)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\n{result['title']}: {len(result['stops'])} stops, {result['distance']}, "
          f"{result['audio_minutes']} min of audio")
    print(f"Open {result['dir']}\\walk.html")


if __name__ == "__main__":
    main()
