import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify, send_from_directory

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
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get('https://itunes.apple.com/search',
                     params={'media': 'podcast', 'term': q},
                     headers=headers)
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
    podcast_id = rss_url

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('REPLACE INTO podcasts (podcast_id, title, author, rss_url) VALUES (?, ?, ?, ?)',
              (podcast_id, title, author, rss_url))
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (podcast_id,))
    for entry in feed.entries[:30]:
        audio = entry.get('enclosures')[0].get('href') if entry.get('enclosures') else ''
        c.execute('INSERT INTO episodes (podcast_id, title, description, pub_date, audio_url) VALUES (?, ?, ?, ?, ?)',
                  (podcast_id, entry.get('title', ''), entry.get('description', ''),
                   entry.get('published', ''), audio))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Added'})

# ─── Favorites ───────────────────────────
@app.route('/api/favorites')
def favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT podcast_id, title FROM podcasts ORDER BY rowid DESC')
    favs = [{'podcast_id': row[0], 'title': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(favs)

# ─── Episodes by Podcast ────────────────
@app.route('/api/podcast/<path:pid>/episodes')
def episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT title, pub_date, audio_url FROM episodes WHERE podcast_id = ? ORDER BY id DESC', (pid,))
    eps = [{'title': row[0], 'pub_date': row[1], 'audio_url': row[2]} for row in c.fetchall()]
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

# ─── Web UI ─────────────────────────────
@app.route('/')
def index():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320">
<title>🎧 Podcasts</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:6px}
input,button{width:100%;margin:5px 0;padding:6px}
.card{border:1px solid #ccc;padding:5px;margin-top:8px}
.tiny{font-size:11px;color:#555}
button{background:#eee;border:1px solid #888;border-radius:4px;cursor:pointer}
</style></head><body>
<h3>🎧 Podcast App</h3>
<input id="q" placeholder="Search podcasts...">
<button onclick="search()">🔍 Search</button>
<input id="rss" placeholder="Paste RSS feed">
<button onclick="addRss()">➕ Add RSS</button>
<button onclick="loadFavourites()">🎯 Show Favourites</button>
<div id="fav-buttons"></div>
<div style="display:flex;gap:5px;margin:5px 0;">
  <button onclick="prevPage()">⬅️ Prev</button>
  <button onclick="nextPage()">➡️ Next</button>
</div>
<div id="results"></div>
<script>
let favs = [], page = 0, pageSize = 9;
function e(id){return document.getElementById(id);}
async function search(){
  e('results').innerHTML = 'Loading...';
  let r = await fetch('/api/search?q=' + encodeURIComponent(e('q').value));
  let d = await r.json();
  e('results').innerHTML = '';
  d.forEach(p=>{
    let div = document.createElement('div');
    div.className='card';
    div.innerHTML = `<b>${p.title}</b><br><span class='tiny'>${p.author}</span><br>
    <button onclick="addFeed('${p.url}')">➕ Add</button>`;
    e('results').appendChild(div);
  });
}
async function addFeed(url){
  await fetch('/api/add_by_rss', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({rss_url:url})
  });
  alert('Added!');
}
function addRss(){addFeed(e('rss').value);}
async function loadFavourites(){
  const r = await fetch('/api/favorites');
  favs = await r.json(); page = 0;
  showPage();
}
function showPage(){
  let b = e('fav-buttons'); b.innerHTML = '';
  let start = page * pageSize, end = Math.min(start + pageSize, favs.length);
  for (let i = start; i < end; i++){
    let p = favs[i];
    let btn = document.createElement('button');
    btn.innerText = `${(i-start+1)}⃣ ${p.title.slice(0, 20)}`;
    btn.onclick = ()=>loadFav(i);
    b.appendChild(btn);
    let del = document.createElement('button');
    del.innerText = '🔥 Delete';
    del.onclick = ()=>deleteFav(p.podcast_id);
    del.style.backgroundColor = '#f88';
    b.appendChild(del);
  }
}
function nextPage(){ if((page+1)*pageSize < favs.length){ page++; showPage(); }}
function prevPage(){ if(page > 0){ page--; showPage(); }}
async function loadFav(i){
  let p = favs[i];
  e('results').innerHTML = `<b>${p.title}</b><br>Loading...`;
  let r = await fetch(`/api/podcast/${encodeURIComponent(p.podcast_id)}/episodes`);
  let d = await r.json();
  d.forEach(ep=>{
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${ep.title}</b><br><span class='tiny'>${ep.pub_date}</span><br>
    <a href="${ep.audio_url}" target="_blank">▶️ Play / Download</a>`;
    e('results').appendChild(div);
  });
}
async function deleteFav(pid){
  if(!confirm('Delete this podcast?')) return;
  await fetch('/api/delete/' + encodeURIComponent(pid), {method:'DELETE'});
  await loadFavourites();
  e('results').innerHTML = 'Deleted.';
}
</script></body></html>
'''

# ─── Start ──────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)