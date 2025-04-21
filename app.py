from flask import Flask, Response, request
import subprocess
import json
import os
import logging
import time
import threading
from pathlib import Path
import random

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Interval settings
REFRESH_INTERVAL = 1800       # 30 minutes
RECHECK_INTERVAL = 3600       # 60 minutes
CLEANUP_INTERVAL = 1800       # 30 minutes
EXPIRE_AGE = 10800            # 3 hours

CHANNELS = {
    "comedy": "https://youtube.com/@malayalamcomedyscene5334/videos",
    "studyiq": "https://youtube.com/@studyiqiasenglish/videos",
    "vijayakumarblathur": "https://youtube.com/@vijayakumarblathur/videos",
    "entridegree": "https://youtube.com/@entridegreelevelexams/videos",
}

VIDEO_CACHE = {name: {"url": None, "last_checked": 0, "avatar": ""} for name in CHANNELS}
TMP_DIR = Path("/tmp/ytmp4")
TMP_DIR.mkdir(exist_ok=True)

def cleanup_old_files():
    while True:
        now = time.time()
        for f in TMP_DIR.glob("*.mp4"):
            if now - f.stat().st_mtime > EXPIRE_AGE:
                try:
                    f.unlink()
                    logging.info(f"Deleted old file: {f}")
                except Exception as e:
                    logging.warning(f"Could not delete {f}: {e}")
        time.sleep(CLEANUP_INTERVAL)

def update_video_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            video_url, avatar_url = fetch_latest_video_url(name, url)
            if video_url:
                VIDEO_CACHE[name]["url"] = video_url
                VIDEO_CACHE[name]["last_checked"] = time.time()
                VIDEO_CACHE[name]["avatar"] = avatar_url
                download_and_convert(name, video_url)
            time.sleep(random.randint(5, 10))
        time.sleep(REFRESH_INTERVAL)

def auto_download_mp4s():
    while True:
        for name, data in VIDEO_CACHE.items():
            video_url = data.get("url")
            if video_url:
                mp4_path = TMP_DIR / f"{name}.mp4"
                if not mp4_path.exists() or time.time() - mp4_path.stat().st_mtime > RECHECK_INTERVAL:
                    logging.info(f"Pre-downloading {name}")
                    download_and_convert(name, video_url)
            time.sleep(random.randint(5, 10))
        time.sleep(RECHECK_INTERVAL)

def fetch_latest_video_url(name, channel_url):
    try:
        result = subprocess.run([
            "yt-dlp",
            "--dump-single-json",
            "--playlist-end", "1",
            "--cookies", "/mnt/data/cookies.txt",
            "--user-agent", "Mozilla/5.0",
            channel_url
        ], capture_output=True, text=True, check=True)

        data = json.loads(result.stdout)
        video_id = data["entries"][0]["id"]
        uploader_thumbnail = data.get("uploader_thumbnail", "")
        return f"https://www.youtube.com/watch?v={video_id}", uploader_thumbnail
    except Exception as e:
        logging.error(f"Error fetching video from {channel_url}: {e}")
        return None, None

def download_and_convert(channel, video_url):
    final_path = TMP_DIR / f"{channel}.mp4"
    if final_path.exists():
        return final_path
    if not video_url:
        logging.warning(f"Skipping download for {channel} because video URL is not available.")
        return None

    try:
        subprocess.run([
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            "--output", str(TMP_DIR / f"{channel}.%(ext)s"),
            "--cookies", "/mnt/data/cookies.txt",
            "--user-agent", "Mozilla/5.0",
            "--postprocessor-args", "ffmpeg:-vf scale=320:240 -r 15 -b:v 384k -c:v libx264 -preset veryfast -ac 1 -ar 22050 -b:a 12k",
            video_url
        ], check=True)
        return final_path if final_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel}: {e}")
        partial = final_path.with_suffix(".mp4.part")
        if partial.exists():
            partial.unlink()
        return None

@app.route("/<channel>.mp4")
def stream_mp4(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404

    video_url = VIDEO_CACHE[channel].get("url") or fetch_latest_video_url(channel, CHANNELS[channel])[0]
    if not video_url:
        return "Unable to fetch video", 500

    VIDEO_CACHE[channel]["url"] = video_url
    VIDEO_CACHE[channel]["last_checked"] = time.time()

    mp4_path = download_and_convert(channel, video_url)
    if not mp4_path or not mp4_path.exists():
        return "Error preparing stream", 500

    file_size = os.path.getsize(mp4_path)
    range_header = request.headers.get('Range', None)
    headers = {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
    }

    if range_header:
        try:
            range_value = range_header.strip().split("=")[1]
            byte1, byte2 = range_value.split("-")
            byte1 = int(byte1)
            byte2 = int(byte2) if byte2 else file_size - 1
        except Exception as e:
            return f"Invalid Range header: {e}", 400

        length = byte2 - byte1 + 1
        with open(mp4_path, 'rb') as f:
            f.seek(byte1)
            chunk = f.read(length)

        headers.update({
            'Content-Range': f'bytes {byte1}-{byte2}/{file_size}',
            'Content-Length': str(length)
        })

        return Response(chunk, status=206, headers=headers)

    with open(mp4_path, 'rb') as f:
        data = f.read()
    headers['Content-Length'] = str(file_size)
    return Response(data, headers=headers)

@app.route("/")
def index():
    html = "<h3>Available Streams</h3><ul>"

    def get_mtime(channel):
        f = TMP_DIR / f"{channel}.mp4"
        return f.stat().st_mtime if f.exists() else 0

    for channel in sorted(CHANNELS, key=get_mtime, reverse=True):
        mp4_path = TMP_DIR / f"{channel}.mp4"
        if not mp4_path.exists():
            continue
        avatar = VIDEO_CACHE[channel].get("avatar", "")
        if not avatar:
            avatar = "https://via.placeholder.com/30?text=YT"
        
        # Embed the thumbnail image in the list
        avatar_img = f'<img src="{avatar}" loading="lazy" style="height:30px; vertical-align:middle; margin-right:10px;">'
        
        # Build the HTML list item
        html += f'<li style="margin-bottom:10px;">{avatar_img}<a href="/{channel}.mp4">{channel}</a> <small>({time.ctime(mp4_path.stat().st_mtime)})</small></li>'
    html += "</ul>"
    return html

# Start background threads
threading.Thread(target=update_video_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_old_files, daemon=True).start()
threading.Thread(target=auto_download_mp4s, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)