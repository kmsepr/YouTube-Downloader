import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ─── DB INIT ─────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts (
        podcast_id TEXT PRIMARY KEY, title TEXT, author TEXT, rss_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, podcast_id TEXT, title TEXT,
        description TEXT, pub_date TEXT, audio_url TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ─── Search (iTunes API) ────────────────
@app.route('/api/search')
def search():
    q = request.args.get('q', '')
    r = requests.get('https://itunes.apple.com/search',
                     params={'media': 'podcast', 'term': q})
    results = r.json().get('results', [])
    out = []
    for item in results:
        url = item.get('feedUrl')
        if url:
            out.append({
                'title': item.get('collectionName'),
                'author': item.get('artistName'),
                'url': url
            })
    return jsonify(out)

# ─── Add RSS ─────────────────────────────
@app.route('/api/add_by_rss', methods=['POST'])
def add_by_rss():
    data = request.get_json()
    rss_url = data.get('rss_url', '').strip()
    if not rss_url:
        return jsonify({'error': 'Missing RSS URL'}), 400

    feed = feedparser.parse(rss_url)
    title = feed.feed.get('title', 'Untitled')
    author = feed.feed.get('author', 'Unknown')
    podcast_id = rss_url  # use RSS URL as ID

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('REPLACE INTO podcasts (podcast_id, title, author, rss_url) VALUES (?, ?, ?, ?)',
              (podcast_id, title, author, rss_url))
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (podcast_id,))
    for entry in feed.entries[:30]:  # limit to 30
        c.execute('INSERT INTO episodes (podcast_id, title, description, pub_date, audio_url) VALUES (?, ?, ?, ?, ?)', (
            podcast_id,
            entry.get('title', ''),
            entry.get('description', ''),
            entry.get('published', ''),
            entry.get('enclosures')[0].get('href') if entry.get('enclosures') else ''
        ))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Added'})

# ─── Favorites ───────────────────────────
@app.route('/api/favorites')
def favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT podcast_id, title, author FROM podcasts ORDER BY rowid DESC')
    favs = [{'podcast_id': row[0], 'title': row[1], 'author': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(favs)

# ─── Episodes by Podcast ────────────────
@app.route('/api/podcast/<path:pid>/episodes')
def episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT title, description, pub_date, audio_url FROM episodes WHERE podcast_id = ? ORDER BY id DESC', (pid,))
    eps = [{'title': row[0], 'description': row[1], 'pub_date': row[2], 'audio_url': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(eps)

# ─── Delete Podcast ─────────────────────
@app.route('/api/delete/<path:pid>', methods=['DELETE'])
def delete_podcast(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM podcasts WHERE podcast_id = ?', (pid,))
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# ─── Main ───────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)