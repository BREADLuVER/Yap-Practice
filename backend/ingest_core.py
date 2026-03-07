import os
import tempfile
from datetime import datetime, timezone
from typing import Any

import firebase_admin
import whisper
import yt_dlp
from firebase_admin import credentials, firestore

_model = None
_db = None


def get_whisper_model():
    global _model
    if _model is None:
        _model = whisper.load_model("base")
    return _model


def get_firestore_client():
    global _db
    if _db is not None:
        return _db

    service_account_path = "serviceAccountKey.json"
    try:
        firebase_admin.get_app()
    except ValueError:
        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()

    _db = firestore.client()
    return _db


def get_ytdlp_cookie_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {}

    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if cookies_file:
        opts["cookiefile"] = cookies_file

    cookies_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if cookies_browser:
        if ":" in cookies_browser:
            browser_name, browser_profile = cookies_browser.split(":", 1)
            browser_name = browser_name.strip()
            browser_profile = browser_profile.strip()
            if browser_name and browser_profile:
                opts["cookiesfrombrowser"] = (browser_name, browser_profile)
        else:
            opts["cookiesfrombrowser"] = (cookies_browser,)

    return opts


def build_base_ydl_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }
    opts.update(get_ytdlp_cookie_opts())
    return opts


def parse_upload_date(upload_date: str | None) -> datetime | None:
    if not upload_date:
        return None
    try:
        parsed = datetime.strptime(upload_date, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def extract_video_metadata(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(build_base_ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def video_exists(video_id: str) -> bool:
    db = get_firestore_client()
    doc_ref = db.collection("videos").document(video_id)
    return doc_ref.get().exists


def _resolve_audio_path(temp_dir: str, video_id: str) -> str:
    default_audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
    if os.path.exists(default_audio_path):
        return default_audio_path

    for file_name in os.listdir(temp_dir):
        if file_name.startswith(video_id):
            return os.path.join(temp_dir, file_name)

    return default_audio_path


def _build_words(transcript_result: dict[str, Any]) -> list[dict[str, Any]]:
    segments = transcript_result.get("segments", [])
    words: list[dict[str, Any]] = []
    for segment in segments:
        for word_info in segment.get("words", []):
            words.append(
                {
                    "word": word_info["word"],
                    "start": word_info["start"],
                    "end": word_info["end"],
                }
            )
    return words


def process_video_url(
    url: str,
    extra_metadata: dict[str, Any] | None = None,
    skip_if_exists: bool = False,
) -> dict[str, Any]:
    db = get_firestore_client()

    with tempfile.TemporaryDirectory() as temp_dir:
        ydl_opts: dict[str, Any] = {
            **build_base_ydl_opts(),
            "format": "bestaudio/best",
            "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info["id"]

            if skip_if_exists and video_exists(video_id):
                return {"status": "skipped_existing", "video_id": video_id}

            title = info.get("title", "Unknown Title")
            thumbnail = info.get("thumbnail", "")
            duration = info.get("duration", 0)
            view_count = info.get("view_count")
            source_channel = info.get("channel") or info.get("uploader")
            source_url = info.get("webpage_url") or url
            published_at = parse_upload_date(info.get("upload_date"))

            if extra_metadata:
                title = extra_metadata.get("title", title)
                thumbnail = extra_metadata.get("thumbnailUrl", thumbnail)
                duration = extra_metadata.get("duration", duration)
                view_count = extra_metadata.get("viewCount", view_count)
                source_channel = extra_metadata.get("sourceChannel", source_channel)
                source_url = extra_metadata.get("sourceUrl", source_url)
                published_at = extra_metadata.get("publishedAt", published_at)

            audio_path = _resolve_audio_path(temp_dir, video_id)

            model = get_whisper_model()
            transcript_result = model.transcribe(audio_path, word_timestamps=True)
            words = _build_words(transcript_result)

            payload: dict[str, Any] = {
                "video_id": video_id,
                "title": title,
                "thumbnailUrl": thumbnail,
                "duration": duration,
                "words": words,
                "full_text": transcript_result.get("text", ""),
                "createdAt": firestore.SERVER_TIMESTAMP,
                "ingestedAt": firestore.SERVER_TIMESTAMP,
                "sourceChannel": source_channel or "",
                "sourceUrl": source_url,
                "viewCount": int(view_count) if isinstance(view_count, (int, float)) else 0,
            }

            if isinstance(published_at, datetime):
                payload["publishedAt"] = published_at

            doc_ref = db.collection("videos").document(video_id)
            doc_ref.set(payload)

            return {"status": "ingested", "video_id": video_id, "title": title}
