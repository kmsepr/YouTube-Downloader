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

REFRESH_INTERVAL = 900
RECHECK_INTERVAL = 1800
CLEANUP_INTERVAL = 1800
EXPIRE_AGE = 10800

CHANNELS = {
    "qasimi": "https://www.youtube.com/@quranstudycentremukkam/videos",
    "sharique": "https://www.youtube.com/@shariquesamsudheen/videos",
    "drali": "https://www.youtube.com/@draligomaa/videos",
    "yaqeen": "https://www.youtube.com/@yaqeeninstituteofficial/videos"
}

VIDEO_CACHE = {name: {"url": None, "last_checked": 0} for name in CHANNELS}
TMP_DIR = Path("/tmp/yt3gp")
TMP_DIR.mkdir(exist_ok=True)

def cleanup_old_files():
    while True:
        now = time.time()
        for f in TMP_DIR.glob("*.3gp"):
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
            video_url = fetch_latest_video_url(url)
            if video_url:
                VIDEO_CACHE[name]["url"] = video_url
                VIDEO_CACHE[name]["last_checked"] = time.time()
                download_and_convert(name, video_url)
            time.sleep(random.randint(5, 10))
        time.sleep(REFRESH_INTERVAL)

def auto_download_3gps():
    while True:
        for name, data in VIDEO_CACHE.items():
            video_url = data.get("url")
            if video_url:
                file_path = TMP_DIR / f"{name}.3gp"
                if not file_path.exists() or time.time() - file_path.stat().st_mtime > RECHECK_INTERVAL:
                    logging.info(f"Pre-downloading {name}")
                    download_and_convert(name, video_url)
            time.sleep(random.randint(5, 10))
        time.sleep(RECHECK_INTERVAL)

def fetch_latest_video_url(channel_url):
    try:
        result = subprocess.run([
            "yt-dlp", "--flat-playlist", "--playlist-end", "1",
            "--dump-single-json", "--cookies", "/mnt/data/cookies.txt", channel_url
        ], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video_id = data["entries"][0]["id"]
        time.sleep(random.randint(5, 10))
        return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        logging.error(f"Error fetching video from {channel_url}: {e}")
        return None

def download_and_convert(channel, video_url):
    final_path = TMP_DIR / f"{channel}.3gp"
    if final_path.exists():
        return final_path

    if not video_url:
        logging.warning(f"Skipping download for {channel} because video URL is not available.")
        return None

    try:
        subprocess.run([
            "yt-dlp",
            "-f", "best[ext=mp4]",
            "--output", str(TMP_DIR / f"{channel}.%(ext)s"),
            "--cookies", "/mnt/data/cookies.txt",
            "--recode-video", "mp4",
            "--postprocessor-args", "ffmpeg:-vf scale=176:144 -r 10 -b:v 96k -b:a 12k -ac 1 -ar 22050 -f 3gp",
            video_url
        ], check=True)

        mp4_file = TMP_DIR / f"{channel}.mp4"
        if mp4_file.exists():
            mp4_file.rename(final_path)

        return final_path if final_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel} to 3gp: {e}")
        return None

@app.route("/<channel>.3gp")
def stream_3gp(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404

    video_url = VIDEO_CACHE[channel].get("url") or fetch_latest_video_url(CHANNELS[channel])
    if not video_url:
        return "Unable to fetch video", 500

    VIDEO_CACHE[channel]["url"] = video_url
    VIDEO_CACHE[channel]["last_checked"] = time.time()

    file_path = download_and_convert(channel, video_url)
    if not file_path or not file_path.exists():
        return "Error preparing stream", 500

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get('Range', None)
    headers = {
        'Content-Type': 'video/3gpp',
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
        with open(file_path, 'rb') as f:
            f.seek(byte1)
            chunk = f.read(length)

        headers.update({
            'Content-Range': f'bytes {byte1}-{byte2}/{file_size}',
            'Content-Length': str(length)
        })

        return Response(chunk, status=206, headers=headers)

    with open(file_path, 'rb') as f:
        data = f.read()
    headers['Content-Length'] = str(file_size)
    return Response(data, headers=headers)

@app.route("/")
def index():
    files = list(TMP_DIR.glob("*.3gp"))
    links = [f'<li><a href="/{f.stem}.3gp">{f.stem}.3gp</a> (created: {time.ctime(f.stat().st_mtime)})</li>' for f in files]
    return f"<h3>Available Streams</h3><ul>{''.join(links)}</ul>"

threading.Thread(target=update_video_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_old_files, daemon=True).start()
threading.Thread(target=auto_download_3gps, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)