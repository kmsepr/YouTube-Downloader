# Use an official Ubuntu image as the base image
FROM ubuntu:20.04

# Set environment variables to non-interactive to avoid prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Update and install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    libfdk-aac-dev \
    libopencore-amrnb-dev \
    libopencore-amrwb-dev \
    libx264-dev \
    yasm \
    nasm \
    git \
    autoconf \
    automake \
    libtool \
    python3 \
    python3-pip \
    python3-venv \
    && apt-get clean

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
        --enable-version3 \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/ffmpeg.tar.gz /usr/src/ffmpeg-4.4.5

# Install Flask and other Python dependencies
RUN pip3 install flask yt-dlp

# Set working directory for your Flask app
WORKDIR /app

# Copy your Flask app into the container
COPY app.py /app

# Expose port 8000 for the Flask app
EXPOSE 8000

# Set the command to run the Flask app
CMD ["python3", "app.py"]