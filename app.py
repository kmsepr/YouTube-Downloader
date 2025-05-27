import os
import json
import logging
import subprocess
from pathlib import Path
from flask import Flask, request, Response, redirect, url_for
from unidecode import unidecode
import requests

app = Flask(__name__)

# Paths
BASE_DIR = Path("/mnt/data/ytmp3")
for d in [BASE_DIR]: d.mkdir(exist_ok=True)

# Environment
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "/mnt/data/youtube_cookies.txt")
FIXED_USER_AGENT = "Mozilla/5.0"
TITLE_CACHE = BASE_DIR / "title_cache.json"
TITLE_CACHE.write_text("{}", encoding="utf-8") if not TITLE_CACHE.exists() else None

# Utils
def safe_filename(name):
    return "".join(c if c.isalnum() or c in " .-" else "_" for c in unidecode(name)).strip()

def save_title(vid, title):
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    cache[vid] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

def load_title(vid):
    try:
        return json.loads(TITLE_CACHE.read_text()).get(vid, vid)
    except:
        return vid

def get_files():
    return {f.stem.split("_")[0]: f for f in BASE_DIR.glob("*.*")}

# Home + Search + Direct form
@app.route("/", methods=["GET"])
def home():
    form = """
    <h2>YouTube Downloader</h2>
    <form method='get' action='/search'>
        <input name='q' placeholder='Search YouTube...' style='width:60%; padding:10px;'/>
        <button type='submit'>Search</button>
    </form><br>
    <form method='post' action='/direct'>
        <input name='video_url' placeholder='Paste YouTube URL' style='width:60%; padding:10px;'/>
        <select name='format'><option value='mp3'>MP3</option><option value='mp4'>MP4</option></select>
        <button type='submit'>Download</button>
    </form><hr><h3>Cached Files</h3><ul>
    """
    items = ""
    for vid, file in get_files().items():
        title = load_title(vid)
        items += f"<li>{title} — <a href='/download?q={vid}&fmt=mp3'>MP3</a> | <a href='/download?q={vid}&fmt=mp4'>MP4</a></li>"
    return f"<html><body>{form}{items}</ul></body></html>"

# Search
@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q: return redirect("/")
    r = requests.get("https://www.googleapis.com/youtube/v3/search", params={
        "key": YOUTUBE_API_KEY, "q": q, "part": "snippet", "type": "video", "maxResults": 10
    })
    html = f"<h3>Results for '{q}'</h3><ul>"
    if r.ok:
        for item in r.json().get("items", []):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            save_title(vid, title)
            html += f"<li>{title} — <a href='/download?q={vid}&fmt=mp3'>MP3</a> | <a href='/download?q={vid}&fmt=mp4'>MP4</a></li>"
    html += "</ul><a href='/'>Back</a>"
    return html

# Direct paste URL
@app.route("/direct", methods=["POST"])
def direct():
    url = request.form.get("video_url")
    fmt = request.form.get("format", "mp3")
    try:
        vid = subprocess.check_output(["yt-dlp", "--cookies", YOUTUBE_COOKIES, "--get-id", url], text=True).strip()
        title = subprocess.check_output(["yt-dlp", "--cookies", YOUTUBE_COOKIES, "--get-title", url], text=True).strip()
        save_title(vid, title)
        ext = ".mp3" if fmt == "mp3" else ".mp4"
        out_path = BASE_DIR / f"{vid}_{safe_filename(title)}{ext}"
        if not out_path.exists():
            if fmt == "mp3":
                subprocess.run(["yt-dlp", "--cookies", YOUTUBE_COOKIES, "-x", "--audio-format", "mp3",
                                "-o", str(out_path.with_suffix(".%(ext)s")), url], check=True)
            else:
                subprocess.run(["yt-dlp", "--cookies", YOUTUBE_COOKIES,
                                "-f", "best[ext=mp4]", "--recode-video", "mp4",
                                "-o", str(out_path.with_suffix(".%(ext)s")), url], check=True)
        return redirect("/")
    except Exception as e:
        return f"Download failed: {e}", 500

# Download
@app.route("/download")
def download():
    vid = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    title = safe_filename(load_title(vid))
    ext = ".mp3" if fmt == "mp3" else ".mp4"
    path = BASE_DIR / f"{vid}_{title}{ext}"
    if not path.exists():
        return "Not found", 404
    return Response(path.open("rb"), mimetype="audio/mpeg" if fmt == "mp3" else "video/mp4")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)