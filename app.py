import os
import time
import logging
import subprocess
from flask import Flask, request, Response, redirect
from pathlib import Path
from urllib.parse import quote_plus
import requests
import json
from unidecode import unidecode

app = Flask(__name__)
TMP_DIR = Path("/mnt/data/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

TITLE_CACHE = TMP_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

logging.basicConfig(level=logging.DEBUG)

last_video_id = None  # Tracks the last searched or downloaded video

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
    files = list(TMP_DIR.glob("*.mp3")) + list(TMP_DIR.glob("*.mp4"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        if vid not in unique_ids:
            unique_ids[vid] = file
    return unique_ids

def safe_filename(name):
    name = unidecode(name)  # Transliterates Unicode to ASCII
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

def get_related_videos(video_id):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "part": "snippet",
        "type": "video",
        "relatedToVideoId": video_id,
        "maxResults": 5
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        logging.warning(f"Failed to get related videos: {e}")
        return []

@app.route("/")
def index():
    global last_video_id

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

    related_html = ""
    if last_video_id:
        related_html += "<h3>Related Videos</h3>"
        for item in get_related_videos(last_video_id):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            thumb = item["snippet"]["thumbnails"]["medium"]["url"]
            save_title(vid, title)
            related_html += f"""
            <div style='margin-bottom:10px; font-size:small;'>
                <img src='{thumb}' width='120' height='90'><br>
                <b>{title}</b><br>
                <a href='/download?q={vid}&fmt=mp3'>Download MP3</a> |
                <a href='/download?q={vid}&fmt=mp4'>Download MP4</a>
            </div>
            """

    return f"<html><body style='font-family:sans-serif;'>{search_html}{cached_html}{related_html}</body></html>"

@app.route("/search")
def search():
    global last_video_id

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
    </form><br><h3>Search results for '{query}'</h3>
    """

    for item in results:
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        save_title(video_id, title)
        last_video_id = video_id
        html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={quote_plus(video_id)}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={quote_plus(video_id)}&fmt=mp4'>Download MP4</a>
        </div>
        """
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
    global last_video_id

    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400

    last_video_id = video_id

    title = safe_filename(load_title(video_id))
    ext = "mp3" if fmt == "mp3" else "mp4"
    filename = f"{video_id}_{title}.{ext}"
    file_path = TMP_DIR / filename

    if not file_path.exists():
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookies_path = "/mnt/data/cookies.txt"
        if not Path(cookies_path).exists():
            return "Cookies file not found", 400

        base_cmd = [
            "yt-dlp",
            "--output", str(TMP_DIR / f"{video_id}_{title}.%(ext)s"),
            "--user-agent", FIXED_USER_AGENT,
            "--cookies", cookies_path,
            url
        ]

        if fmt == "mp3":
            cmd = base_cmd[:1] + ["-f", "bestaudio"] + base_cmd[1:] + [
                "--postprocessor-args", "-ar 22050 -ac 1 -b:a 40k",
                "--extract-audio", "--audio-format", "mp3"
            ]
        else:
            cmd = base_cmd[:1] + ["-f", "best[ext=mp4]"] + base_cmd[1:] + [
                "--recode-video", "mp4",
                "--postprocessor-args", "-vf scale=320:240 -r 15 -b:v 384k -b:a 12k"
            ]

        success = False
        for attempt in range(3):
            try:
                logging.debug(f"Attempt {attempt + 1}: running yt-dlp...")
                subprocess.run(cmd, check=True)
                success = True
                break
            except subprocess.CalledProcessError as e:
                logging.warning(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(10)

        if not success or not file_path.exists():
            return "Download failed after retries", 500

    def generate():
        with open(file_path, "rb") as f:
            yield from f

    mimetype = "audio/mpeg" if fmt == "mp3" else "video/mp4"
    return Response(generate(), mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)