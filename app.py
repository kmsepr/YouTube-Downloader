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
    if LAST_VIDEO_FILE.exists():
        return LAST_VIDEO_FILE.read_text().strip()
    return None

def get_unique_video_ids():
    files = list(BASE_DIR.glob("*.*"))
    unique_ids = {}
    for f in files:
        vid = f.stem.split("_")[0]
        unique_ids.setdefault(vid, []).append(f)
    return unique_ids

def download_thumbnail(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                         headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok:
            path = THUMB_DIR / f"{video_id}.jpg"
            path.write_bytes(r.content)
            return path
    except Exception as e:
        logging.warning(f"Thumbnail error: {e}")
    return None

# Routes
@app.route("/")
def index():
    search_form = """..."""  # your existing HTML
    content = "<h3>Cached Files</h3>"
    for vid, files in get_unique_video_ids().items():
        title = load_title(vid)
        content += f"<div>...<b>{title}</b><br>"
        for ext, label in [("mp3","MP3"),("mp4","MP4"),("3gp","3GP")]:
            if any(str(f).endswith(f".{ext}") for f in files):
                content += f"<a href='/download?q={vid}&fmt={ext}'>Download {label}</a> | "
        content += f"<a href='/remove?q={vid}' style='color:red;'>Remove</a></div>"
    last = get_last_video()
    if last:
        # related videos logic ...
        pass
    return f"<html>...{search_form}{content}</body></html>"

@app.route("/search")
def search():
    q = request.args.get("q","").strip()
    if not q: return redirect("/")
    r = requests.get("https://www.googleapis.com/youtube/v3/search",
                     params={"key":YOUTUBE_API_KEY,"q":q,"part":"snippet","type":"video","maxResults":15})
    # build HTML with results, links to /details and downloads
    # call save_title(...) and set_last_video(...)
    return "<html>...</html>"

@app.route("/thumb/<video_id>")
def thumbnail_proxy(video_id):
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                         headers={"User-Agent": FIXED_USER_AGENT}, timeout=5)
        if r.ok: return Response(r.content, mimetype="image/jpeg")
    except:
        pass
    return "Not found",404

@app.route("/details/<video_id>")
def details(video_id):
    # fetch snippet/stats, related videos...
    # include 3GP link similar to MP3/MP4
    return "<html>...</html>"

@app.route("/download")
def download():
    vid = request.args.get("q")
    fmt = request.args.get("fmt","mp3")
    if not vid: return "Missing video ID",400
    return redirect(url_for("ready", q=vid, fmt=fmt))

@app.route("/ready")
def ready():
    vid = request.args.get("q")
    fmt = request.args.get("fmt","mp3")
    title = safe_filename(load_title(vid))
    ext = fmt if fmt in ["mp3","mp4","3gp"] else "mp3"
    final = BASE_DIR / f"{vid}_{title}.{ext}"
    temp = TEMP_DIR / f"{vid}_{title}.{ext}"
    if not final.exists():
        url = f"https://www.youtube.com/watch?v={vid}"
        cook = "/mnt/data/cookies.txt"
        if not Path(cook).exists(): return "Cookies missing",400
        # metadata fetch
        out = subprocess.check_output(["yt-dlp","--print","%(title)s|||%(uploader)s|||%(upload_date)s",
                                       "--cookies",cook,url], text=True).strip()
        parts = out.split("|||")
        video_title, uploader, upload_date = parts
        album_date = datetime.strptime(upload_date, "%Y%m%d").strftime("%B %Y")
        base = ["yt-dlp","--output",str(temp.with_suffix(".%(ext)s")),
                "--user-agent",FIXED_USER_AGENT,"--cookies",cook,url]
        if fmt=="mp3":
            cmd = base + ["-f","bestaudio","--extract-audio","--audio-format","mp3","--postprocessor-args","-ar 22050 -ac 1 -b:a 24k"]
        elif fmt=="mp4":
            cmd = base + ["-f","best[ext=mp4]","--recode-video","mp4","--postprocessor-args","-vf scale=320:240 -r 15 -b:v 384k -b:a 12k"]
        else:  # 3gp
            cmd = base + ["-f","18","--recode-video","3gp","--postprocessor-args","-vf scale=320:240 -r 15 -b:v 256k -b:a 32k"]
        subprocess.run(cmd, check=True)
        if temp.exists():
            if fmt=="mp3":
                thumb = download_thumbnail(vid)
                if thumb:
                    inter = BASE_DIR / f"{title}.mp3"
                    subprocess.run(["ffmpeg","-y","-i",str(temp),"-i",str(thumb),
                                    "-map","0","-map","1","-c","copy","-id3v2_version","3",
                                    "-metadata",f"title={video_title}","-metadata",f"artist={uploader}",
                                    "-metadata",f"album={album_date}","-metadata:s:v","title=Album cover",
                                    "-metadata:s:v","comment=Cover (front)",str(inter)], check=True)
                    shutil.move(str(inter), str(final))
                else:
                    subprocess.run(["ffmpeg","-y","-i",str(temp),
                                    "-metadata",f"title={video_title}","-metadata",f"artist={uploader}",
                                    "-metadata",f"album={album_date}",str(final)], check=True)
                temp.unlink()
            else:
                shutil.move(str(temp), str(final))
    mime = {"mp3":"audio/mpeg","mp4":"video/mp4","3gp":"video/3gpp"}[fmt]
    return Response(final.open("rb"), mimetype=mime)

@app.route("/remove")
def remove():
    vid = request.args.get("q")
    if not vid: return redirect("/")
    for f in BASE_DIR.glob(f"{vid}_*.*"):
        try: f.unlink()
        except logging.warning(f"Remove failed: {f}")
    t = THUMB_DIR / f"{vid}.jpg"
    if t.exists(): t.unlink()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)