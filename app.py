import os
import logging
import requests
import json
from flask import Flask, request, Response, redirect
from urllib.parse import quote_plus
from pathlib import Path
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

# Define your predefined channels here
CHANNELS = {
    "maheen": "https://youtube.com/@hitchhikingnomaad/videos",
    "entri": "https://youtube.com/@entriapp/videos",
    "zamzam": "https://youtube.com/@zamzamacademy/videos",
    "jrstudio": "https://youtube.com/@jrstudiomalayalam/videos",
    "raftalks": "https://youtube.com/@raftalksmalayalam/videos",
    "parvinder": "https://www.youtube.com/@pravindersheoran/videos",
    "qasimi": "https://www.youtube.com/@quranstudycentremukkam/videos",
    "sharique": "https://youtube.com/@shariquesamsudheen/videos",
    "drali": "https://youtube.com/@draligomaa/videos",
    "yaqeen": "https://youtube.com/@yaqeeninstituteofficial/videos",
    "talent": "https://youtube.com/@talentacademyonline/videos",
    "vijayakumarblathur": "https://youtube.com/@vijayakumarblathur/videos",
    "entridegree": "https://youtube.com/@entridegreelevelexams/videos",
    "suprabhatam": "https://youtube.com/@suprabhaatham2023/videos",
    "bayyinah": "https://youtube.com/@bayyinah/videos",
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "skicr": "https://youtube.com/@skicrtv/videos",
    "dhruvrathee": "https://youtube.com/@dhruvrathee/videos",
    "safari": "https://youtube.com/@safaritvlive/videos",
    "sunnxt": "https://youtube.com/@sunnxtmalayalam/videos",
    "movieworld": "https://youtube.com/@movieworldmalayalammovies/videos",
    "comedy": "https://youtube.com/@malayalamcomedyscene5334/videos",
    "studyiq": "https://youtube.com/@studyiqiasenglish/videos",
}

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

def get_latest_video(channel_url):
    channel_id = channel_url.split('@')[-1].split('/')[0]
    url = f"https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "channelId": channel_id,
        "order": "date",
        "part": "snippet",
        "maxResults": 1
    }
    response = requests.get(url, params=params)
    data = response.json()

    if "items" in data:
        latest_video = data["items"][0]
        video_id = latest_video["id"]["videoId"]
        title = latest_video["snippet"]["title"]
        thumbnail_url = latest_video["snippet"]["thumbnails"]["high"]["url"]
        return video_id, title, thumbnail_url
    return None, None, None

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

    # Add predefined channels to the homepage with their latest video and thumbnail
    channels_html = "<h3>Predefined Channels</h3>"
    for channel_name, channel_url in CHANNELS.items():
        video_id, title, thumbnail_url = get_latest_video(channel_url)
        if video_id:
            channels_html += f"""
            <div style='margin-bottom:10px; font-size:small;'>
                <b>{channel_name}</b><br>
                <img src='{thumbnail_url}' width='120' height='90'><br>
                <b>{title}</b><br>
                <a href='/download?q={quote_plus(video_id)}&fmt=mp3'>Download MP3</a> |
                <a href='/download?q={quote_plus(video_id)}&fmt=mp4'>Download MP4</a>
            </div>
            """

    return f"<html><body style='font-family:sans-serif;'>{search_html}{cached_html}{channels_html}</body></html>"

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
    </form><br><h3>Search results for '{query}'</h3>
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
    ext = "mp3" if fmt == "mp3" else "mp4"
    filename = f"{video_id}_{title}.{ext}"
    file_path = TMP_DIR / filename

    if not file_path.exists():
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookies_path = "/mnt/data/cookies.txt"
        if not Path(cookies_path).exists():
            return "Cookies file not found", 400

        base_cmd = [
            "yt-dlp", url, "-f", "bestaudio[ext=m4a]+bestaudio/best", "--merge-output-format", ext,
            "--output", str(file_path)
        ]
        subprocess.run(base_cmd, check=True)

    return Response(file_path.read_bytes(), mimetype=f"audio/{ext}" if ext == "mp3" else f"video/{ext}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)