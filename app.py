import os
import sqlite3
import requests
import feedparser
import time
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ── DB INIT ──
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

# ── API: Add podcast by RSS ──
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

# ── API: Favorites ──
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ── API: Episodes ──
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

    # If not cached, fetch from RSS
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

# ── API: Delete podcast ──
@app.route('/api/delete_podcast/<path:pid>', methods=['DELETE'])
def delete_podcast(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (pid,))
    c.execute('DELETE FROM podcasts WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# ── API: iTunes search ──
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

# ── HTML Pages ──
@app.route('/')
def homepage():
    return Response(f"""
    <h1>Podcast App</h1>
    <ul>
        <li><a href="/home">Home</a></li>
        <li><a href="/favorites">Favorites</a></li>
    </ul>
    """, mimetype="text/html")

@app.route('/home')
def home_ui():
    return Response("""
    <h2>Add Podcast by RSS</h2>
    <form action="/api/add_by_rss" method="post" onsubmit="submitForm(event)">
        <input type="text" name="rss_url" placeholder="Enter RSS URL" required>
        <button type="submit">Add</button>
    </form>
    <script>
        function submitForm(e) {{
            e.preventDefault();
            fetch('/api/add_by_rss', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ rss_url: e.target.rss_url.value }})
            }}).then(r => r.json()).then(data => alert(data.message || data.error));
        }}
    </script>
    """, mimetype="text/html")

@app.route('/favorites')
def favorites_page():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT title, podcast_id FROM podcasts')
    items = c.fetchall()
    conn.close()
    html = "<h2>Favorites</h2><ul>"
    for title, pid in items:
        html += f'<li><a href="/episodes/{pid}">{title}</a></li>'
    html += "</ul>"
    return Response(html, mimetype="text/html")

@app.route('/episodes/<path:pid>')
def episodes_page(pid):
    html = f"<h2>Episodes</h2><ul>"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT title, audio_url FROM episodes WHERE podcast_id=? ORDER BY pub_timestamp DESC LIMIT 10', (pid,))
    for title, audio_url in c.fetchall():
        html += f'<li>{title}<br><a href="{audio_url}">▶️ Play</a></li>'
    conn.close()
    html += "</ul>"
    return Response(html, mimetype="text/html")

# ── Run App ──
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)