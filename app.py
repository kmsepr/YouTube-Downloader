import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify, Response

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
            category TEXT,
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
    return Response('''<!DOCTYPE html><html><head><meta name="viewport" content="width=320">
<title>Podcasts</title>
<style>
body { background: #0a0a16; color: #fff; font-family: sans-serif; padding: 6px; font-size: 13px }
button, select, input { padding: 6px; margin: 4px 2px; }
.tab { display: inline-block; padding: 5px 10px; border-radius: 6px; background: #222; margin-right: 5px; }
.active { background: #3399ff; color: white }
.grid { display: flex; flex-wrap: wrap; gap: 8px; }
.card { width: 90px; background: #111; border-radius: 10px; overflow: hidden; text-align: center; font-size: 12px; cursor: pointer; }
.card img { width: 90px; height: 90px; object-fit: cover; }
#episodes { margin-top: 10px; }
.ep { margin: 4px 0; padding: 4px; border-bottom: 1px solid #444; }
audio { width: 100%; margin-top: 4px; }
</style></head><body>
<div>
  <span class="tab active">🎧 Podcasts</span>
  <span style="float:right">🇮🇳</span>
</div>
<h2>Popular Podcasts</h2>
<div id="list"></div>
<div id="episodes"></div>
<script>
const list = document.getElementById('list');
const eps = document.getElementById('episodes');
let episodes = [], current = 0;
fetch('/api/favorites')
  .then(r => r.json())
  .then(data => {
    let html = '';
    for (const [cat, pods] of Object.entries(data)) {
      html += `<h3>${cat}</h3><div class="grid">` +
              pods.map(p => `<div class='card' onclick="load('${p.rss_url}', '${p.podcast_id}', '${p.title.replace(/'/g, '')}')">
              <img src='${p.cover_url || 'https://via.placeholder.com/90'}' onerror="this.src='https://via.placeholder.com/90'">
              ${p.title.split(' ').slice(0, 2).join(' ')}
              </div>`).join('') + '</div>';
    }
    list.innerHTML = html;
  });

function load(rss_url, pid, title) {
  fetch('/api/mark_played/' + encodeURIComponent(pid), { method: 'POST' });
  fetch('/api/episodes_from_rss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rss_url })
  })
  .then(r => r.json())
  .then(data => {
    episodes = data;
    current = 0;
    showEpisode(title);
  });
}

function showEpisode(title) {
  if (!episodes.length) return;
  const ep = episodes[current];
  eps.innerHTML = `<h3>${title}</h3>
  <div class='ep'>
    <b>${ep.title}</b><br>
    <audio controls autoplay src='${ep.audio_url}'></audio><br>
    <button onclick="prev()">⏮ Prev</button>
    <button onclick="next()">Next ⏭</button>
  </div>`;
}

function next() {
  if (current < episodes.length - 1) {
    current++;
    showEpisode(document.querySelector('h3')?.textContent || 'Podcast');
  }
}

function prev() {
  if (current > 0) {
    current--;
    showEpisode(document.querySelector('h3')?.textContent || 'Podcast');
  }
}
</script>
</body></html>''', mimetype='text/html')

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
            'cover_url': (feed.feed.get('image', {}) or {}).get('href', '') or feed.feed.get('itunes_image', {}).get('href', '')
        })
    return jsonify(results)

@app.route('/api/favorites')
def get_favorites():
    offset = int(request.args.get('offset', 0))
    limit = 30
    default_feeds = [
        ("https://anchor.fm/s/c1cd3f68/podcast/rss", "Malayalam"),
        ("https://anchor.fm/s/1c3ac138/podcast/rss", "Malayalam"),
        ("https://anchor.fm/s/28ef3620/podcast/rss", "Malayalam"),
        ("https://anchor.fm/s/f662ec14/podcast/rss", "Malayalam"),
        ("https://feeds.blubrry.com/feeds/2931440.xml", "Malayalam"),
        ("https://anchor.fm/s/39ae8bf0/podcast/rss", "Malayalam"),
        ("https://www.omnycontent.com/d/playlist/.../podcast.rss", "Malayalam"),
        ("https://feeds.buzzsprout.com/2050847.rss", "Malayalam"),
        ("https://anchor.fm/s/601dfb4/podcast/rss", "Malayalam"),
        ("https://feeds.soundcloud.com/users/soundcloud:users:774008737/sounds.rss", "Malayalam"),
        ("https://www.spreaker.com/show/5085297/episodes/feed", "Malayalam"),
        ("https://anchor.fm/s/46be7940/podcast/rss", "Malayalam"),
        ("https://muslimcentral.com/audio/hamza-yusuf/feed/", "Islamic"),
        ("https://muslimcentral.com/audio/the-deen-show/feed/", "Islamic"),
        ("https://feeds.buzzsprout.com/1194665.rss", "Islamic"),
        ("https://feeds.megaphone.fm/THGU4956605070", "English")
    ]

    for rss_url, category in default_feeds:
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            podcast_id = rss_url
            title = feed.feed.get('title', 'Untitled')
            author = feed.feed.get('author', 'Unknown')
            image = (feed.feed.get('image', {}) or {}).get('href', '') or feed.feed.get('itunes_image', {}).get('href', '') or 'https://via.placeholder.com/90'

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url, category)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (podcast_id, title, author, image, rss_url, category))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error parsing {rss_url}: {e}")
            continue

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts ORDER BY last_played DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()

    grouped = {}
    for row in rows:
        cat = row.get('category', 'Other')
        grouped.setdefault(cat, []).append(row)
    return jsonify(grouped)

@app.route('/api/mark_played/<path:pid>', methods=['POST'])
def mark_played(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE podcasts SET last_played = CURRENT_TIMESTAMP WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Marked as played'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)