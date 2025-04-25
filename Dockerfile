# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (e.g., ffmpeg, yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code to the container
COPY . /app

# Set environment variables (ensure YOUTUBE_API_KEY is set in your environment or Docker)
ENV YOUTUBE_API_KEY=your_api_key_here

# Expose port 8000
EXPOSE 8000

# Run the Flask app when the container starts
CMD ["python", "app.py"]