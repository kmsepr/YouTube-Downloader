import os
import sqlite3
import requests
import feedparser
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
            duration TEXT,
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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
            if enc['href'].startswith('http'):
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('SELECT podcast_id FROM podcasts')
    existing = {row[0] for row in c.fetchall()}

    default_feeds = [
        "https://anchor.fm/s/c1cd3f68/podcast/rss",
        "https://anchor.fm/s/1c3ac138/podcast/rss",
        "https://anchor.fm/s/28ef3620/podcast/rss",
        "https://anchor.fm/s/f662ec14/podcast/rss",
        "https://muslimcentral.com/audio/hamza-yusuf/feed/",
        "https://feeds.megaphone.fm/THGU4956605070",
        "https://feeds.blubrry.com/feeds/2931440.xml",
        "https://anchor.fm/s/39ae8bf0/podcast/rss",
        "https://www.omnycontent.com/d/playlist/4bb33704-615b-4054-aae9-ace500fd4197/1773a28d-33f6-4f5b-90fe-af5100be356d/dbe0f12b-7cf1-4d2e-9a7c-af5100bf1545/podcast.rss",
        "https://feeds.buzzsprout.com/2050847.rss",
        "https://anchor.fm/s/601dfb4/podcast/rss",
        "https://muslimcentral.com/audio/the-deen-show/feed/",
        "https://feeds.buzzsprout.com/1194665.rss",
        "https://feeds.soundcloud.com/users/soundcloud:users:774008737/sounds.rss",
        "https://www.spreaker.com/show/5085297/episodes/feed",
        "https://anchor.fm/s/46be7940/podcast/rss"
    ]

    for rss_url in default_feeds:
        if rss_url in existing:
            continue
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            podcast_id = rss_url
            title = feed.feed.get('title', 'Untitled')
            author = feed.feed.get('author', 'Unknown')
            image = (feed.feed.get('image', {}) or {}).get('href', '') or feed.feed.get('itunes_image', {}).get('href', '')
            c.execute('''
                INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (podcast_id, title, author, image, rss_url))
        except:
            continue
    conn.commit()

    c.execute('SELECT * FROM podcasts ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

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
            if enc['href'].startswith('http'):
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

@app.route('/')
def homepage():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320"><title>Podcast</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666}
</style></head><body>
<h3>🎧 Podcast</h3>
<p style="font-size:12px;color:#666">🔢 Press 1 to view Favorites</p>
<input id="q" placeholder="Search..."><button onclick="search()">🔍 Search</button>
<button onclick="showFavs()">⭐ My Favorites</button>
<div id="results"></div>
<script>
const B = location.origin;
function e(id){return document.getElementById(id)}
document.addEventListener('keydown', (ev)=>{if(ev.key==='1') showFavs();});

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
    e('results').innerHTML = '⏳ Fetching episodes...';
    let r = await fetch('/api/episodes_from_rss', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({rss_url: url})
    });
    let d = await r.json();
    showEpisodes(d, true);
}

let favOffset = 0;
async function showFavs(){
    favOffset = 0;
    loadFavPage(true);
}

async function loadFavPage(reset){
    let r = await fetch(`/api/favorites?offset=${favOffset}`);
    let d = await r.json();
    let o = e('results');
    if (reset) o.innerHTML = '';
    d.forEach(p => {
        let div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `<b>${p.title}</b><br><span class='tiny'>${p.author}</span><br><button onclick="loadEp('${p.podcast_id}')">📻 Episodes</button>`;
        o.appendChild(div);
    });
    if (d.length === 5) {
        let btn = document.createElement('button');
        btn.innerText = '⏬ More';
        btn.onclick = () => {
            favOffset += 5;
            loadFavPage(false);
        };
        o.appendChild(btn);
    }
}

let epOffset = 0, currentId = '';
async function loadEp(id){
    currentId = id;
    epOffset = 0;
    e('results').innerHTML = '⏳ Loading...';
    let r = await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes?offset=0`);
    let d = await r.json();
    showEpisodes(d, true);
}

async function loadMore(){
    epOffset += 9;
    let r = await fetch(`/api/podcast/${encodeURIComponent(currentId)}/episodes?offset=${epOffset}`);
    let d = await r.json();
    showEpisodes(d, false);
}

function showEpisodes(data, reset){
    let o = e('results');
    if (reset) o.innerHTML = '';
    data.forEach(ep => {
        let div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `<b>${ep.title}</b><br><span class="tiny">${ep.pub_date}</span><br><p>${ep.description || ''}</p><a href="${ep.audio_url}" target="_blank">▶️ Play / Download</a>`;
        o.appendChild(div);
    });
    if (data.length === 9) {
        let btn = document.createElement('button');
        btn.innerText = '⏬ Load More';
        btn.onclick = loadMore;
        o.appendChild(btn);
    }
}
</script>
</body></html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)