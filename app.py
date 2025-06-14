import os
import time
import json
import shutil
import logging
import subprocess
from datetime import datetime
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
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

LAST_VIDEO_FILE = BASE_DIR / "last_video.txt"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

logging.basicConfig(level=logging.DEBUG)

# Utilities
def safe_filename(name):
    name = unidecode(name)
    return "".join(c if c.isalnum() or c in " .-" else "" for c in name)

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
    files = list(BASE_DIR.glob("*.mp3")) + list(BASE_DIR.glob("*.mp4")) + list(BASE_DIR.glob("*.3gp"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        if vid not in unique_ids:
            unique_ids[vid] = []
        unique_ids[vid].append(file)
    return unique_ids

def download_thumbnail(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                         headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok:
            thumb_path = THUMB_DIR / f"{video_id}.jpg"
            thumb_path.write_bytes(r.content)
            return thumb_path
    except Exception as e:
        logging.warning(f"Thumbnail download failed for {video_id}: {e}")
    return None

@app.route("/")
def index():
    search_form = """
    <div style='text-align:center; margin-top:30px;'>
        <form method='get' action='/search'>
            <input type='text' name='q' placeholder='Search YouTube...'
                   style='width:60%; padding:12px; font-size:18px; border-radius:8px; border:1px solid #ccc;'>
            <input type='submit' value='Search'
                   style='padding:12px 20px; font-size:18px; border-radius:8px; margin-left:10px;'>
        </form>
    </div><br>
    """

    content = "<h3>Cached Files</h3>"
    for video_id, files in get_unique_video_ids().items():
        title = load_title(video_id)
        content += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>"""
        for fmt in ["mp3", "mp4", "3gp"]:
            if any(file.name.endswith(f".{fmt}") for file in files):
                content += f"<a href='/download?q={video_id}&fmt={fmt}'>Download {fmt.upper()}</a> | "
        content += f"<a href='/remove?q={video_id}' style='color:red;'>Remove</a></div>"

    return f"<html><head><title>Downloader</title></head><body>{search_form}{content}</body></html>"

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
    title = safe_filename(load_title(video_id))
    ext = fmt
    final_path = BASE_DIR / f"{video_id}_{title}.{ext}"
    temp_path = TEMP_DIR / f"{video_id}_{title}.{ext}"

    if not final_path.exists():
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookies_path = "/mnt/data/cookies.txt"
        if not Path(cookies_path).exists():
            return "Cookies file missing", 400

        try:
            output = subprocess.check_output([
                "yt-dlp", "--print", "%(title)s|||%(uploader)s|||%(upload_date)s",
                "--cookies", cookies_path, url
            ], text=True).strip()
            parts = output.split("|||")
            if len(parts) != 3:
                raise ValueError("Unexpected metadata format.")
            video_title, uploader, upload_date = parts
            album_date = datetime.strptime(upload_date, "%Y%m%d").strftime("%B %Y")
        except Exception as e:
            logging.error(f"Metadata extraction failed: {e}")
            return "Metadata fetch failed", 500

        base_cmd = [
            "yt-dlp", "--output", str(temp_path.with_suffix(".%(ext)s")),
            "--user-agent", FIXED_USER_AGENT, "--cookies", cookies_path, url
        ]

        if fmt == "mp3":
            cmd = base_cmd + [
                "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3",
                "--postprocessor-args", "-ar 22050 -ac 1 -b:a 24k"
            ]
        elif fmt == "mp4":
            cmd = base_cmd + [
                "-f", "best[ext=mp4]", "--recode-video", "mp4",
                "--postprocessor-args", "-vf scale=320:240 -r 15 -b:v 384k -b:a 12k"
            ]
        elif fmt == "3gp":
            cmd = base_cmd + [
                "-f", "18", "--recode-video", "3gp",
                "--postprocessor-args", "-vf scale=320:240 -r 15 -b:v 256k -b:a 32k"
            ]
        else:
            return "Unsupported format", 400

        try:
            subprocess.run(cmd, check=True)
            if temp_path.exists():
                shutil.move(str(temp_path), str(final_path))
        except Exception as e:
            logging.error(f"Download failed for {video_id}: {e}")
            return "Download failed", 500

    mimetype = "audio/mpeg" if fmt == "mp3" else ("video/3gpp" if fmt == "3gp" else "video/mp4")
    return Response(final_path.open("rb"), mimetype=mimetype)

@app.route("/thumb/<video_id>")
def thumbnail_proxy(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                         headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok:
            return Response(r.content, mimetype="image/jpeg")
    except Exception:
        pass
    return "Thumbnail not found", 404

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