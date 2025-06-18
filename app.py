import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = 'podcasts.db'

# ─── DB INIT ─────────────────────────────
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
            duration INTEGER,
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── SEARCH ─────────────────────────────
@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    try:
        res = requests.get(f'https://api.podcastindex.org/api/1.0/search/byterm?q={query}',
                           headers={'User-Agent': 'PodApp', 'X-Auth-Date': '0', 'X-Auth-Key': '000'})
        return jsonify(res.json().get('feeds', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── ADD PODCAST BY RSS ─────────────────
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

# ─── LIST FAVORITES ─────────────────────
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─── GET EPISODES ───────────────────────
@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ?', (pid,))
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
    new_eps = []
    for item in feed.entries:
        eid = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
        audio = ''
        for enc in item.get('enclosures', []):
            if enc['href'].startswith('http') and enc['href'].endswith('.mp3'):
                audio = enc['href']
                break
        if not audio:
            continue
        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            pid, eid, item.get('title', ''), item.get('summary', ''),
            audio, item.get('published', ''), 0
        ))
        new_eps.append({
            'episode_id': eid,
            'title': item.get('title', ''),
            'description': item.get('summary', ''),
            'audio_url': audio,
            'pub_date': item.get('published', ''),
            'duration': 0
        })
    conn.commit()
    conn.close()
    return jsonify(new_eps)

# ─── UI HOMEPAGE ────────────────────────
@app.route('/')
def homepage():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320">
<title>Podcast</title>
<style>body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666}</style></head>
<body>
<h3>🎧 Podcast</h3>
<input id="q" placeholder="Search..."><button onclick="search()">🔍 Search</button>
<input id="rss" placeholder="Paste RSS feed"><button onclick="addRss()">➕ Add by RSS</button>
<button onclick="loadFavs()">⭐ Favorites</button>
<div id="results"></div>
<script>
const B = location.origin;
function e(id){return document.getElementById(id)}
async function search(){let q=e('q').value;
let r=await fetch(`/api/search?q=${encodeURIComponent(q)}`);let d=await r.json();
let o=e('results');o.innerHTML='';d.forEach(p=>{let div=document.createElement('div');
div.className='card';div.innerHTML=`<b>${p.title}</b><br><span class="tiny">${p.url}</span><br>
<button onclick="addFeed('${p.url}')">➕ Add</button>`;o.appendChild(div);})}
async function addFeed(url){await fetch('/api/add_by_rss',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({rss_url:url})});alert('Added!');}
async function addRss(){addFeed(e('rss').value)}
async function loadFavs(){let r=await fetch('/api/favorites');let d=await r.json();let o=e('results');
o.innerHTML='';d.forEach(p=>{let div=document.createElement('div');div.className='card';
div.innerHTML=`<b>${p.title}</b><br><span class="tiny">${p.author}</span><br>
<button onclick="loadEp('${p.podcast_id}')">📻 Episodes</button>`;o.appendChild(div);})}
async function loadEp(id){let r=await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes`);
let d=await r.json();let o=e('results');o.innerHTML='';
d.slice(0,5).forEach(ep=>{let div=document.createElement('div');div.className='card';
div.innerHTML=`<b>${ep.title}</b><br><span class="tiny">${ep.pub_date}</span><br>
<a href="${ep.audio_url}" target="_blank">▶️ Play / Download</a>`;o.appendChild(div);})}
</script></body></html>
'''

# ─── START SERVER ───────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)