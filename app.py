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
    files = list(BASE_DIR.glob("*.mp3")) + list(BASE_DIR.glob("*.mp4"))
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

# Routes
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
    for video_id, file in get_unique_video_ids().items():
        title = load_title(video_id)
        content += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a> |
            <a href='/download?q={video_id}&fmt=3gp'>Download 3GP</a> |
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

    return f"<html><head><title>YouTube Downloader</title></head><body style='font-family:sans-serif;'>{search_form}{content}</body></html>"

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
        "maxResults": 15
    })

    html = f"""
    <html><head><title>Search results for '{query}'</title></head>
    <body style='font-family:sans-serif;'>
    <div style='text-align:center; margin-top:30px;'>
        <form method='get' action='/search'>
            <input type='text' name='q' value='{query}' placeholder='Search YouTube...'
                   style='width:60%; padding:12px; font-size:18px; border-radius:8px; border:1px solid #ccc;'>
            <input type='submit' value='Search'
                   style='padding:12px 20px; font-size:18px; border-radius:8px; margin-left:10px;'>
        </form>
    </div>
    <a href='/' style='display:block; text-align:center; margin-top:20px;'>Home</a>
    <br><br><h3>Search results for '{query}'</h3>"""

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
                <a href='/details/{video_id}'>View Details</a> |
<a href='/download?q={quote_plus(video_id)}&fmt=mp3'>MP3</a> |
<a href='/download?q={quote_plus(video_id)}&fmt=mp4'>MP4</a> |
<a href='/download?q={quote_plus(video_id)}&fmt=3gp'>3GP</a>
            </div>"""
        if results:
            set_last_video(results[0]["id"]["videoId"])

    html += "</body></html>"
    return html

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

@app.route("/download")
def download():
    video_id = request.args.get("q")
    fmt = request.args.get("fmt", "mp3")
    if not video_id:
        return "Missing video ID", 400
    return redirect(url_for("ready", q=video_id, fmt=fmt))

@app.route("/details/<video_id>")
def details(video_id):
    # Fetch video details
    details_res = requests.get(
        "https://www.googleapis.com/youtube/v3/videos", params={
            "key": YOUTUBE_API_KEY,
            "id": video_id,
            "part": "snippet,statistics"
        }
    )
    details_data = details_res.json()["items"][0] if details_res.ok and details_res.json()["items"] else None

    # Fetch related videos
    related_res = requests.get(
        "https://www.googleapis.com/youtube/v3/search", params={
            "key": YOUTUBE_API_KEY,
            "relatedToVideoId": video_id,
            "type": "video",
            "part": "snippet",
            "maxResults": 10
        }
    )
    related_items = related_res.json().get("items", []) if related_res.ok else []

    if not details_data:
        return "Video not found", 404

    title = details_data["snippet"]["title"]
    save_title(video_id, title)

    content = f"""
    <html><head><title>{title}</title></head><body style='font-family:sans-serif;'>
    <a href='/' style='display:block; margin-bottom:20px;'>Home</a>
    <h2>{title}</h2>
    <img src='/thumb/{video_id}' width='320'><br>
    <p>{details_data["snippet"]["description"][:500]}...</p>
    <p>Views: {details_data["statistics"].get("viewCount", "N/A")}</p>
    <p>Channel: {details_data["snippet"]["channelTitle"]}</p>
    <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
    <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a>
    <hr>
    <h3>Related Videos</h3>
    """

    for item in related_items:
        rid = item["id"]["videoId"]
        rtitle = item["snippet"]["title"]
        save_title(rid, rtitle)
        content += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{rid}' width='120' height='90'><br>
            <b>{rtitle}</b><br>
            <a href='/details/{rid}'>View Details</a> |
            <a href='/download?q={rid}&fmt=mp3'>MP3</a> |
            <a href='/download?q={rid}&fmt=mp4'>MP4</a>
        </div>"""

    content += "</body></html>"
    return content



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
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "--recode-video", "3gp",
                "--postprocessor-args", "-vf scale=240:320 -r 12 -b:v 256k -b:a 24k"
            ]
        else:
            return "Unsupported format", 400

        try:
            subprocess.run(cmd, check=True)
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
            logging.error(f"Download failed for {video_id}: {e}")
            return "Download failed", 500

    return Response(final_path.open("rb"),
                    mimetype="audio/mpeg" if fmt == "mp3" else
                             "video/mp4" if fmt == "mp4" else
                             "video/3gpp")

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