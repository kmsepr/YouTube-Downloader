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
        unique_ids.setdefault(vid, file)
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

    ext = "mp3" if fmt == "mp3" else "mp4" if fmt == "mp4" else "3gp"
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
                "-f", "18", "-o", str(temp_path.with_suffix(".mp4"))  # download to mp4 first
            ]

        try:
            subprocess.run(cmd, check=True)
            if fmt == "3gp":
                mp4_path = temp_path.with_suffix(".mp4")
                if mp4_path.exists():
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(mp4_path),
                        "-s", "240x320", "-r", "15", "-b:v", "256k",
                        "-ac", "1", "-ar", "22050", "-b:a", "24k",
                        "-f", "3gp", str(temp_path)
                    ], check=True)
                    mp4_path.unlink()
                else:
                    raise FileNotFoundError("MP4 intermediate file not found")

            if temp_path.exists():
                if fmt == "mp3":
                    thumb = download_thumbnail(video_id)
                    if thumb and thumb.exists():
                        final_with_art = BASE_DIR / f"{title}.mp3"
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(temp_path), "-i", str(thumb),
                            "-map", "0", "-map", "1", "-c", "copy",
                            "-id3v2_version", "3",
                            "-metadata", f"title={video_title}",
                            "-metadata", f"artist={uploader}",
                            "-metadata", f"album={album_date}",
                            "-metadata:s:v", "title=Album cover",
                            "-metadata:s:v", "comment=Cover (front)",
                            str(final_with_art)
                        ], check=True)
                        shutil.move(str(final_with_art), str(final_path))
                    else:
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(temp_path),
                            "-metadata", f"title={video_title}",
                            "-metadata", f"artist={uploader}",
                            "-metadata", f"album={album_date}",
                            str(final_path)
                        ], check=True)
                    temp_path.unlink()
                else:
                    shutil.move(str(temp_path), str(final_path))
        except Exception as e:
            logging.error(f"Download failed for {video_id} in {fmt}: {e}")
            return f"Download failed for {fmt}", 500

    return Response(final_path.open("rb"),
                    mimetype=(
                        "audio/mpeg" if fmt == "mp3" else
                        "video/mp4" if fmt == "mp4" else
                        "video/3gpp"
                    ))

# Existing routes: index, search, details, remove, thumb (unchanged)
# You can now add `&fmt=3gp` to any /download?q=... link

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)