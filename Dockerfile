FROM python:3.11-slim

# Install required build tools and dependencies
RUN apt-get update && apt-get install -y \
    wget build-essential pkg-config \
    libx264-dev libx265-dev libvpx-dev libfdk-aac-dev libmp3lame-dev libopus-dev \
    libvorbis-dev libass-dev libfreetype6-dev libssl-dev yasm libtool \
    zlib1g-dev git curl ffmpeg \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
 && chmod +x /usr/local/bin/yt-dlp

# Optional: build FFmpeg from source with 3gp-compatible codecs (H.263, AAC)
# Comment out if system ffmpeg is sufficient
RUN git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg && \
    cd ffmpeg && \
    ./configure --prefix=/usr/local \
        --disable-debug \
        --enable-gpl \
        --enable-libx264 \
        --enable-libmp3lame \
        --enable-libfdk-aac \
        --enable-libopus \
        --enable-libvorbis \
        --enable-libass \
        --enable-libfreetype \
        --enable-nonfree \
        --enable-encoder=h263 \
        --enable-decoder=h263 \
        --enable-muxer=3gp \
        --enable-demuxer=3gp \
        --enable-encoder=aac \
        --enable-decoder=aac \
        --enable-small && \
    make -j$(nproc) && make install && cd .. && rm -rf ffmpeg

# Copy app files
COPY . .

# Expose port
EXPOSE 8000

# Run the Flask app
CMD ["python", "app.py"]