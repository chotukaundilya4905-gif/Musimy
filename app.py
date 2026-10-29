import os
import time
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# ---------- In-memory caches ----------
_SEARCH_CACHE = {}
_PLAY_CACHE = {}
SEARCH_TTL = 600      # 10 minutes
PLAY_TTL   = 3600     # 1 hour

# ============================================================
# FAST YouTube search using yt-dlp (Extraction disabled for speed)
# ============================================================
def fast_yt_search(query, limit=5):
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'default_search': f'ytsearch{limit}',
        'skip_download': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            results = []
            if 'entries' in info:
                for entry in info['entries']:
                    if not entry: continue
                    
                    thumb = entry.get('thumbnail', '')
                    if not thumb and entry.get('thumbnails'):
                        thumb = entry.get('thumbnails')[-1].get('url', '')
                        
                    results.append({
                        'id': entry.get('id'),
                        'title': entry.get('title', 'Unknown'),
                        'artist': entry.get('uploader', 'YouTube'),
                        'thumb': thumb
                    })
            return results
    except Exception as e:
        print(f"Search error: {e}")
        return []

# ============================================================
# Audio URL extraction
# ============================================================
def extract_audio_url(video_id):
    now = time.time()
    if video_id in _PLAY_CACHE and now - _PLAY_CACHE[video_id]["t"] < PLAY_TTL:
        return _PLAY_CACHE[video_id]["url"]

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

        url = None
        for f in info.get("formats", []):
            if f.get("acodec") == "none":
                continue
            if f.get("vcodec") == "none" and f.get("ext") == "m4a":
                url = f["url"]
                break
            if not url:
                url = f.get("url")
        if not url:
            url = info.get("url")

        _PLAY_CACHE[video_id] = {"t": now, "url": url}
        return url
    except Exception as e:
        print(f"Play extraction error: {e}")
        return None

# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def index():
    return send_from_directory(".", "music.html")

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query empty"}), 400

    key = query.lower()
    now = time.time()
    if key in _SEARCH_CACHE and now - _SEARCH_CACHE[key]["t"] < SEARCH_TTL:
        return jsonify(_SEARCH_CACHE[key]["d"])

    results = fast_yt_search(query, limit=10)
    _SEARCH_CACHE[key] = {"t": now, "d": results}
    return jsonify(results)

@app.route("/api/play/<video_id>")
def api_play(video_id):
    try:
        url = extract_audio_url(video_id)
        if not url:
            return jsonify({"error": "No audio found"}), 404
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download")
def download_song():
    video_id = request.args.get("id")
    quality  = request.args.get("quality", "192")
    if not video_id:
        return "Invalid ID", 400

    if quality == "320":
        fmt = "bestaudio[abr>=256]/bestaudio[ext=m4a]/bestaudio/best"
    elif quality == "128":
        fmt = "bestaudio[abr<=128]/bestaudio[ext=m4a]/bestaudio/best"
    else:
        fmt = "bestaudio[ext=m4a]/bestaudio/best"

    ydl_opts = {
        "format": fmt,
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "nocheckcertificate": True,
        "quiet": True,
        "noplaylist": True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    os.makedirs('downloads', exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            filename = ydl.prepare_filename(info)
        
        return jsonify({"status": "success", "filename": os.path.basename(filename)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/file/<filename>")
def serve_file(filename):
    try:
        return send_from_directory("downloads", filename, as_attachment=True)
    except:
        return "File not found", 404

@app.route("/api/check_download")
def check_download():
    video_id = request.args.get("id")
    filename = request.args.get("filename")
    if filename and os.path.exists(os.path.join("downloads", filename)):
        return jsonify({"downloaded": True, "filename": filename})
    return jsonify({"downloaded": False})

# ============================================================
# REAL UPDATE CORE LOGIC
# ============================================================
@app.route("/api/update_core", methods=["POST"])
def update_core():
    data = request.get_json()
    code = data.get("code", "")
    if not code.strip():
        return jsonify({"status": "error", "msg": "Code is empty!"}), 400
    try:
        # Naya code app.py me save kar do
        with open("app.py", "w", encoding="utf-8") as f:
            f.write(code)
        return jsonify({"status": "success", "msg": "Core updated successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
