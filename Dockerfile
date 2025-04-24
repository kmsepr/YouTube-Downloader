FROM python:3.9-slim

WORKDIR /app

COPY . .

# Install dependencies and build FFmpeg with AMR support
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    wget \
    yasm \
    libopencore-amrnb-dev \
    libopencore-amrwb-dev \
    ffmpeg \
 && pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8000

CMD ["flask", "run"]