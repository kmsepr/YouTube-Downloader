import os
import json
import subprocess
import hashlib
from pathlib import Path
from flask import Flask, request, Response, redirect

from unidecode import unidecode
import requests

app = Flask(__name__)

# Paths
BASE_DIR = Path("/mnt/data/ytmp3")
BASE_DIR.mkdir(parents=True, exist_ok=True)

TITLE_CACHE = BASE_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

# Environment variables for cookies
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "/mnt/data/youtube_cookies.txt")
XYLEM_COOKIES = os.getenv("XYLEM_COOKIES", "/mnt/data/xylem_cookies.txt")

# Utils
def safe_filename(name):
    return "".join(c if c.isalnum() or c in " .-" else "_" for c in unidecode(name)).strip()

def save_title(key, title):
    cache = json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    cache[key] = title
    TITLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

def load_title(key):
    try:
        return json.loads(TITLE_CACHE.read_text(encoding="utf-8")).get(key, key)
    except Exception:
        return key

def url_to_key(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()

def get_cached_files():
    files = {}
    for f in BASE_DIR.glob("*"):
        stem = f.stem
        key = stem.split("_")[0]
        files[key] = f
    return files

def choose_cookies(url):
    if "youtube.com" in url or "youtu.be" in url:
        return YOUTUBE_COOKIES
    # Extend domain checks here if needed
    return XYLEM_COOKIES

# Routes
@app.route("/", methods=["GET"])
def home():
    form = """
    <h2>YouTube Search + Generic Video Downloader</h2>
    <form method='get' action='/search'>
        <input name='q' placeholder='Search YouTube...' style='width:60%; padding:10px;'/>
        <button type='submit'>Search</button>
    </form><br>
    <form method='post' action='/direct'>
        <input name='video_url' placeholder='Paste any video URL' style='width:60%; padding:10px;' required/>
        <select name='format'>
            <option value='mp3'>MP3</option>
            <option value='mp4'>MP4</option>
        </select>
        <button type='submit'>Download</button>
    </form>
    <hr>
    <h3>Cached Files</h3>
    <ul>
    """
    items = ""
    cached_files = get_cached_files()
    for key, file in cached_files.items():
        title = load_title(key)
        items += f"<li>{title} — <a href='/download?q={key}&fmt=mp3'>MP3</a> | <a href='/download?q={key}&fmt=mp4'>MP4</a></li>"
    return f"<html><body>{form}{items}</ul></body></html>"

@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q or not YOUTUBE_API_KEY:
        return redirect("/")
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "key": YOUTUBE_API_KEY,
            "q": q,
            "part": "snippet",
            "type": "video",
            "maxResults": 10,
        },
    )
    html = f"<h3>Results for '{q}'</h3><ul>"
    if r.ok:
        for item in r.json().get("items", []):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            save_title(vid, title)
            thumb_url = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
            html += f"""
            <li>
                <img src='{thumb_url}' width='120' height='90'><br>
                <b>{title}</b><br>
                <a href='/download?q={vid}&fmt=mp3'>MP3</a> |
                <a href='/download?q={vid}&fmt=mp4'>MP4</a>
            </li>
            """
    else:
        html += "<li>Failed to fetch results</li>"
    html += "</ul><a href='/'>Back</a>"
    return html

@app.route("/direct", methods=["POST"])
def direct():
    url = request.form.get("video_url")
    fmt = request.form.get("format", "mp3")
    if not url:
        return "No URL provided", 400

    cookies_file = choose_cookies(url)

    try:
        title = subprocess.check_output(
            ["yt-dlp", "--cookies", cookies_file, "--get-title", url], text=True
        ).strip()

        if "youtube.com/watch" in url or "youtu.be/" in url:
            vid = subprocess.check_output(
                ["yt-dlp", "--cookies", cookies_file, "--get-id", url], text=True
            ).strip()
            key = vid
        else:
            key = url_to_key(url)

        save_title(key, title)
        ext = ".mp3" if fmt == "mp3" else ".mp4"
        out_path = BASE_DIR / f"{key}_{safe_filename(title)}{ext}"

        if not out_path.exists():
            if fmt == "mp3":
                subprocess.run(
                    [
                        "yt-dlp",
                        "--cookies",
                        cookies_file,
                        "-x",
                        "--audio-format",
                        "mp3",
                        "-o",
                        str(out_path.with_suffix(".%(ext)s")),
                        url,
                    ],
                    check=True,
                )
            else:
                subprocess.run(
                    [
                        "yt-dlp",
                        "--cookies",
                        cookies_file,
                        "-f",
                        "bestvideo+bestaudio/best",
                        "--recode-video",
                        "mp4",
                        "-o",
                        str(out_path.with_suffix(".%(ext)s")),
                        url,
                    ],
                    check=True,
                )
        return redirect("/")
    except subprocess.CalledProcessError as e:
        return f"Download failed: {e}", 500
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/download")
def download():
    key = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not key:
        return "Missing parameter q", 400

    title = safe_filename(load_title(key))
    ext = ".mp3" if fmt == "mp3" else ".mp4"
    path = BASE_DIR / f"{key}_{title}{ext}"

    if not path.exists():
        return "File not found. Please download it first.", 404

    mimetype = "audio/mpeg" if fmt == "mp3" else "video/mp4"
    return Response(path.open("rb"), mimetype=mimetype)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)