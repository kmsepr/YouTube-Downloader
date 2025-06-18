import os
import sqlite3
import requests
import feedparser
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
DB_FILE = 'podcasts.db'

# Initialize DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id TEXT UNIQUE,
            title TEXT,
            author TEXT,
            cover_url TEXT,
            rss_url TEXT
        )
    ''')
    cursor.execute('''
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

# 🔍 Search podcasts using ListenNotes
@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    api_key = os.getenv('LISTEN_NOTES_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key missing'}), 500
    try:
        res = requests.get(
            f'https://listen-api.listennotes.com/api/v2/search?q={query}',
            headers={'X-ListenAPI-Key': api_key}
        )
        return jsonify(res.json().get('results', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ➕ Add podcast to favorites
@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    data = request.get_json()
    fields = ['podcast_id', 'title', 'author', 'cover_url', 'rss_url']
    if not all(field in data for field in fields):
        return jsonify({'error': 'Missing fields'}), 400
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['podcast_id'], data['title'], data['author'], data['cover_url'], data['rss_url']))
        conn.commit()
        return jsonify({'message': 'Podcast added'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ⭐ Get all favorite podcasts
@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM podcasts')
    podcasts = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify(podcasts)

# 🎧 Get episodes for a podcast
@app.route('/api/podcast/<podcast_id>/episodes', methods=['GET'])
def get_episodes(podcast_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Check DB first
    cursor.execute('SELECT * FROM episodes WHERE podcast_id = ?', (podcast_id,))
    episodes = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    if episodes:
        conn.close()
        return jsonify(episodes)

    # Else fetch RSS
    cursor.execute('SELECT rss_url FROM podcasts WHERE podcast_id = ?', (podcast_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    rss_url = row[0]
    feed = feedparser.parse(rss_url)
    new_episodes = []

    try:
        for item in feed.entries:
            ep_id = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
            title = item.get('title', '')
            desc = item.get('summary', '')
            audio = item.get('enclosures')[0]['href'] if item.get('enclosures') else ''
            pub_date = item.get('published', '')
            duration = int(item.get('itunes_duration', 0)) if 'itunes_duration' in item else 0

            new_episodes.append({
                'episode_id': ep_id,
                'title': title,
                'description': desc,
                'audio_url': audio,
                'pub_date': pub_date,
                'duration': duration
            })

            cursor.execute('''
                INSERT OR IGNORE INTO episodes
                (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (podcast_id, ep_id, title, desc, audio, pub_date, duration))

        conn.commit()
        return jsonify(new_episodes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 🔃 Health check
@app.route('/')
def home():
    return '🎙️ Podcast API is running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 3000)))