import os
import sqlite3
import requests
import feedparser
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

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

@app.route('/')
def homepage():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Podcast Player</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; padding: 1rem; max-width: 600px; margin: auto; }
            input, button { font-size: 1rem; padding: 0.5rem; margin: 0.2rem; }
            .card { border: 1px solid #ccc; padding: 1rem; margin: 0.5rem 0; border-radius: 8px; }
            audio { width: 100%; margin-top: 0.5rem; }
        </style>
    </head>
    <body>
        <h2>🎧 Podcast Player</h2>
        <input id="searchBox" placeholder="Search podcasts..." />
        <button onclick="search()">Search</button>
        <h3>Results</h3>
        <div id="results"></div>
        <h3>Favorites</h3>
        <button onclick="loadFavorites()">Refresh</button>
        <div id="favorites"></div>

        <script>
        function search() {
            const query = document.getElementById('searchBox').value;
            fetch('/api/search?q=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(data => {
                    const results = document.getElementById('results');
                    results.innerHTML = '';
                    data.forEach(p => {
                        const el = document.createElement('div');
                        el.className = 'card';
                        el.innerHTML = `
                            <b>${p.collectionName}</b><br/>
                            ${p.artistName}<br/>
                            <button onclick="loadEpisodes('${p.feedUrl}')">Play Latest</button>
                        `;
                        results.appendChild(el);
                    });
                });
        }

        function loadFavorites() {
            fetch('/api/favorites')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('favorites');
                    container.innerHTML = '';
                    data.forEach(p => {
                        const el = document.createElement('div');
                        el.className = 'card';
                        el.innerHTML = `
                            <b>${p.title}</b><br/>
                            ${p.author}<br/>
                            <button onclick="loadEpisodes('${p.podcast_id}')">Play</button>
                        `;
                        container.appendChild(el);
                    });
                });
        }

        function loadEpisodes(pid) {
            fetch(`/api/podcast/${encodeURIComponent(pid)}/episodes`)
                .then(r => r.json())
                .then(data => {
                    if (data.length) {
                        const ep = data[0];
                        const player = document.createElement('div');
                        player.className = 'card';
                        player.innerHTML = `
                            <h4>${ep.title}</h4>
                            <audio controls src="${ep.audio_url}"></audio>
                            <p>${ep.description}</p>
                        `;
                        document.body.appendChild(player);
                        fetch('/api/mark_played/' + encodeURIComponent(pid), { method: 'POST' });
                    } else {
                        alert('No episode found!');
                    }
                });
        }

        loadFavorites();
        </script>
    </body>
    </html>
    """

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
    for item in feed.entries[:10]:
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
            'audio_url': audio
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
        "https://muslimcentral.com/audio/hamza-yusuf/feed/",
        "https://feeds.megaphone.fm/THGU4956605070",
        "https://feeds.blubrry.com/feeds/2931440.xml",
        "https://anchor.fm/s/39ae8bf0/podcast/rss",
        "https://feeds.buzzsprout.com/2050847.rss",
        "https://anchor.fm/s/601dfb4/podcast/rss",
        "https://muslimcentral.com/audio/the-deen-show/feed/",
        "https://feeds.buzzsprout.com/1194665.rss",
        "https://www.spreaker.com/show/5085297/episodes/feed",
        "https://anchor.fm/s/46be7940/podcast/rss"
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
    placeholders = ','.join('?' for _ in default_feeds)
    c.execute(f'''
        SELECT * FROM podcasts
        WHERE podcast_id IN ({placeholders})
        ORDER BY last_played DESC
        LIMIT ? OFFSET ?
    ''', (*default_feeds, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()

    # Prefetch episodes
    for p in rows:
        threading.Thread(target=lambda url=f"{request.host_url}api/podcast/{p['podcast_id']}/episodes": requests.get(url)).start()

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
    limit = 1
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_date DESC LIMIT ? OFFSET ?', (pid, limit, offset))
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
    all_eps = []
    for item in feed.entries:
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
    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)