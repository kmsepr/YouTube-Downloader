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
BASE_DIR = Path("/mnt/data/ytmp3")
BASE_DIR.mkdir(exist_ok=True)

TITLE_CACHE = BASE_DIR / "title_cache.json"
if not TITLE_CACHE.exists():
    TITLE_CACHE.write_text("{}", encoding="utf-8")

LAST_VIDEO_FILE = BASE_DIR / "last_video.txt"
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

logging.basicConfig(level=logging.DEBUG)


def save_title(video_id, title, cache_dir):
    try:
        cache = json.loads((cache_dir / "title_cache.json").read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    cache[video_id] = title
    (cache_dir / "title_cache.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def load_title(video_id, cache_dir):
    try:
        cache = json.loads((cache_dir / "title_cache.json").read_text(encoding="utf-8"))
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
    name = unidecode(name)  # Transliterates Unicode to ASCII
    return "".join(c if c.isalnum() or c in " .-" else "" for c in name)


def set_last_video(video_id):
    LAST_VIDEO_FILE.write_text(video_id)


def get_last_video():
    if LAST_VIDEO_FILE.exists():
        return LAST_VIDEO_FILE.read_text().strip()
    return None


@app.route("/")
def index():
    search_html = """<form method='get' action='/search'> <input type='text' name='q' placeholder='Search YouTube...'> <input type='submit' value='Search'></form><br>"""

    cached_html = "<h3>Cached Files</h3>"
    for video_id, file in get_unique_video_ids().items():
        ext = file.suffix.lstrip(".")
        title = load_title(video_id, BASE_DIR)
        cached_html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/video/{video_id}'>View Details</a> |
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
                save_title(vid, title, BASE_DIR)
                related_html += f"""
                <div style='margin-bottom:10px; font-size:small;'>
                    <img src='/thumb/{vid}' width='120' height='90'><br>
                    <b>{title}</b><br>
                    <a href='/video/{vid}'>View Details</a> |
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
        save_title(video_id, title, BASE_DIR)
        html += f"""
        <div style='margin-bottom:10px; font-size:small;'>
            <img src='/thumb/{video_id}' width='120' height='90'><br>
            <b>{title}</b><br>
            <a href='/video/{video_id}'>View Details</a> |
            <a href='/download?q={quote_plus(video_id)}&fmt=mp3'>Download MP3</a> |
            <a href='/download?q={quote_plus(video_id)}&fmt=mp4'>Download MP4</a>
        </div>
        """

    if results:
        set_last_video(results[0]["id"]["videoId"])

    html += "</body></html>"
    return html


@app.route("/video/<video_id>")
def video_details(video_id):
    title = load_title(video_id, BASE_DIR)
    description_html = f"<h3>{title}</h3><p>Loading description...</p>"

    try:
        url = f"https://www.googleapis.com/youtube/v3/videos"
        params = {
            "key": YOUTUBE_API_KEY,
            "id": video_id,
            "part": "snippet"
        }
        r = requests.get(url, params=params)
        video_data = r.json().get("items", [])[0]

        description = video_data["snippet"]["description"]
        description_html = f"<h3>{title}</h3><p>{description}</p>"

        # Fetch related videos
        related_html = "<h3>Related Videos</h3>"
        related_url = "https://www.googleapis.com/youtube/v3/search"
        related_params = {
            "key": YOUTUBE_API_KEY,
            "relatedToVideoId": video_id,
            "type": "video",
            "part": "snippet",
            "maxResults": 5
        }
        related_r = requests.get(related_url, params=related_params)
        related_results = related_r.json().get("items", [])

        for related_item in related_results:
            related_video_id = related_item["id"]["videoId"]
            related_title = related_item["snippet"]["title"]
            save_title(related_video_id, related_title, BASE_DIR)
            related_html += f"""
            <div style='margin-bottom:10px; font-size:small;'>
                <img src='/thumb/{related_video_id}' width='120' height='90'><br>
                <b>{related_title}</b><br>
                <a href='/video/{related_video_id}'>View Details</a> |
                <a href='/download?q={related_video_id}&fmt=mp3'>Download MP3</a> |
                <a href='/download?q={related_video_id}&fmt=mp4'>Download MP4</a>
            </div>
            """

        # Add the Home link at the end of the page
        return f"""
        <html>
            <head><title>{title}</title></head>
            <body style='font-family:sans-serif;'>
                <a href='/'>Home</a><br><br>
                {description_html}
                {related_html}
                <br><br>
                <a href='/download?q={video_id}&fmt=mp3'>Download MP3</a> |
                <a href='/download?q={video_id}&fmt=mp4'>Download MP4</a>
                <br><br>
                <a href='/'>Back to Home</a>
            </body>
        </html>
        """
    except Exception as e:
        logging.error(f"Error fetching video details: {e}")
        return "Error fetching video details", 500


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
    format = request.args.get("fmt", "mp3")

    # Handle the download process (e.g., streaming or direct file transfer)
    file_path = BASE_DIR / f"{video_id}_{format}.mp3"  # Example path, modify as needed
    if not file_path.exists():
        return "File not found", 404

    return Response(file_path.read_bytes(), mimetype="audio/mp3" if format == "mp3" else "video/mp4")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)