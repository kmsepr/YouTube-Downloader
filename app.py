import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ───── DB INIT ─────
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
            rss_url TEXT,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            duration TEXT,
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ───── API ROUTES ─────

@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    try:
        res = requests.get(f'https://itunes.apple.com/search?media=podcast&term={query}')
        return jsonify(res.json().get('results', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/episodes_from_rss', methods=['POST'])
def episodes_from_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url:
        return jsonify([])
    feed = feedparser.parse(rss_url)
    results = []
    for item in feed.entries[:3]:
        audio = ''
        for enc in item.get('enclosures', []):
            if enc.get('href', '').startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue
        results.append({
            'title': item.get('title', ''),
            'description': item.get('summary', '') or item.get('description', ''),
            'pub_date': item.get('published', ''),
            'audio_url': audio,
            'cover_url': (feed.feed.get('image', {}) or {}).get('href', '') or
                         feed.feed.get('itunes_image', {}).get('href', '')
        })
    return jsonify(results)

@app.route('/api/favorites')
def get_favorites():
    offset = int(request.args.get('offset', 0))
    limit = 5
    default_feeds = [
        "https://anchor.fm/s/c1cd3f68/podcast/rss",
        "https://anchor.fm/s/1c3ac138/podcast/rss",
        "https://anchor.fm/s/28ef3620/podcast/rss",
        "https://anchor.fm/s/f662ec14/podcast/rss",
        "https://muslimcentral.com/audio/hamza-yusuf/feed/"
    ]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for rss_url in default_feeds:
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            podcast_id = rss_url
            title = feed.feed.get('title', 'Untitled')
            author = feed.feed.get('author', 'Unknown')
            image = (feed.feed.get('image', {}) or {}).get('href', '') or \
                    feed.feed.get('itunes_image', {}).get('href', '')
            c.execute('''
                INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (podcast_id, title, author, image, rss_url))
        except:
            continue
    conn.commit()
    c.execute('SELECT * FROM podcasts WHERE podcast_id IN (%s) ORDER BY last_played DESC LIMIT ? OFFSET ?'
              % ','.join('?' * len(default_feeds)),
              (*default_feeds, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/mark_played/<path:pid>', methods=['POST'])
def mark_played(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE podcasts SET last_played = CURRENT_TIMESTAMP WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Marked as played'})

@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 9
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Return stored episodes
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_date DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    if rows:
        c.execute('SELECT cover_url FROM podcasts WHERE podcast_id = ?', (pid,))
        row = c.fetchone()
        cover_url = row[0] if row else ''
        for ep in rows:
            ep['cover_url'] = cover_url
        conn.close()
        return jsonify(rows)

    # If not found, parse and save
    c.execute('SELECT rss_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    feed = feedparser.parse(row[0])
    all_eps = []
    for item in feed.entries[:3]:
        eid = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
        audio = ''
        for enc in item.get('enclosures', []):
            if enc.get('href', '').startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue
        title = item.get('title', '')
        desc = item.get('summary', '') or item.get('description', '')
        pub_date = item.get('published', '')
        duration = item.get('itunes_duration', '')
        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (pid, eid, title, desc, audio, pub_date, duration))
        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'duration': duration
        })
    c.execute('SELECT cover_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    cover_url = row[0] if row else ''
    for ep in all_eps:
        ep['cover_url'] = cover_url
    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

# ───── HOMEPAGE ─────
@app.route('/')
def homepage():
    html = '''
<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Podcast</title>
<style>
body { font-family: sans-serif; font-size: 14px; margin: 8px }
input, button { width: 100%; padding: 6px; margin: 6px 0 }
.card { border: 1px solid #ccc; padding: 6px; border-radius: 8px; margin: 6px 0 }
.sidebar { position: fixed; left: 0; top: 0; bottom: 0; width: 220px; background: #f0f0f0; overflow-y: auto; padding: 10px }
main { margin-left: 230px }
audio { width: 100%; margin-top: 6px }
</style>
</head><body>
<div class="sidebar">
  <h3>Favourites</h3>
  <div id="favList">Loading...</div>
</div>
<main>
  <h2>Podcast App</h2>
  <input id="search" placeholder="Search podcast">
  <button onclick="search()">Search</button>
  <input id="rss" placeholder="Add RSS feed URL">
  <button onclick="addRSS()">Add Feed</button>
  <div id="results"></div>
</main>
<script>
async function search() {
  let q = document.getElementById('search').value;
  let r = await fetch('/api/search?q=' + encodeURIComponent(q));
  let j = await r.json();
  show(j.map(p => ({title: p.collectionName, pid: p.feedUrl, rss: p.feedUrl})));
}
async function addRSS() {
  let url = document.getElementById('rss').value;
  let r = await fetch('/api/episodes_from_rss', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rss_url: url})
  });
  let j = await r.json();
  show(j.map(p => ({title: p.title, pid: url, rss: url, audio: p.audio_url})));
}
async function loadFavs() {
  let r = await fetch('/api/favorites');
  let j = await r.json();
  let fav = document.getElementById('favList');
  fav.innerHTML = '';
  j.forEach(p => {
    let div = document.createElement('div');
    div.innerHTML = `<b>${p.title}</b>`;
    div.onclick = () => loadEpisodes(p.podcast_id);
    fav.appendChild(div);
  });
}
async function loadEpisodes(pid) {
  await fetch('/api/mark_played/' + encodeURIComponent(pid), {method: 'POST'});
  let r = await fetch('/api/podcast/' + encodeURIComponent(pid) + '/episodes');
  let j = await r.json();
  show(j.map(e => ({title: e.title, pid: pid, audio: e.audio_url})));
}
function show(list) {
  let out = document.getElementById('results');
  out.innerHTML = '';
  list.forEach(item => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${item.title}</b>` + (item.audio ? `<audio controls src="${item.audio}"></audio>` : '');
    out.appendChild(div);
  });
}
loadFavs();
</script>
</body></html>
'''
    return Response(html, mimetype='text/html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)