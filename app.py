from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import feedparser
import requests

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
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320"><title>Podcast</title><style>
body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666} audio{width:100%; margin-top:5px}
.help{background:#f2f2f2;padding:5px;font-size:12px;color:#444;margin-bottom:6px}
</style></head><body><h3>🎧 Podcast</h3>
<div class="help">
📱 Keypad Help:<br>
1 = Favorites<br>
2 = Previous Episode<br>
4 = ⏪ Seek 15s / long press 60s<br>
6 = ⏩ Seek 30s / long press 60s<br>
8 = Next Episode
</div>
<input id="q" placeholder="Search..."><button onclick="search()">🔍 Search</button>
<button onclick="showFavs()">⭐ My Favorites</button>
<div id="results"></div>
<div id="playerBox" style="display:none">
  <div class="card">
    <b id="epTitle"></b><br><span class="tiny" id="epDate"></span><br>
    <audio id="player" controls></audio><br>
    <p id="epDesc" style="margin-top:6px"></p>
    <a id="downloadBtn" href="#" download style="display:inline-block;margin:5px 0">📥 Download MP3</a><br>
    <button onclick="prevEp()">⏮️</button>
    <button onclick="seek(-15)">⏪ 15s</button>
    <button onclick="togglePlay()">⏯️</button>
    <button onclick="seek(30)">⏩ 30s</button>
    <button onclick="nextEp()">⏭️</button>
  </div>
</div>
<script>
const B = location.origin;
function e(id){return document.getElementById(id);}

let keyDownTime = {};
document.addEventListener('keydown', ev => {
  const k = ev.key;
  keyDownTime[k] = Date.now();
});

document.addEventListener('keyup', ev => {
  const k = ev.key;
  const heldTime = Date.now() - (keyDownTime[k] || 0);

  if (k === '1') showFavs();
  else if (k === '2') prevEp();
  else if (k === '8') nextEp();
  else if (k === '4') seek(heldTime > 600 ? -60 : -15);
  else if (k === '6') seek(heldTime > 600 ? 60 : 30);
else if (k === '5') togglePlay();

  delete keyDownTime[k];
});

async function search(){
  let q = e('q').value;
  let r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  let d = await r.json();
  let o = e('results');
  o.innerHTML = '';
  d.forEach(p => {
    if (!p.feedUrl) return;
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${p.collectionName}</b><br><span class='tiny'>${p.artistName}</span><br>
    <button onclick="previewFeed('${p.feedUrl}')">📻 Episodes</button>`;
    o.appendChild(div);
  });
}

async function previewFeed(url){
  e('results').innerHTML = '⏳ Fetching latest episode...';
  let r = await fetch('/api/episodes_from_rss', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rss_url: url})
  });
  let d = await r.json();
  if (d.length) showPlayer(d, true);
  else e('results').innerHTML = '❌ No episodes found.';
}

let favOffset = 0;
async function showFavs(){ favOffset = 0; loadFavPage(true); }

async function loadFavPage(reset){
  let r = await fetch(`/api/favorites?offset=${favOffset}`);
  let d = await r.json();
  let o = e('results');
  if (reset) o.innerHTML = '';
  d.forEach(p => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${p.title}</b><br><span class='tiny'>${p.author}</span><br>
    <button onclick="loadEp('${p.podcast_id}')">📻 Latest Episode</button>`;
    o.appendChild(div);
  });
  if (d.length === 5) {
    let btn = document.createElement('button');
    btn.innerText = '⏬ More';
    btn.onclick = () => { favOffset += 5; loadFavPage(false); };
    o.appendChild(btn);
  }
}

let currentId = '', currentList = [], currentIndex = 0;
async function loadEp(id){
  currentId = id; currentIndex = 0;
  e('results').innerHTML = '⏳ Loading latest...';
  await fetch(`/api/mark_played/${encodeURIComponent(id)}`, { method: 'POST' });
  let r = await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes?offset=0`);
  let d = await r.json();
  if (d.length) showPlayer(d, true);
  else e('results').innerHTML = '❌ No episodes found.';
}

function showPlayer(data, reset){
  currentList = data;
  currentIndex = 0;
  showEpisode(currentList[currentIndex]);
  e('playerBox').style.display = 'block';
  e('results').innerHTML = '';
}

function showEpisode(ep){
  e('epTitle').innerText = ep.title;
  e('epDate').innerText = ep.pub_date;
  e('epDesc').innerText = ep.description || '';
  e('player').src = ep.audio_url;
  e('downloadBtn').href = ep.audio_url;
  e('player').play();
}

function prevEp(){
  if (currentIndex > 0) {
    currentIndex--;
    showEpisode(currentList[currentIndex]);
  }
}

function nextEp(){
  if (currentIndex < currentList.length - 1) {
    currentIndex++;
    showEpisode(currentList[currentIndex]);
  }
}

function togglePlay(){
  let p = e('player');
  if (p.paused) p.play(); else p.pause();
}

function seek(seconds) {
  let p = e('player');
  p.currentTime = Math.max(0, p.currentTime + seconds);
}
</script></body></html>
'''

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
        "https://muslimcentral.com/audio/hamza-yusuf/feed/",
        "https://feeds.megaphone.fm/THGU4956605070",
        "https://feeds.buzzsprout.com/2050847.rss",
        "https://muslimcentral.com/audio/the-deen-show/feed/",
        "https://feeds.buzzsprout.com/1194665.rss",
        "https://www.spreaker.com/show/5085297/episodes/feed"
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
    return jsonify(rows)

@app.route('/api/mark_played/<path:pid>', methods=['POST'])
def mark_played(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE podcasts SET last_played = CURRENT_TIMESTAMP WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Marked as played'})



@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    try:
        res = requests.get(f'https://itunes.apple.com/search?media=podcast&term={query}')
        return jsonify(res.json().get('results', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 9
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_date DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]

    if rows:
        conn.close()
        return jsonify(rows)

    # If no cached episodes, fetch from RSS
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