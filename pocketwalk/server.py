"""A tiny local web page for making walks and handing them to your phone."""

import json
import mimetypes
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import places
from .build import build_walk

INDEX = Path(__file__).with_name("index.html")
WALKS = Path("walks")
jobs = {}
one_at_a_time = threading.Lock()  # one GPU, one walk


def run_job(job_id, params):
    job = jobs[job_id]
    try:
        with one_at_a_time:
            if params.get("place"):
                start = places.geocode(params["place"])
            else:
                start = {"lat": float(params["lat"]), "lon": float(params["lon"])}
            job["result"] = build_walk(
                start,
                minutes=max(10, min(120, int(params.get("minutes", 30)))),
                units="imperial" if params.get("units") == "imperial" else "metric",
                out_root=WALKS,
                progress=lambda msg: job.update(status=msg),
            )
        job["state"] = "done"
    except Exception as e:  # shown to the person at the keyboard
        job.update(state="error", status=str(e))


def list_walks():
    walks = []
    for meta in sorted(WALKS.glob("*/walk.json"), reverse=True):
        w = json.loads(meta.read_text(encoding="utf-8"))
        walks.append({"id": meta.parent.name, "title": w["title"], "distance": w["distance"],
                      "stops": [s["name"] for s in w["stops"]]})
    return walks


class Handler(BaseHTTPRequestHandler):
    def send(self, body, content_type="application/json", status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self.send(INDEX.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/walks":
            return self.send(list_walks())
        if path.startswith("/api/jobs/"):
            job = jobs.get(path.rsplit("/", 1)[1])
            return self.send(job or {"state": "error", "status": "Unknown job"}, status=200 if job else 404)
        if path.startswith("/walks/"):
            root = WALKS.resolve()
            target = (root / path[len("/walks/"):]).resolve()
            if root in target.parents and target.is_file():
                kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if kind.startswith("text/"):
                    kind += "; charset=utf-8"
                return self.send(target.read_bytes(), kind)
        self.send({"error": "Not found"}, status=404)

    def do_POST(self):
        if self.path != "/api/walks" or self.headers.get("Content-Type") != "application/json":
            return self.send({"error": "Not found"}, status=404)
        try:
            params = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self.send({"error": "Bad request"}, status=400)
        job_id = uuid.uuid4().hex[:12]
        jobs[job_id] = {"state": "running", "status": "Waiting for the previous walk to finish"}
        threading.Thread(target=run_job, args=(job_id, params), daemon=True).start()
        self.send({"job": job_id})

    def log_message(self, *args):
        pass


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 80))  # no packets sent; just picks the outgoing interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def serve(port=8000, lan=False):
    WALKS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), Handler)
    print(f"Pocket Walk is at http://localhost:{port}")
    if lan:
        print(f"On your phone (same Wi-Fi): http://{lan_address()}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
