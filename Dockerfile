FROM python:3.9-slim

WORKDIR /app

COPY . .

# Install dependencies and clean up unnecessary files
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopencore-amrnb0 \
    libopencore-amrwb0 \
    libopencore-amrnb-dev \
    libopencore-amrwb-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8000

CMD ["flask", "run"]