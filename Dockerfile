FROM python:3.10-slim

# Install system dependencies and FFmpeg from apt
RUN apt-get update && apt-get install -y \
    wget curl git make autoconf automake build-essential cmake pkg-config \
    libtool libvorbis-dev libmp3lame-dev libx264-dev zlib1g-dev \
    libass-dev libfreetype6-dev libopus-dev yasm \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install yt-dlp

# Install Flask and other Python dependencies
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

# Optional: Add your app code
WORKDIR /app
COPY . /app

# Expose port for Flask app (8000)
EXPOSE 8000

# Run the Flask app with the built-in server
CMD ["python", "app.py"]