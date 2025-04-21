FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget curl git make autoconf automake build-essential cmake pkg-config \
    libtool libvorbis-dev libmp3lame-dev libx264-dev zlib1g-dev \
    libass-dev libfreetype6-dev libopus-dev yasm \
    && rm -rf /var/lib/apt/lists/*

# Install ffmpeg dependencies and build libfdk-aac from source
RUN wget https://github.com/mstorsjo/fdk-aac/archive/v2.0.2.tar.gz \
    && tar -xvzf v2.0.2.tar.gz \
    && cd fdk-aac-2.0.2 \
    && autoreconf -fiv \
    && ./configure --enable-shared \
    && make -j$(nproc) \
    && make install \
    && cd .. \
    && rm -rf fdk-aac-2.0.2 v2.0.2.tar.gz

# Install FFmpeg from source with x264 (H.264) and AAC support
RUN wget https://ffmpeg.org/releases/ffmpeg-5.1.tar.bz2 \
    && tar -xjf ffmpeg-5.1.tar.bz2 \
    && cd ffmpeg-5.1 \
    && ./configure --enable-gpl --enable-libfdk-aac --enable-libx264 --enable-nonfree --enable-pic \
    && make -j$(nproc) \
    && make install \
    && rm -rf /ffmpeg-5.1

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

# Install gunicorn for production deployment
RUN pip install gunicorn

# Use gunicorn to run the Flask app in production mode
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]