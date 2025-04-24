FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget curl git build-essential python3-dev \
    libx264-dev libx265-dev libvpx-dev \
    libmp3lame-dev libopus-dev libass-dev \
    libfreetype6-dev libvorbis-dev yasm pkg-config \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Create persistent tmp dir (Koyeb uses /mnt/data)
RUN mkdir -p /mnt/data/ytmp3

# Expose Flask port
EXPOSE 8000

# Run the app
CMD ["python", "app.py"]