import os
import json
import shutil
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, request, Response, redirect, url_for
from unidecode import unidecode
import requests

# Setup
app = Flask(__name__)
BASE_DIR = Path("/mnt/data/ytmp3")
TEMP_DIR = Path("/mnt/data/temp")
THUMB_DIR = Path("/mnt/data/thumbs")

for folder in [BASE_DIR, TEMP_DIR, THUMB_DIR]:
    folder.mkdir(exist_ok=True)

TITLE_CACHE = BASE_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

LAST_VIDEO_FILE = BASE_DIR / "last_video.txt"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES", "/mnt/data/youtube_cookies.txt")
XYLEM_COOKIES = os.environ.get("XYLEM_COOKIES", "/mnt/data/xylem_cookies.txt")
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

logging.basicConfig(level=logging.DEBUG)

# Utilities
def safe_filename(name):
    name = unidecode(name)
    return "".join(c if c.isalnum() or c in " .-" else "" for c in name).strip()

def save_title(video_id, title):
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    cache[video_id] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

def load_title(video_id):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
        return cache.get(video_id, video_id)
    except:
        return video_id

def get_unique_video_ids():
    files = list(BASE_DIR.glob("*.mp3")) + list(BASE_DIR.glob("*.mp4"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        unique_ids.setdefault(vid, file)
    return unique_ids

# Direct download route
@app.route("/direct", methods=["POST"])
def direct_download():
    url = request.form.get("video_url")
    fmt = request.form.get("format", "mp3")
    if not url:
        return "Missing URL", 400
    try:
        video_id = subprocess.check_output(["yt-dlp", "--cookies", YOUTUBE_COOKIES, "--get-id", url], text=True).strip()
        title = subprocess.check_output(["yt-dlp", "--cookies", YOUTUBE_COOKIES, "--get-title", url], text=True).strip()
        safe_title = safe_filename(title)
        save_title(video_id, title)
        ext = ".mp3" if fmt == "mp3" else ".mp4"
        out_path = BASE_DIR / f"{video_id}_{safe_title}{ext}"
        if not out_path.exists():
            if fmt == "mp3":
                subprocess.run([
                    "yt-dlp", "--cookies", YOUTUBE_COOKIES, "-x", "--audio-format", "mp3",
                    "-o", str(out_path.with_suffix(".%(ext)s")), url
                ], check=True)
            else:
                subprocess.run([
                    "yt-dlp", "--cookies", YOUTUBE_COOKIES,
                    "-f", "best[ext=mp4]", "--recode-video", "mp4",
                    "-o", str(out_path.with_suffix(".%(ext)s")), url
                ], check=True)
        return redirect("/")
    except Exception as e:
        logging.error(e)
        return f"Download failed: {e}", 500

# Homepage with direct download form + cache listing
@app.route("/")
def home_with_direct():
    form = """
    <html><head><title>YouTube Downloader</title></head><body style='font-family:sans-serif;'>
    <div style='text-align:center; margin-top:30px;'>
        <form method='post' action='/direct'>
            <input type='text' name='video_url' placeholder='Paste YouTube URL here...' style='width:60%; padding:10px;'>
            <select name='format' style='padding:10px;'>
                <option value='mp3'>MP3</option>
                <option value='mp4'>MP4</option>
            </select>
            <input type='submit' value='Download' style='padding:10px 20px;'>
        </form>
    </div><hr><h3>Cached Files</h3><ul>
    """
    items = "\n".join(
        f"<li>{load_title(vid)} — "
        f"<a href='/download?q={vid}&fmt=mp3'>MP3</a> | "
        f"<a href='/download?q={vid}&fmt=mp4'>MP4</a></li>"
        for vid in get_unique_video_ids()
    )
    return form + items + "</ul></body></html>"

# Download route
@app.route("/download")
def download():
    vid = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not vid:
        return "Missing ID", 400
    title = safe_filename(load_title(vid))
    ext = "mp3" if fmt == "mp3" else "mp4"
    path = BASE_DIR / f"{vid}_{title}.{ext}"
    if not path.exists():
        return "File not found", 404
    return Response(path.open("rb"), mimetype="audio/mpeg" if fmt == "mp3" else "video/mp4")

# File remover
@app.route("/remove")
def remove():
    vid = request.args.get("q")
    if not vid:
        return redirect("/")
    for f in BASE_DIR.glob(f"{vid}_*.*"):
        try: f.unlink()
        except: pass
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)