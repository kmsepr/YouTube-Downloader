# Use a Python 3.9 slim base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy all files from the current directory to the container's /app directory
COPY . .

# Install dependencies, including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \  # Install FFmpeg for video and audio processing
    && pip install --no-cache-dir -r requirements.txt \  # Install Python dependencies
    && apt-get clean \  # Clean up apt cache to reduce image size
    && rm -rf /var/lib/apt/lists/*  # Remove package list files

# Expose port 8000 for the Flask application
EXPOSE 8000

# Set environment variables for Flask application
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0  # Make the app accessible on all interfaces
ENV FLASK_RUN_PORT=8000  # Set the Flask app to run on port 8000

# Start the Flask application when the container is run
CMD ["flask", "run"]