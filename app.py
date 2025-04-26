import os
import time
import logging
import subprocess
from flask import Flask, request, Response, redirect, url_for
from pathlib import Path
from urllib.parse import quote_plus
import requests
import json
from unidecode import unidecode
import shutil

app = Flask(__name__)
BASE_DIR = Path("/mnt/data/ytmp3")
TEMP_DIR = Path("/mnt/data/temp")
THUMB_DIR = Path("/mnt/data/thumbs")
BASE_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)

TITLE_CACHE = BASE_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

LAST_VIDEO_FILE = BASE_DIR / "last_video.txt"
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

logging.basicConfig(level=logging.DEBUG)

def save_title(video_id, title):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    cache[video_id] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

def load_title(video_id):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
        return cache.get(video_id, video_id)
    except Exception:
        return video_id

def get_unique_video_ids():
    files = list(BASE_DIR.glob("*.mp3")) + list(BASE_DIR.glob("*.mp4"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        if vid not in unique_ids:
            unique_ids[vid] = file
    return unique_ids

def safe_filename(name):
    name = unidecode(name)
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

def set_last_video(video_id):
    LAST_VIDEO_FILE.write_text(video_id)

def get_last_video():
    if LAST_VIDEO_FILE.exists():
        return LAST_VIDEO_FILE.read_text().strip()
    return None

def download_thumbnail(video_id):
    thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    thumb_path = THUMB_DIR / f"{video_id}.jpg"
    try:
        r = requests.get(thumb_url, headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.status_code == 200:
            thumb_path.write_bytes(r.content)
            return thumb_path
    except Exception as e:
        logging.warning(f"Thumbnail download failed: {e}")
    return None

@app.route("/")
def index():
    search_html = """<form method='get' action='/search'>
    <input type='text' name='q' placeholder='Search YouTube...'>
    <input type='submit' value='Search'></form><br>"""

    cached_html = "<h3>Cached Files</h3>"
    for video_id, file in get_unique_video_ids().items():
        ext = file.suffix.lstrip(".")
        title = load_title(video_id)
        cached_html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a>
        </div>
        """

    last_video = get_last_video()
    if last_video:
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "key": YOUTUBE_API_KEY,
                "relatedToVideoId": last_video,
                "type": "video",
                "part": "snippet",
                "maxResults": 5
            }
            r = requests.get(url, params=params)
            results = r.json().get("items", [])

            related_html = "<h3>Related to Your Last Search</h3>"
            for item in results:
                vid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                save_title(vid, title)
                related_html += f"""
                <div style='margin-bottom:10px; font-size:small;'>
                    <img src='/thumb/{vid}' width='120' height='90'><br>
                    <b>{title}</b><br>
                    <a href='/download?q={vid}&fmt=mp3'>Download MP3</a> |
                    <a href='/download?q={vid}&fmt=mp4'>Download MP4</a>
                </div>
                """
            cached_html += related_html
        except Exception as e:
            logging.warning(f"Failed to load related videos: {e}")

    return f"<html><body style='font-family:sans-serif;'>{search_html}{cached_html}</body></html>"

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/")

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 5
    }

    r = requests.get(url, params=params)
    results = r.json().get("items", [])

    html = f"""
    <html><head><title>Search results for '{query}'</title></head>
    <body style='font-family:sans-serif;'>
    <form method='get' action='/search'>
        <input type='text' name='q' value='{query}' placeholder='Search YouTube'>
        <input type='submit' value='Search'>
    </form>
    <a href='/'>Home</a><br><br>
    <h3>Search results for '{query}'</h3>
    """

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
        </div>
        """

    if results:
        set_last_video(results[0]["id"]["videoId"])

    html += "</body></html>"
    return html

@app.route("/thumb/<video_id>")
def thumbnail_proxy(video_id):
    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    try:
        r = requests.get(url, headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.status_code == 200:
            return Response(r.content, mimetype="image/jpeg")
        else:
            return "Thumbnail not found", 404
    except Exception:
        return "Error fetching thumbnail", 500

@app.route("/download")
def download():
    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400

    return redirect(url_for('ready', q=video_id, fmt=fmt))

@app.route("/ready")
def ready():
    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")

    title = safe_filename(load_title(video_id))
    ext = "mp3" if fmt == "mp3" else "mp4"
    final_path = BASE_DIR / f"{video_id}_{title}.{ext}"
    temp_path = TEMP_DIR / f"{video_id}_{title}.{ext}"

    if not final_path.exists():
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookies_path = "/mnt/data/cookies.txt"
        if not Path(cookies_path).exists():
            return "Cookies file not found", 400

        base_cmd = [
            "yt-dlp",
            "--output", str(temp_path.with_suffix(".%(ext)s")),
            "--user-agent", FIXED_USER_AGENT,
            "--cookies", cookies_path,
            url
        ]

        if fmt == "mp3":
            cmd = base_cmd[:1] + ["-f", "bestaudio"] + base_cmd[1:] + [
                "--extract-audio", "--audio-format", "mp3",
                "--postprocessor-args", "-ar 22050 -ac 1 -b:a 40k"
            ]
        else:
            cmd = base_cmd[:1] + ["-f", "best[ext=mp4]"] + base_cmd[1:] + [
                "--recode-video", "mp4",
                "--postprocessor-args", "-vf scale=320:240 -r 15 -b:v 384k -b:a 12k"
            ]

        try:
            subprocess.run(cmd, check=True)
            if temp_path.exists():
                if fmt == "mp3":
                    thumb_path = download_thumbnail(video_id)
                    if thumb_path and thumb_path.exists():
                        final_with_art = BASE_DIR / f"{video_id}_{title}_with_art.mp3"
                        subprocess.run([
                            "ffmpeg", "-y",
                            "-i", str(temp_path),
                            "-i", str(thumb_path),
                            "-map", "0", "-map", "1",
                            "-c", "copy",
                            "-id3v2_version", "3",
                            "-metadata:s:v", "title=Album cover",
                            "-metadata:s:v", "comment=Cover (front)",
                            str(final_with_art)
                        ], check=True)
                        shutil.move(str(final_with_art), str(final_path))
                    else:
                        shutil.move(str(temp_path), str(final_path))
                else:
                    shutil.move(str(temp_path), str(final_path))
        except Exception as e:
            logging.error(f"Download failed: {e}")
            return "Download failed", 500

    def generate_and_delete():
        with open(final_path, "rb") as f:
            yield from f
        try:
            final_path.unlink()
        except Exception:
            pass

    mimetype = "audio/mpeg" if fmt == "mp3" else "video/mp4"
    return Response(generate_and_delete(), mimetype=mimetype)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)