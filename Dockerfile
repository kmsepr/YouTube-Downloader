FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget build-essential pkg-config \
    libx264-dev libx265-dev libvpx-dev \
    libmp3lame-dev libopus-dev \
    libvorbis-dev libass-dev libfreetype6-dev \
    libssl-dev yasm libtool \
    zlib1g-dev git curl ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements first to leverage Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Set environment variables (if needed)
ENV PYTHONUNBUFFERED=1

# Expose port if needed (e.g., 5000 for Flask)
EXPOSE 5000

# Command to run your Flask app
CMD ["python", "app.py"]