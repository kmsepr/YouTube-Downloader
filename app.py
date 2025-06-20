import os
import sqlite3
import requests
import feedparser
import hashlib
from flask import Flask, request, jsonify
from dateutil import parser as date_parser

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
    c.execute('CREATE INDEX IF NOT EXISTS idx_episode_sort ON episodes(podcast_id, pub_date DESC)')
    conn.commit()
    conn.close()

init_db()

# ─── SEARCH PODCASTS (iTunes API) ────────
@app.route('/api/search')
def search_podcasts():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])

    try:
        res = requests.get('https://itunes.apple.com/search', params={
            'term': q,
            'media': 'podcast',
            'limit': 25
        })

        data = res.json()
        results = []
        for p in data.get('results', []):
            if 'feedUrl' in p:
                results.append({
                    'title': p.get('collectionName'),
                    'author': p.get('artistName'),
                    'rss': p.get('feedUrl'),
                    'cover': p.get('artworkUrl100')
                })

        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── ADD BY RSS URL (with hashed ID) ─────
@app.route('/api/add_by_rss', methods=['POST'])
def add_by_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url:
        return jsonify({'error': 'Missing rss_url'}), 400

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        return jsonify({'error': 'Invalid RSS'}), 400

    podcast_id = hashlib.md5(rss_url.encode()).hexdigest()
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

# ─── GET FAVORITE PODCASTS ───────────────
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─── GET PAGINATED EPISODES ─────────────
@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 5

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_date DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    if rows:
        conn.close()
        return jsonify(rows)

    # Fetch & save if not in DB
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
            if enc['href'].startswith('http') and ('.mp3' in enc['href'] or 'audio' in enc.get('type', '')):
                audio = enc['href']
                break
        if not audio:
            continue
        title = item.get('title', '')
        desc = item.get('summary', '') or item.get('description', '')
        raw_date = item.get('published', '') or item.get('pubDate', '')
        try:
            pub_date = date_parser.parse(raw_date).isoformat()
        except:
            pub_date = '1970-01-01T00:00:00'

        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            pid, eid, title, desc, audio, pub_date, 0
        ))
        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'duration': 0
        })
    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

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
div.className='card';div.innerHTML=`<b>${p.title}</b><br><span class="tiny">${p.rss}</span><br>
<button onclick="addFeed('${p.rss}')">➕ Add</button>`;o.appendChild(div);})}
async function addFeed(url){await fetch('/api/add_by_rss',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({rss_url:url})});alert('Added!');}
async function addRss(){addFeed(e('rss').value)}
async function loadFavs(){let r=await fetch('/api/favorites');let d=await r.json();let o=e('results');
o.innerHTML='';d.forEach(p=>{let div=document.createElement('div');div.className='card';
div.innerHTML=`<b>${p.title}</b><br><span class="tiny">${p.author}</span><br>
<button onclick="loadEp('${p.podcast_id}')">📻 Episodes</button>`;o.appendChild(div);})}
let epOffset=0,currentId='';
async function loadEp(id){currentId=id;epOffset=0;
e('results').innerHTML='⏳ Loading...';let r=await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes?offset=0`);
let d=await r.json();showEpisodes(d,true);}
async function loadMore(){epOffset+=5;
let r=await fetch(`/api/podcast/${encodeURIComponent(currentId)}/episodes?offset=${epOffset}`);
let d=await r.json();showEpisodes(d,false);}
function showEpisodes(data,reset){let o=e('results');
if(reset) o.innerHTML='';data.forEach(ep=>{let div=document.createElement('div');
div.className='card';div.innerHTML=`<b>${ep.title}</b><br><span class="tiny">${ep.pub_date}</span><br>
<p>${ep.description||''}</p><a href="${ep.audio_url}" target="_blank">▶️ Play / Download</a>`;o.appendChild(div);});
if(data.length===5){let btn=document.createElement('button');btn.innerText='⏬ Load More';
btn.onclick=loadMore;o.appendChild(btn);}}
</script></body></html>
'''

# ─── START SERVER ────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)