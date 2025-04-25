import os
import re
import threading
import shutil
import subprocess
from flask import Flask, request, send_file, render_template_string
from urllib.parse import urlencode
import requests
import logging

app = Flask(__name__)
API_KEY = os.getenv("YOUTUBE_API_KEY")
DATA_DIR = "/mnt/data/ytmp3"
os.makedirs(DATA_DIR, exist_ok=True)

YDL_OPTIONS = {
    "format": "best[ext=mp4]",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "cookiefile": "/mnt/data/cookies.txt"
}

HTML_TEMPLATE = """
<!doctype html>
<title>YouTube Search</title>
<h2>Search YouTube</h2>
<form action="/search">
  <input name="q" value="{{ query }}" placeholder="Search term" size="40">
  <button type="submit">Search</button>
</form>
<ul>
{% for vid in videos %}
  <li>
    <img src="/thumb/{{ vid.id }}" width="120">
    <b>{{ vid.title }}</b><br>
    <a href="/download?q={{ vid.id }}&title={{ vid.title }}&fmt=mp3">MP3</a> |
    <a href="/download?q={{ vid.id }}&title={{ vid.title }}&fmt=3gp">3GP</a>
  </li>
{% endfor %}
</ul>
"""

def safe_filename(name):
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)

def get_ip_folder():
    ip = request.remote_addr.replace('.', '_')
    path = os.path.join(DATA_DIR, ip)
    os.makedirs(path, exist_ok=True)
    return path

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, query="", videos=[])

@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q:
        return render_template_string(HTML_TEMPLATE, query="", videos=[])
    params = {
        "key": API_KEY,
        "q": q,
        "part": "snippet",
        "type": "video",
        "maxResults": 5,
    }
    url = f"https://www.googleapis.com/youtube/v3/search?{urlencode(params)}"
    res = requests.get(url).json()
    videos = []
    for item in res.get("items", []):
        vid = item["id"]["videoId"]
        title = item["snippet"]["title"]
        videos.append({"id": vid, "title": title})
    return render_template_string(HTML_TEMPLATE, query=q, videos=videos)

@app.route("/thumb/<video_id>")
def thumb(video_id):
    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    r = requests.get(url, stream=True)
    return r.content, 200, {'Content-Type': 'image/jpeg'}

@app.route("/download")
def download():
    video_id = request.args.get("q")
    title = request.args.get("title", "video")
    fmt = request.args.get("fmt", "mp3")
    folder = get_ip_folder()
    safe_title = safe_filename(title)
    output_base = os.path.join(folder, f"{video_id}_{safe_title}")
    final_file = f"{output_base}.{fmt}"
    if os.path.exists(final_file):
        return send_file(final_file)
    
    try:
        tmp_file = f"{output_base}.temp.mp4"
        cmd = [
            "yt-dlp", "-f", YDL_OPTIONS["format"], "-o", tmp_file,
            "--user-agent", YDL_OPTIONS["user_agent"],
            "--cookies", YDL_OPTIONS["cookiefile"],
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        subprocess.check_call(cmd)

        if fmt == "mp3":
            out_file = f"{output_base}.mp3"
            subprocess.check_call(["ffmpeg", "-i", tmp_file, "-vn", "-b:a", "64k", out_file])
        else:
            out_file = f"{output_base}.3gp"
            subprocess.check_call([
                "ffmpeg", "-i", tmp_file, "-vf", "scale=320:240", "-r", "15",
                "-c:v", "mpeg4", "-b:v", "384k", "-c:a", "aac", "-b:a", "12k", out_file
            ])
        os.remove(tmp_file)
        return send_file(out_file)
    except Exception as e:
        logging.exception(f"{fmt.upper()} conversion failed")
        return f"{fmt.upper()} conversion failed: {e}", 500

def cleanup_thread():
    while True:
        for folder in os.listdir(DATA_DIR):
            full = os.path.join(DATA_DIR, folder)
            if os.path.isdir(full):
                shutil.rmtree(full, ignore_errors=True)
        time.sleep(3600)

if __name__ == "__main__":
    threading.Thread(target=cleanup_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)