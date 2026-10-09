"""python -m pocketwalk serve            open the web page
python -m pocketwalk walk "Some Park"  make a walk from the terminal"""

import argparse
import sys

from . import places, script, voice
from .build import build_walk
from .lang import LANGS
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
    w.add_argument("--stops", type=int, help="how many stops to aim for (default: about one per 8 minutes)")
    w.add_argument("--units", choices=["metric", "imperial"], default="metric")
    w.add_argument("--model", default=script.DEFAULT_MODEL, help="any model you have pulled in Ollama")
    w.add_argument("--lang", choices=list(LANGS), default="en",
                   help="language of the narration: " + ", ".join(f"{k} ({v['name']})" for k, v in LANGS.items()))
    w.add_argument("--voice-engine", choices=voice.ENGINES, default="piper",
                   help="piper runs on this computer; elevenlabs is a cloud voice")
    w.add_argument("--voice", help="a Piper voice name or an ElevenLabs voice id (default: one that suits --lang)")

    w.add_argument("--voice-speed", type=float, help="ElevenLabs only: 0.7 (slow) to 1.2 (fast)")
    w.add_argument("--voice-stability", type=float,
                   help="ElevenLabs only: 0 (expressive, varies) to 1 (steady, flatter)")
    w.add_argument("--voice-style", type=float, help="ElevenLabs only: 0 (neutral) to 1 (exaggerated)")

    sub.add_parser("voices", help="list the ElevenLabs voices your key can use")

    args = parser.parse_args()
    if args.command == "serve":
        return serve(args.port, args.lan)
    if args.command == "voices":
        try:
            for v in voice.elevenlabs_voices():
                print(f"{v['id']}  {v['name']}" + (f"  ({v['about']})" if v["about"] else ""))
        except RuntimeError as e:
            sys.exit(str(e))
        return

    if args.place:
        start = places.geocode(args.place)
    elif args.lat is not None and args.lon is not None:
        start = {"lat": args.lat, "lon": args.lon}
    else:
        parser.error("give a place name, or --lat and --lon")
    settings = {"speed": args.voice_speed, "stability": args.voice_stability, "style": args.voice_style}
    try:
        result = build_walk(start, args.minutes, args.units, args.model, args.voice,
                            engine=args.voice_engine, voice_settings=settings, lang=args.lang, stops_wanted=args.stops)
    except RuntimeError as e:
        sys.exit(str(e))
    if result["stops_wanted"] and len(result["stops"]) < result["stops_wanted"]:
        print(f"\nOnly {len(result['stops'])} of the {result['stops_wanted']} stops you asked for fit in "
              f"{args.minutes} minutes here. A longer walk makes room for more.")
    print(f"\n{result['title']}: {len(result['stops'])} stops, {result['distance']}, "
          f"{result['audio_minutes']} min of audio")
    print(f"Open {result['dir']}\\walk.html")


if __name__ == "__main__":
    main()
