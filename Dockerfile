FROM python:3.11-slim

# Enable contrib and non-free for libfdk-aac and similar
RUN sed -i 's/^Components: main$/& contrib non-free/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    procps gcc build-essential make yasm \
    libfdk-aac-dev libssl-dev libopencore-amrwb-dev \
    wget curl git python3-dev libass-dev libfreetype6-dev \
 && rm -rf /var/lib/apt/lists/*

# Download and build FFmpeg 4.4.5 with required codec support
RUN wget https://ffmpeg.org/releases/ffmpeg-4.4.5.tar.gz -O /tmp/ffmpeg.tar.gz \
 && tar -xzf /tmp/ffmpeg.tar.gz -C /usr/src \
 && cd /usr/src/ffmpeg-4.4.5 \
 && ./configure \
    --enable-gpl \
    --enable-nonfree \
    --enable-libfdk-aac \
    --enable-libopencore-amrwb \
    --enable-openssl \
 && make -j$(nproc) \
 && make install \
 && rm -rf /tmp/ffmpeg.tar.gz /usr/src/ffmpeg-4.4.5

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Create persistent data directory (e.g., for caching)
RUN mkdir -p /mnt/data/ytmp3

# Expose Flask port
EXPOSE 8000

# Run the Flask app
CMD ["python", "app.py"]