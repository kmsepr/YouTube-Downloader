import os
import sqlite3
import requests
import feedparser
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ─── Database Initialization ─────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id TEXT UNIQUE,
            title TEXT,
            author TEXT,
            cover_url TEXT,
            rss_url TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
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
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── Add Podcast by RSS ─────────────────────────────
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
    c.execute('''
        INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
        VALUES (?, ?, ?, ?, ?)
    ''', (podcast_id, title, author, image, rss_url))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Added from RSS', 'title': title})

# ─── List All Saved Podcasts ─────────────────────────────
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─── Fetch Episodes (cached + parse if needed) ─────────────────────────────
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

    # Not found in DB, fetch from RSS
    c.execute('SELECT rss_url, cover_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    rss_url, cover_url = row
    feed = feedparser.parse(rss_url)
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

        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, pub_timestamp, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pid, eid, title, desc, audio, pub_date, pub_ts, 0))

        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'cover': cover_url,
            'duration': 0
        })

    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

# ─── Delete Podcast ─────────────────────────────
@app.route('/api/delete_podcast/<path:pid>', methods=['DELETE'])
def delete_podcast(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (pid,))
    c.execute('DELETE FROM podcasts WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# ─── Search from iTunes API ─────────────────────────────
@app.route('/api/search_podcasts')
def search_podcasts():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])

    r = requests.get("https://itunes.apple.com/search", params={"term": q, "media": "podcast"})
    data = r.json()
    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("collectionName"),
            "author": item.get("artistName"),
            "cover": item.get("artworkUrl100"),
            "rss": item.get("feedUrl")
        })
    return jsonify(results)

# ─── Static Pages ─────────────────────────────
@app.route('/')
def homepage():
    return '<meta http-equiv="refresh" content="0; url=/home">'

@app.route('/home')
def home_ui():
    return open("/app/home.html").read()

@app.route('/favorites')
def favorites_page():
    return open("/app/favorites.html").read()

@app.route('/episodes/<path:pid>')
def episodes_page(pid):
    cover = request.args.get('cover', '')
    return open("/app/episodes.html").read().replace('{{PID}}', pid).replace('{{COVER}}', cover)

# ─── Run Server ─────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)