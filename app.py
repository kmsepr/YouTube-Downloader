import os
import json
import requests
import logging
from flask import Flask, request, redirect, Response, session
from urllib.parse import quote_plus
from pathlib import Path
from unidecode import unidecode

app = Flask(__name__)
app.secret_key = "random_secret_key"  # Needed for session

# Temporary directory for saving files
TMP_DIR = Path("/mnt/data/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

# Cache file for video titles
TITLE_CACHE = TMP_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

# Environment variable for YouTube API key
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

# Setup logging
logging.basicConfig(level=logging.INFO)

# Sanitize filenames by removing non-ASCII characters
def safe_filename(name):
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in unidecode(name))

# Save video title to cache
def save_title(video_id, title):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    except:
        cache = {}
    cache[video_id] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

# Load video title from cache
def load_title(video_id):
    try:
        cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
        return cache.get(video_id, video_id)
    except:
        return video_id

# Get unique video files from the cache directory
def get_unique_video_ids():
    files = list(TMP_DIR.glob("*.mp3")) + list(TMP_DIR.glob("*.mp4"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        if vid not in unique_ids:
            unique_ids[vid] = file
    return unique_ids

# Fetch related videos using YouTube API
def fetch_related_videos(query):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 6
    }
    r = requests.get(url, params=params)
    return r.json().get("items", [])

@app.route("/")
def index():
    search_html = """<form method='get' action='/search'>
    <input type='text' name='q' placeholder='Search YouTube...'>
    <input type='submit' value='Search'></form><br>"""

    cached_html = "<h3>Cached Downloads</h3>"
    for video_id, file in get_unique_video_ids().items():
        title = load_title(video_id)
        cached_html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a>
        </div>
        """

    # Show related videos if a search was recently done
    related_html = ""
    query = session.get("last_query", "")
    if query:
        related_html = "<h3>Related Videos</h3>"
        for item in fetch_related_videos(query):
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
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/")
    session["last_query"] = query

    results = fetch_related_videos(query)

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
        thumb = item["snippet"]["thumbnails"]["medium"]["url"]
        save_title(video_id, title)
        html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='{thumb}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a>
        </div>
        """
    html += "</body></html>"
    return html

@app.route("/thumb/<video_id>")
def thumbnail_proxy(video_id):
    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return Response(r.content, mimetype="image/jpeg")
    except:
        pass
    return "Thumbnail not found", 404

@app.route("/download")
def download():
    import subprocess

    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400

    title = safe_filename(load_title(video_id))
    ext = "mp3" if fmt == "mp3" else "mp4"
    filename = f"{video_id}_{title}.{ext}"
    file_path = TMP_DIR / filename

    if not file_path.exists():
        url = f"https://www.youtube.com/watch?v={video_id}"
        subprocess.run([
            "yt-dlp", "-f", "bestaudio/best", "--extract-audio" if ext == "mp3" else "",
            "--audio-format", ext if ext == "mp3" else "",
            "-o", str(file_path), url
        ], check=True)

    return Response(file_path.read_bytes(), mimetype=f"audio/{ext}" if ext == "mp3" else f"video/{ext}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)