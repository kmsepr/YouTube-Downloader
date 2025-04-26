import os
import threading
import time
import shutil
import re
from flask import Flask, request, send_file, render_template_string
from yt_dlp import YoutubeDL
from googleapiclient.discovery import build

app = Flask(__name__)

# Hardcoded YouTube channel IDs (replace with your actual channel IDs)
CHANNELS = ['UCLz0R5eHg5Yeo5JThWtfZ8Q', 'UCOhHO2ICt0ti9KAh-QHvttQ']  # Add your actual channels here
CACHE_ROOT = 'cache'
IP_ISOLATION = True

# Templates
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>YouTube MP3 & MP4 Stream</title></head>
<body>
<h1>YouTube Channel Cache</h1>
{% for channel, files in data.items() %}
<h2>{{ channel }}</h2>
<ul>
{% for file in files %}
<li>
  <b>{{ file['title'] }}</b> ({{ file['date'] }})<br>
  <a href="/stream/{{ channel }}/{{ file['filename'] }}">MP3</a> |
  <a href="/stream/{{ channel }}/{{ file['filename'].replace('.mp3', '.mp4') }}">MP4</a>
</li>
{% endfor %}
</ul>
{% endfor %}
</body>
</html>
"""

def get_user_cache_dir():
    if IP_ISOLATION:
        return os.path.join(CACHE_ROOT, request.remote_addr.replace('.', '_'))
    return CACHE_ROOT

def sanitize_filename(name):
    return re.sub(r'[^\w\-\.]', '_', name)

def fetch_latest_videos(channel):
    youtube = build('youtube', 'v3', developerKey=os.environ.get('YOUTUBE_API_KEY'))
    request = youtube.search().list(part='snippet', channelId=channel, maxResults=3, order='date')
    response = request.execute()
    videos = []
    for item in response['items']:
        if item['id']['kind'] == 'youtube#video':
            title = item['snippet']['title']
            date = item['snippet']['publishedAt'].split('T')[0]
            video_id = item['id']['videoId']
            videos.append({'id': video_id, 'title': title, 'date': date})
    return videos

def download_media(video_id, title, cache_dir):
    safe_title = sanitize_filename(title)
    mp3_path = os.path.join(cache_dir, f'{safe_title}.mp3')
    mp4_path = os.path.join(cache_dir, f'{safe_title}.mp4')

    if not os.path.exists(mp3_path):
        ydl_opts_mp3 = {
            'format': 'bestaudio',
            'outtmpl': mp3_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',
            }],
            'quiet': True
        }
        with YoutubeDL(ydl_opts_mp3) as ydl:
            ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

    if not os.path.exists(mp4_path):
        ydl_opts_mp4 = {
            'format': '18',
            'outtmpl': mp4_path,
            'quiet': True
        }
        with YoutubeDL(ydl_opts_mp4) as ydl:
            ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

def cleanup_old_files(cache_dir):
    files = sorted(
        [f for f in os.listdir(cache_dir) if f.endswith('.mp3')],
        key=lambda x: os.path.getmtime(os.path.join(cache_dir, x)),
        reverse=True
    )
    for old in files[3:]:
        base = old.rsplit('.', 1)[0]
        try:
            os.remove(os.path.join(cache_dir, f'{base}.mp3'))
            os.remove(os.path.join(cache_dir, f'{base}.mp4'))
        except FileNotFoundError:
            continue

def background_cache():
    while True:
        for channel in CHANNELS:
            channel_id = channel.strip()
            for root, dirs, _ in os.walk(CACHE_ROOT):
                if IP_ISOLATION and not dirs:
                    continue
                cache_dir = os.path.join(root, channel_id)
                os.makedirs(cache_dir, exist_ok=True)
                videos = fetch_latest_videos(channel_id)
                for vid in videos:
                    download_media(vid['id'], vid['title'], cache_dir)
                cleanup_old_files(cache_dir)
        time.sleep(3600)

@app.route('/')
def index():
    data = {}
    user_dir = get_user_cache_dir()
    for channel in CHANNELS:
        channel_id = channel.strip()
        cache_dir = os.path.join(user_dir, channel_id)
        os.makedirs(cache_dir, exist_ok=True)
        files = []
        for file in sorted(os.listdir(cache_dir)):
            if file.endswith('.mp3'):
                base = file[:-4]
                date = "Unknown"
                files.append({'filename': file, 'title': base, 'date': date})
        data[channel_id] = files
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/stream/<channel>/<filename>')
def stream_file(channel, filename):
    cache_dir = os.path.join(get_user_cache_dir(), channel)
    file_path = os.path.join(cache_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=False)
    return 'File not found', 404

@app.route('/search')
def search():
    query = request.args.get('q')
    if not query:
        return 'Missing query', 400
    youtube = build('youtube', 'v3', developerKey=os.environ.get('YOUTUBE_API_KEY'))
    req = youtube.search().list(q=query, part='snippet', type='video', maxResults=5)
    res = req.execute()
    output = "<h1>Search Results</h1><ul>"
    for item in res['items']:
        vid = item['id']['videoId']
        title = item['snippet']['title']
        output += f'<li>{title} - <a href="/download/{vid}">Download</a></li>'
    return output + "</ul>"

@app.route('/download/<video_id>')
def download_from_search(video_id):
    title = f'video_{video_id}'
    cache_dir = get_user_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    download_media(video_id, title, cache_dir)
    return f"Downloaded: <a href='/stream/{video_id}/{title}.mp3'>MP3</a> | <a href='/stream/{video_id}/{title}.mp4'>MP4</a>"

if __name__ == '__main__':
    threading.Thread(target=background_cache, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)