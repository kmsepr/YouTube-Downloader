import os
import time
import json
import shutil
import logging
import subprocess
from pathlib import Path
from flask import Flask, request, Response, redirect, url_for
from urllib.parse import quote_plus
import requests
from unidecode import unidecode

# Setup
app = Flask(__name__)
BASE_DIR = Path("/mnt/data/ytmp3")
TEMP_DIR = Path("/mnt/data/temp")
THUMB_DIR = Path("/mnt/data/thumbs")

for folder in [BASE_DIR, TEMP_DIR, THUMB_DIR]:
    folder.mkdir(exist_ok=True)

TITLE_CACHE = BASE_DIR / "title_cache.json"
TITLE_CACHE.write_text("{}", encoding="utf-8") if not TITLE_CACHE.exists() else None

LAST_VIDEO_FILE = BASE_DIR / "last_video.txt"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

logging.basicConfig(level=logging.DEBUG)

# Utilities
def safe_filename(name):
    name = unidecode(name)
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

def save_title(video_id, title):
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    cache[video_id] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

def load_title(video_id):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
        return cache.get(video_id, video_id)
    except Exception:
        return video_id

def set_last_video(video_id):
    LAST_VIDEO_FILE.write_text(video_id)

def get_last_video():
    return LAST_VIDEO_FILE.read_text().strip() if LAST_VIDEO_FILE.exists() else None

def get_unique_video_ids():
    files = list(BASE_DIR.glob("*.mp3")) + list(BASE_DIR.glob("*.mp4"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        unique_ids.setdefault(vid, file)
    return unique_ids

def download_thumbnail(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok:
            thumb_path = THUMB_DIR / f"{video_id}.jpg"
            thumb_path.write_bytes(r.content)
            return thumb_path
    except Exception as e:
        logging.warning(f"Thumbnail download failed for {video_id}: {e}")
    return None

# Routes
@app.route("/")
def index():
    search_form = """<form method='get' action='/search'>
    <input type='text' name='q' placeholder='Search YouTube...'>
    <input type='submit' value='Search'></form><br>"""

    content = "<h3>Cached Files</h3>"
    for video_id, file in get_unique_video_ids().items():
        title = load_title(video_id)
        content += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a> |
            <a href='/remove?q={video_id}' style='color:red;'>Remove</a>
        </div>"""

    last_video = get_last_video()
    if last_video:
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search", params={
                "key": YOUTUBE_API_KEY,
                "relatedToVideoId": last_video,
                "type": "video",
                "part": "snippet",
                "maxResults": 5
            })
            if r.ok:
                related = r.json().get("items", [])
                content += "<h3>Related to Your Last Search</h3>"
                for item in related:
                    vid = item["id"]["videoId"]
                    title = item["snippet"]["title"]
                    save_title(vid, title)
                    content += f"""
                    <div style='margin-bottom:10px; font-size:small;'>
                        <img src='/thumb/{vid}' width='120' height='90'><br>
                        <b>{title}</b><br>
                        <a href='/download?q={vid}&fmt=mp3'>Download MP3</a> |
                        <a href='/download?q={vid}&fmt=mp4'>Download MP4</a>
                    </div>"""
        except Exception as e:
            logging.warning(f"Related videos fetch failed: {e}")

    return f"<html><body style='font-family:sans-serif;'>{search_form}{content}</body></html>"

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/")

    r = requests.get("https://www.googleapis.com/youtube/v3/search", params={
        "key": YOUTUBE_API_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 15  # Increased to 15
    })

    html = f"""
    <html><head><title>Search results for '{query}'</title></head>
    <body style='font-family:sans-serif;'>
    <form method='get' action='/search'>
        <input type='text' name='q' value='{query}' placeholder='Search YouTube'>
        <input type='submit' value='Search'>
    </form><a href='/'>Home</a><br><br><h3>Search results for '{query}'</h3>"""

    if r.ok:
        results = r.json().get("items", [])
        for item in results:
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            save_title(video_id, title)
            html += f"""
            <div style='margin-bottom:10px; font-size:small;'>
                <img src='/thumb/{video_id}' width='120' height='90'><br>
                <b>{title}</b><br>
                <a href='/download?q={quote_plus(video_id)}&fmt=mp3'>Download MP3</a> |
                <a href='/download?q={quote_plus(video_id)}&fmt=mp4'>Download MP4</a>
            </div>"""

        if results:
            set_last_video(results[0]["id"]["videoId"])

    html += "</body></html>"
    return html

@app.route("/thumb/<video_id>")
def thumbnail_proxy(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok:
            return Response(r.content, mimetype="image/jpeg")
    except Exception:
        pass
    return "Thumbnail not found", 404

@app.route("/download")
def download():
    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400
    return redirect(url_for("ready", q=video_id, fmt=fmt))

@app.route("/ready")
def ready():
    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400

    url = f"https://www.youtube.com/watch?v={video_id}"
    cookies_path = "/mnt/data/cookies.txt"
    if not Path(cookies_path).exists():
        return "Cookies file missing", 400

    ext = "mp3" if fmt == "mp3" else "mp4"
    base_path = TEMP_DIR / f"{video_id}"
    final_path = BASE_DIR / f"{video_id}.{ext}"
    audio_path = base_path.with_suffix(".webm")
    thumb_path = base_path.with_suffix(".jpg")

    if not final_path.exists():
        try:
            # Download audio + thumbnail
            cmd = [
                "yt-dlp", "-f", "bestaudio",
                "--output", str(base_path) + ".%(ext)s",
                "--cookies", cookies_path,
                "--user-agent", FIXED_USER_AGENT,
                "--write-thumbnail", "--convert-thumbnails", "jpg",
                url
            ]
            subprocess.run(cmd, check=True)

            if not audio_path.exists():
                logging.error(f"Audio not downloaded for {video_id}")
                return "Audio download failed", 500

            if fmt == "mp3":
                title = safe_filename(load_title(video_id))
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(audio_path),
                    "-i", str(thumb_path),
                    "-map", "0:a", "-map", "1:v",
                    "-c:a", "libmp3lame", "-c:v", "mjpeg",
                    "-b:a", "24k", "-ar", "22050", "-ac", "1",
                    "-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                    str(final_path)
                ], check=True)
            else:
                # MP4 version
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(audio_path),
                    "-vf", "scale=320:240", "-r", "15",
                    "-b:v", "384k", "-b:a", "12k",
                    str(final_path)
                ], check=True)

            # Clean up
            audio_path.unlink(missing_ok=True)
            thumb_path.unlink(missing_ok=True)

        except Exception as e:
            logging.error(f"Download or conversion failed for {video_id}: {e}")
            return "Download failed", 500

    def stream_and_delete():
        with final_path.open("rb") as f:
            yield from f
        try:
            final_path.unlink()
        except Exception:
            pass

    return Response(stream_and_delete(), mimetype="audio/mpeg" if fmt == "mp3" else "video/mp4")

@app.route("/remove")
def remove():
    video_id = request.args.get("q")
    if not video_id:
        return redirect("/")

    removed = 0
    for file in BASE_DIR.glob(f"{video_id}_*.*"):
        try:
            file.unlink()
            removed += 1
        except Exception as e:
            logging.warning(f"Failed to remove {file}: {e}")

    thumb = THUMB_DIR / f"{video_id}.jpg"
    if thumb.exists():
        thumb.unlink()

    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)