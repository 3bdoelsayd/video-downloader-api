from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "/tmp/downloads"
COOKIES_FILE = "/tmp/cookies.txt"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# كتابة الـ cookies من الـ Environment Variable
cookies_content = os.environ.get("COOKIES_CONTENT", "")
if cookies_content:
    with open(COOKIES_FILE, "w") as f:
        f.write(cookies_content)


def cleanup_old_files():
    while True:
        time.sleep(3600)
        now = time.time()
        for f in os.listdir(DOWNLOAD_FOLDER):
            path = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.getmtime(path) < now - 3600:
                os.remove(path)

threading.Thread(target=cleanup_old_files, daemon=True).start()


def get_format(quality):
    if quality == "audio":
        return "bestaudio/best"
    elif quality == "best":
        return "bestvideo+bestaudio/best"
    else:
        return f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"


def get_ydl_opts_base():
    opts = {"quiet": True, "noplaylist": True}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "✅ السيرفر شغّال!"})


@app.route("/info", methods=["POST"])
def get_info():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "الرابط فاضي"}), 400

    try:
        ydl_opts = get_ydl_opts_base()
        ydl_opts["skip_download"] = True
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get("title", ""),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", ""),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url", "").strip()
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "الرابط فاضي!"}), 400

    try:
        file_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

        ydl_opts = get_ydl_opts_base()
        ydl_opts.update({
            "format": get_format(quality),
            "outtmpl": output_template,
            "merge_output_format": "mp4",
        })

        if quality == "audio":
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            thumbnail = info.get("thumbnail", "")
            ext = "mp3" if quality == "audio" else "mp4"
            filename = f"{file_id}.{ext}"

        base_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        if base_url:
            download_url = f"https://{base_url}/file/{filename}"
        else:
            download_url = f"http://localhost:5000/file/{filename}"

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "download_url": download_url,
            "filename": filename,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/file/<filename>")
def serve_file(filename):
    filename = os.path.basename(filename)
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({"error": "الملف مش موجود أو انتهت صلاحيته"}), 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
