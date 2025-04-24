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
TMP_DIR = Path("/mnt/data/ytcache")
TMP_DIR.mkdir(exist_ok=True)

TITLE_CACHE = TMP_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

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
    files = list(TMP_DIR.glob("*.*"))
    unique_ids = {}
    for file in files:
        vid = file.stem.split("_")[0]
        if vid not in unique_ids:
            unique_ids[vid] = file
    return unique_ids

def safe_filename(name):
    name = unidecode(name)
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

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
            <a href='/download?q={video_id}&fmt=mp3'>MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>MP4</a> |
            <a href='/download?q={video_id}&fmt=3gp'>3GP</a>
        </div>
        """
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

    html = f"""<html><head><title>Search results for '{query}'</title></head>
    <body style='font-family:sans-serif;'>
    <form method='get' action='/search'>
        <input type='text' name='q' value='{query}' placeholder='Search YouTube'>
        <input type='submit' value='Search'>
    </form><br><h3>Search results for '{query}'</h3>"""

    for item in results:
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        save_title(video_id, title)
        html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={quote_plus(video_id)}&fmt=mp3'>MP3</a> |
            <a href='/download?q={quote_plus(video_id)}&fmt=mp4'>MP4</a> |
            <a href='/download?q={quote_plus(video_id)}&fmt=3gp'>3GP</a>
        </div>"""
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

    title = safe_filename(load_title(video_id))
    ext = "3gp" if fmt == "3gp" else ("mp4" if fmt == "mp4" else "mp3")
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
                "--extract-audio", "--audio-format", "mp3",
                "--postprocessor-args", "-ar 22050 -ac 1 -b:a 40k"
            ]
        elif fmt == "mp4":
            cmd = base_cmd[:1] + ["-f", "best[ext=mp4]"] + base_cmd[1:] + [
                "--recode-video", "mp4",
                "--postprocessor-args", "-vf scale=320:240 -r 15 -b:v 384k -b:a 12k -ar 22050 -ac 1"
            ]
        else:  # 3gp
            cmd = base_cmd[:1] + ["-f", "best[ext=mp4]"] + base_cmd[1:]
            temp_mp4 = TMP_DIR / f"{video_id}_{title}.mp4"
            output_3gp = TMP_DIR / filename

        success = False
        for attempt in range(3):
            try:
                logging.debug(f"Attempt {attempt + 1}: running yt-dlp...")
                subprocess.run(cmd, check=True)
                if fmt == "3gp":
                    # Here we change to H.263 for video and AAC for audio in 3GP format
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(temp_mp4),
                        "-vf", "scale=176:144", "-r", "15",  # QCIF resolution with 15fps
                        "-c:v", "h263",  # Use H.263 for video
                        "-c:a", "aac",  # Use AAC for audio
                        "-ar", "22050",  # Audio sample rate
                        "-ab", "64k",  # Audio bitrate
                        "-ac", "1",  # Mono audio
                        "-b:v", "128k",  # Video bitrate
                        "-f", "3gp",  # Force 3GP container format
                        str(output_3gp)
                    ], check=True)
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

    mimetype = {
        "mp3": "audio/mpeg",
        "mp4": "video/mp4",
        "3gp": "video/3gpp"
    }.get(ext, "application/octet-stream")

    return Response(generate(), mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)