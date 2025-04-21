FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget curl git make autoconf automake build-essential cmake pkg-config \
    libtool libvorbis-dev libmp3lame-dev libx264-dev libfdk-aac-dev zlib1g-dev \
    libass-dev libfreetype6-dev libopus-dev yasm \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp flask

# Compile FFmpeg with 3GP support (H.264 + AAC)
WORKDIR /opt
RUN git clone https://github.com/FFmpeg/FFmpeg.git ffmpeg && \
    cd ffmpeg && \
    ./configure \
        --enable-gpl \
        --enable-libx264 \
        --enable-libmp3lame \
        --enable-libfdk-aac \
        --enable-nonfree \
        --disable-debug \
        --enable-small \
        --enable-pic \
        --disable-doc \
        --disable-ffplay \
        --disable-ffprobe \
        --disable-devices \
        --disable-avdevice \
        --disable-postproc \
        --disable-network \
        --prefix=/usr/local && \
    make -j$(nproc) && make install && \
    cd .. && rm -rf ffmpeg

# Add app code
WORKDIR /app
COPY . .

# Port
EXPOSE 8000

# Run the app
CMD ["python", "app.py"]