import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# --- DB Setup ---
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

# --- Search iTunes ---
@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    try:
        res = requests.get(f'https://itunes.apple.com/search?media=podcast&term={query}')
        return jsonify(res.json().get('results', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Parse RSS feed and return latest 3 episodes ---
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

# --- Mobile-Friendly Homepage with Cards and Player ---
@app.route('/')
def homepage():
    html = '''
<!DOCTYPE html><html><head>
<meta name="viewport" content="width=320">
<title>Podcasts</title>
<style>
  body { font-family: sans-serif; font-size: 14px; margin: 0; background: #001; color: white; }
  .header { display: flex; justify-content: space-between; padding: 6px; background: #111; }
  .tabs button { background: #222; color: white; border: none; padding: 6px 12px; margin-right: 4px; border-radius: 6px; }
  .tabs .active { background: #4db8ff; }
  .lang { font-size: 18px; margin-right: 10px }
  h2 { margin: 10px; }
  .scroll-row { display: flex; overflow-x: auto; gap: 10px; padding: 0 10px }
  .card { min-width: 100px; flex: none; background: #222; border-radius: 10px; padding: 4px; text-align: center; cursor: pointer; }
  .card img { width: 100%; height: 80px; border-radius: 8px; object-fit: cover }
  .card div { font-size: 12px; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis }

  .player { display: none; flex-direction: column; align-items: center; padding: 8px }
  .player img { width: 100%; max-height: 160px; object-fit: cover; border-radius: 10px }
  .player h3 { margin: 10px 0 4px; font-size: 16px; text-align: center }
  .controls { display: flex; gap: 10px; margin: 10px }
  .controls button { font-size: 18px; padding: 6px 12px; border: none; border-radius: 6px; background: #444; color: white }
  audio { width: 100% }
</style>
</head><body>
<div class="header">
  <div class="tabs">
    <button class="active">Podcasts</button>
    <button onclick="alert('Radio not implemented yet')">Radios</button>
  </div>
  <div class="lang">🇮🇳</div>
</div>

<h2>Popular Podcasts</h2>
<div class="scroll-row" id="popular">
  <div class="card" onclick="loadPodcast('https://feeds.acast.com/public/shows/5f764315818c4b61720b0b19')">
    <img src="https://cdn.thehindu.com/podcasts/podcast-logo.jpg"><div>The Hindu</div>
  </div>
  <div class="card" onclick="loadPodcast('https://feeds.simplecast.com/tOjNXec5')">
    <img src="https://cdn-images-1.listennotes.com/podcasts/the-ranveer-show-TRS-GM1e8NF7vhM-x8bkZ9jOyNb.1400x1400.jpg"><div>Ranveer Show</div>
  </div>
  <div class="card" onclick="loadPodcast('https://feeds.simplecast.com/wjQvY1RS')">
    <img src="https://cdn-images-1.listennotes.com/podcasts/figuring-out-with-raj-shamani-qCHfGZrmP6S-6ms82T6BTrG.1400x1400.jpg"><div>Raj Shamani</div>
  </div>
</div>

<div class="player" id="player">
  <img id="cover" src="">
  <h3 id="title">Title</h3>
  <div class="controls">
    <button onclick="audio.currentTime-=15">⏪</button>
    <button onclick="audio.paused?audio.play():audio.pause()">⏯</button>
    <button onclick="audio.currentTime+=15">⏩</button>
  </div>
  <audio id="audio" controls></audio>
</div>

<script>
let audio = document.getElementById('audio');

function loadPodcast(rss) {
  fetch('/api/episodes_from_rss', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rss_url: rss})
  })
  .then(r => r.json())
  .then(j => {
    if (j.length > 0) {
      document.getElementById('title').textContent = j[0].title;
      document.getElementById('cover').src = j[0].cover_url || '';
      audio.src = j[0].audio_url;
      document.getElementById('player').style.display = 'flex';
      audio.play();
    }
  });
}
</script>

</body></html>
'''
    return Response(html, mimetype='text/html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)