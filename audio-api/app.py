"""Small Render-hosted audio service for downloads the user is authorized to make."""
import os
import re
import tempfile
import hmac
from pathlib import Path
from flask import Flask, jsonify, request, send_file
import yt_dlp

app = Flask(__name__)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

@app.get("/health")
def health():
    return jsonify(status="ok",service="ipod-audio-api")

@app.post("/convert")
def convert():
    key = os.environ.get("AUDIO_API_KEY")
    if not key:
        return jsonify(error="Audio API key not configured"), 503
    supplied = request.headers.get("X-Audio-Key", "")
    if not hmac.compare_digest(supplied, key):
        return jsonify(error="Unauthorized"), 401
    data = request.get_json(silent=True) or {}
    video_id = str(data.get("videoId", ""))
    if not VIDEO_ID.fullmatch(video_id):
        return jsonify(error="Invalid video ID"), 400
    if data.get("authorized") is not True:
        return jsonify(error="Only request downloads you are authorized to make"), 400
    directory = tempfile.TemporaryDirectory()
    try:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(directory.name) / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "retries": 1,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(["https://www.youtube.com/watch?v=" + video_id])
        audio = Path(directory.name) / (video_id + ".mp3")
        if not audio.is_file() or audio.stat().st_size < 1024:
            return jsonify(error="No valid MP3 produced"), 502
        # Keep temporary directory alive through response iteration.
        from flask import Response, stream_with_context
        def chunks():
            try:
                with audio.open("rb") as handle:
                    while chunk := handle.read(65536):
                        yield chunk
            finally:
                directory.cleanup()
        return Response(stream_with_context(chunks()), mimetype="audio/mpeg", headers={"Cache-Control":"no-store"})
    except Exception as exc:
        directory.cleanup()
        app.logger.warning("Audio conversion failed: %s", type(exc).__name__)
        return jsonify(error="Audio conversion failed; provider may restrict automated access",type=type(exc).__name__), 502
