import os
import subprocess
from flask import Flask, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)

# Function to download the video (WebM format)
def download_video(url, output_path, cookies_path):
    ydl_opts = {
        'format': 'bestaudio/best',  # Get the best quality audio and video
        'outtmpl': output_path,
        'cookies': cookies_path,  # Path to the cookies.txt file for authentication
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise Exception(f"Error downloading video: {str(e)}")

# Function to convert WebM to MP4
def convert_webm_to_mp4(webm_path, mp4_path):
    try:
        # Run FFmpeg to convert WebM to MP4 with Symbian-compatible settings
        subprocess.run([
            "ffmpeg", "-y", "-i", webm_path,
            "-vf", "scale=320:240", "-r", "15",
            "-b:v", "384k", "-b:a", "12k", "-ac", "1",
            "-c:v", "libx264", "-c:a", "aac",
            mp4_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error during video conversion: {str(e)}")

# Health check route
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route('/download', methods=['GET'])
def download_video_file():
    video_url = request.args.get('url')
    cookies_path = '/mnt/data/cookies.txt'  # Path to cookies.txt file

    if not video_url:
        return "No URL provided", 400

    # Define file paths for download and conversion
    webm_path = '/tmp/video.webm'
    mp4_path = '/tmp/video.mp4'

    try:
        # Step 1: Download the video (WebM format)
        download_video(video_url, webm_path, cookies_path)

        # Step 2: Convert WebM to MP4
        convert_webm_to_mp4(webm_path, mp4_path)

        # Step 3: Serve the MP4 file
        return send_file(mp4_path, as_attachment=True)

    except Exception as e:
        # Log and return detailed error message
        return f"Error: {str(e)}", 500

@app.route('/')
def home():
    return "Flask app is running!"
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)