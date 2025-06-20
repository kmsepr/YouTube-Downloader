import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = 'podcasts.db'

# ─── DB INIT ───
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
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── iTunes API SEARCH ───
@app.route('/api/search')
def search_podcasts():
    q = request.args.get('q', '')
    if not q: return jsonify([])
    try:
        r = requests.get("https://itunes.apple.com/search", params={"term": q, "media": "podcast"})
        data = r.json()
        return jsonify([
            {
                "title": item.get("collectionName"),
                "author": item.get("artistName"),
                "cover": item.get("artworkUrl100"),
                "url": item.get("feedUrl")
            } for item in data.get("results", []) if item.get("feedUrl")
        ])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── ADD BY RSS ───
@app.route('/api/add_by_rss', methods=['POST'])
def add_by_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url: return jsonify({'error': 'Missing rss_url'}), 400

    feed = feedparser.parse(rss_url)
    if not feed.entries: return jsonify({'error': 'Invalid RSS'}), 400

    pid = rss_url
    title = feed.feed.get('title', 'Untitled')
    author = feed.feed.get('author', 'Unknown')
    cover = feed.feed.get('image', {}).get('href', '')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
        VALUES (?, ?, ?, ?, ?)
    ''', (pid, title, author, cover, rss_url))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Added', 'title': title})

# ─── GET FAVORITES ───
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─── GET EPISODES ───
@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT rss_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    feed = feedparser.parse(row[0])
    episodes = []
    for item in feed.entries:
        audio = ''
        for enc in item.get('enclosures', []):
            if enc['href'].startswith('http'):
                audio = enc['href']
                break
        if not audio: continue

        episodes.append({
            'title': item.get('title', ''),
            'pub_date': item.get('published', ''),
            'description': item.get('summary', '') or item.get('description', ''),
            'audio_url': audio
        })
    conn.close()
    return jsonify(episodes)

# ─── UI ───
@app.route('/')
def homepage():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320">
<title>🎧 Podcasts</title><style>
body{font-family:sans-serif;font-size:14px;margin:6px}
input,button{width:100%;margin:5px 0;padding:6px}
.card{border:1px solid #ccc;padding:5px;margin-top:8px}
.tiny{font-size:11px;color:#555}
</style></head><body>
<h3>🎧 Podcast App</h3>
<input id="q" placeholder="Search podcasts...">
<button onclick="search()">🔍 Search (iTunes)</button>
<input id="rss" placeholder="Paste RSS feed">
<button onclick="addRss()">➕ Add RSS</button>
<button onclick="loadFavs()">1️⃣ Show Favorites</button>
<div id="results"></div>
<script>
const B=location.origin;
function e(id){return document.getElementById(id);}
async function search(){
  let q=e('q').value;
  let r=await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  let d=await r.json(); let o=e('results'); o.innerHTML='';
  d.forEach(p=>{
    let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${p.title}</b><br><span class='tiny'>${p.author||''}</span><br>
    <span class='tiny'>${p.url}</span><br>
    <button onclick="addFeed('${p.url}')">➕ Add</button>`;
    o.appendChild(div);
  });
}
async function addFeed(url){
  await fetch('/api/add_by_rss',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({rss_url:url})});
  alert('Added!');
}
function addRss(){addFeed(e('rss').value);}
async function loadFavs(){
  let r=await fetch('/api/favorites'); let d=await r.json();
  let o=e('results'); o.innerHTML='';
  d.forEach(p=>{
    let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${p.title}</b><br><span class='tiny'>${p.author}</span><br>
    <button onclick="loadEp('${p.podcast_id}')">▶️ Show Episodes</button>`;
    o.appendChild(div);
  });
}
async function loadEp(pid){
  let r=await fetch(`/api/podcast/${encodeURIComponent(pid)}/episodes`);
  let d=await r.json(); let o=e('results'); o.innerHTML='';
  d.forEach(ep=>{
    let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${ep.title}</b><br><span class='tiny'>${ep.pub_date}</span><br>
    <p>${ep.description}</p><a href="${ep.audio_url}" target="_blank">▶️ Play / Download</a>`;
    o.appendChild(div);
  });
}
</script></body></html>
'''

# ─── MAIN ───
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)