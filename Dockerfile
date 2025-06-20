# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount point for persistent data
VOLUME ["/mnt/data"]

# Set environment variable to avoid buffering logs
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "app.py"]