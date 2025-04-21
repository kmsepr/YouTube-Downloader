FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    pip install --no-cache-dir flask yt-dlp && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Create TMP_DIR directory for MP4 files
RUN mkdir -p /tmp/ytmp4

# Expose Flask port
EXPOSE 8000

# Start Flask app
CMD ["python", "app.py"]
