import os
import time
import logging
from googleapiclient.discovery import build
from unidecode import unidecode
import yt_dlp
from flask import Flask, render_template, send_from_directory
from threading import Thread

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'your-api-key-here')  # Replace with your YouTube API key
CHANNELS = ["channel_1_handle", "channel_2_handle", "channel_3_handle"]  # Replace with actual YouTube channel usernames

# Flask App Setup
app = Flask(__name__)

# Initialize YouTube API client
def get_youtube_service():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Function to fetch latest videos from YouTube channels
def get_latest_videos_from_channel(channel_handle):
    youtube = get_youtube_service()
    request = youtube.search().list(
        part="snippet",
        channelId=channel_handle,
        maxResults=5,
        order="date"
    )
    response = request.execute()
    return response["items"]

# Function to download and convert videos
def download_and_convert_video(url, download_dir):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{download_dir}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',  # Convert video to MP4
        }],
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Function to clean up any special characters in the video title
def clean_video_title(title):
    return unidecode(title)  # Convert to ASCII, remove any special characters

# Route to serve MP4 files
@app.route('/video/<filename>')
def serve_video(filename):
    return send_from_directory(os.path.join(os.getcwd(), 'downloads'), filename)

# Function to fetch and serve the latest videos from multiple channels
def fetch_and_serve_videos():
    while True:
        for channel in CHANNELS:
            logger.info(f"Fetching latest videos from {channel}...")
            try:
                videos = get_latest_videos_from_channel(channel)
                download_dir = os.path.join(os.getcwd(), 'downloads', unidecode(channel))
                os.makedirs(download_dir, exist_ok=True)

                for video in videos:
                    title = clean_video_title(video['snippet']['title'])
                    url = f"https://www.youtube.com/watch?v={video['id']['videoId']}"
                    logger.info(f"Downloading video: {title}")
                    download_and_convert_video(url, download_dir)

                time.sleep(10)  # Delay before checking the next channel
            except Exception as e:
                logger.error(f"Error fetching videos for channel {channel}: {e}")
                time.sleep(30)  # Retry in case of failure

# Run the background task to download videos
def run_background_task():
    thread = Thread(target=fetch_and_serve_videos)
    thread.daemon = True
    thread.start()

# Start the Flask app
if __name__ == '__main__':
    run_background_task()  # Start fetching and downloading videos in the background
    app.run(host='0.0.0.0', port=8000)