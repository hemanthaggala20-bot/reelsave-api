import os
import re
import time
from collections import defaultdict
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*"))

PATH_RE = re.compile(r"^/(reel|reels|p)/[\w-]+")
RATE_LIMIT = 10
RATE_WINDOW = 60
hits = defaultdict(list)


def rate_limited(ip):
    now = time.time()
    hits[ip] = [t for t in hits[ip] if now - t < RATE_WINDOW]
    if len(hits[ip]) >= RATE_LIMIT:
        return True
    hits[ip].append(now)
    return False


def is_reel_link(link):
    try:
        u = urlparse(link)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (
        u.scheme in ("http", "https")
        and (host == "instagram.com" or host.endswith(".instagram.com"))
        and bool(PATH_RE.match(u.path))
    )


@app.get("/fetch")
def fetch():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if rate_limited(ip):
        return jsonify(error="Too many requests, try again in a minute."), 429

    link = request.args.get("url", "").strip()
    if not is_reel_link(link):
        return jsonify(error="Not a valid Instagram reel link."), 400

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception:
        return jsonify(error="Could not fetch this reel. It may be private or removed."), 502

    video = info.get("url")
    if not video:
        formats = [f for f in info.get("formats", []) if f.get("vcodec") != "none" and f.get("url")]
        if formats:
            video = max(formats, key=lambda f: f.get("height") or 0)["url"]
    if not video:
        return jsonify(error="No video found in this link."), 404

    return jsonify(video=video, title=info.get("title"))


@app.get("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
