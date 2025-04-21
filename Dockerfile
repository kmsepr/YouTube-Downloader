FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget curl git make autoconf automake build-essential cmake pkg-config \
    libtool libvorbis-dev libmp3lame-dev libx264-dev zlib1g-dev \
    libass-dev libfreetype6-dev libopus-dev yasm \
    libfdk-aac-dev \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install yt-dlp

# Install FFmpeg from source with x264 (H.264) and AAC support
RUN wget https://ffmpeg.org/releases/ffmpeg-5.1.tar.bz2 \
    && tar -xjf ffmpeg-5.1.tar.bz2 \
    && cd ffmpeg-5.1 \
    && ./configure --enable-gpl --enable-libfdk-aac --enable-libx264 --enable-nonfree --enable-pic \
    && make -j$(nproc) \
    && make install \
    && rm -rf /ffmpeg-5.1

# Optional: Add your app code
WORKDIR /app
COPY . /app

# Expose port for Flask app (8000)
EXPOSE 8000

# Run Flask app (adjust as needed)
CMD ["python", "app.py"]