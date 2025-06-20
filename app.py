import os
import sqlite3
import requests
import feedparser
import xml.etree.ElementTree as ET
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔒 Persistent DB path
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ────── DB SETUP ──────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT UNIQUE,
        title TEXT,
        author TEXT,
        cover_url TEXT,
        rss_url TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT,
        episode_id TEXT UNIQUE,
        title TEXT,
        description TEXT,
        audio_url TEXT,
        pub_date TEXT,
        pub_timestamp INTEGER,
        duration INTEGER,
        FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
    )''')
    conn.commit()
    conn.close()

init_db()

# ────── Add Podcast by RSS ──────
@app.route('/api/add_by_rss', methods=['POST'])
def add_by_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url:
        return jsonify({'error': 'Missing rss_url'}), 400

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        return jsonify({'error': 'Invalid RSS'}), 400

    podcast_id = rss_url
    title = feed.feed.get('title', 'Untitled')
    author = feed.feed.get('author', 'Unknown')
    image = feed.feed.get('image', {}).get('href', '')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
                 VALUES (?, ?, ?, ?, ?)''', (podcast_id, title, author, image, rss_url))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Added from RSS', 'title': title})

# ────── Get Saved Favorites ──────
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ────── Get Podcast Episodes ──────
@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 5
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_timestamp DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    if rows:
        conn.close()
        return jsonify(rows)

    c.execute('SELECT rss_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    feed = feedparser.parse(row[0])
    entries = sorted(feed.entries, key=lambda e: e.get('published_parsed', time.gmtime(0)), reverse=True)
    all_eps = []
    for item in entries:
        eid = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
        audio = ''
        for enc in item.get('enclosures', []):
            if enc['href'].startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue

        title = item.get('title', '')
        desc = item.get('summary', '') or item.get('description', '')
        pub_date = item.get('published', '')
        pub_parsed = item.get('published_parsed')
        pub_ts = int(time.mktime(pub_parsed)) if pub_parsed else 0

        c.execute('''INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, pub_timestamp, duration)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (pid, eid, title, desc, audio, pub_date, pub_ts, 0))
        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'duration': 0
        })

    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

# ────── Delete Podcast ──────
@app.route('/api/delete_podcast/<path:pid>', methods=['DELETE'])
def delete_podcast(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (pid,))
    c.execute('DELETE FROM podcasts WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# ────── OPML Import ──────
@app.route('/api/import_opml', methods=['POST'])
def import_opml():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file uploaded'}), 400
    try:
        tree = ET.parse(file)
        root = tree.getroot()
        count = 0
        for outline in root.iter('outline'):
            rss = outline.attrib.get('xmlUrl')
            if rss:
                requests.post('http://localhost:3000/api/add_by_rss', json={'rss_url': rss})
                count += 1
        return jsonify({'message': f'Imported {count} feeds'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ────── iTunes Search API ──────
@app.route('/api/itunes_search')
def itunes_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    r = requests.get('https://itunes.apple.com/search', params={'term': q, 'media': 'podcast', 'limit': 20})
    data = r.json()
    results = []
    for item in data.get('results', []):
        results.append({
            'title': item.get('collectionName'),
            'author': item.get('artistName'),
            'rss': item.get('feedUrl'),
            'cover': item.get('artworkUrl100')
        })
    return jsonify(results)

# ────── Frontend UI ──────
@app.route('/')
def homepage():
    with open("frontend.html") as f:
        return f.read()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)