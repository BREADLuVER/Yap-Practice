import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
import whisper
import yt_dlp
from firebase_admin import credentials, firestore

_model = None
_db = None


@dataclass(frozen=True)
class TranscriptQualityFilter:
    min_speech_ratio: float = 0.0


def get_whisper_model():
    global _model
    if _model is None:
        _model = whisper.load_model("base")
    return _model


def get_firestore_client():
    global _db
    if _db is not None:
        return _db

    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parent
    service_account_path = repo_root / "serviceAccountKey.json"
    try:
        firebase_admin.get_app()
    except ValueError:
        if service_account_path.exists():
            cred = credentials.Certificate(str(service_account_path))
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


def _coerce_duration_seconds(duration: Any) -> int:
    if isinstance(duration, bool):
        return 0
    if isinstance(duration, (int, float)):
        return max(int(duration), 0)
    if isinstance(duration, str):
        stripped = duration.strip()
        if stripped.isdigit():
            return int(stripped)
    return 0


def _compute_speech_coverage_seconds(
    transcript_result: dict[str, Any],
    merge_gap_seconds: float = 0.35,
) -> float:
    """
    Computes speech coverage by merging nearby transcript segments.
    A short silence gap is treated as continuous speech to avoid
    under-counting natural pauses between words/phrases.
    """
    segments = transcript_result.get("segments", [])
    intervals: list[tuple[float, float]] = []

    for segment in segments:
        start = segment.get("start")
        end = segment.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        start_f = float(start)
        end_f = float(end)
        if end_f <= start_f:
            continue
        intervals.append((start_f, end_f))

    if not intervals:
        return 0.0

    intervals.sort(key=lambda item: item[0])
    merged_start, merged_end = intervals[0]
    merged_total = 0.0

    for start, end in intervals[1:]:
        if start <= merged_end + merge_gap_seconds:
            merged_end = max(merged_end, end)
            continue
        merged_total += merged_end - merged_start
        merged_start, merged_end = start, end

    merged_total += merged_end - merged_start
    return max(merged_total, 0.0)


def _evaluate_transcript_quality(
    duration_seconds: int,
    transcript_result: dict[str, Any],
    words: list[dict[str, Any]],
    filter_settings: TranscriptQualityFilter,
) -> dict[str, Any]:
    word_count = len(words)
    spoken_seconds = _compute_speech_coverage_seconds(transcript_result)
    speech_ratio = (spoken_seconds / duration_seconds) if duration_seconds > 0 else 0.0

    if filter_settings.min_speech_ratio > 0 and speech_ratio < filter_settings.min_speech_ratio:
        return {
            "passed": False,
            "reason": "low_speech_ratio",
            "metrics": {
                "durationSeconds": duration_seconds,
                "wordCount": word_count,
                "spokenSeconds": round(spoken_seconds, 2),
                "speechRatio": round(speech_ratio, 4),
            },
        }

    return {
        "passed": True,
        "reason": "",
        "metrics": {
            "durationSeconds": duration_seconds,
            "wordCount": word_count,
            "spokenSeconds": round(spoken_seconds, 2),
            "speechRatio": round(speech_ratio, 4),
        },
    }


def process_video_url(
    url: str,
    extra_metadata: dict[str, Any] | None = None,
    skip_if_exists: bool = False,
    filter_settings: TranscriptQualityFilter | None = None,
) -> dict[str, Any]:
    db = get_firestore_client()
    quality_filter = filter_settings or TranscriptQualityFilter()

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

            duration = _coerce_duration_seconds(duration)
            audio_path = _resolve_audio_path(temp_dir, video_id)

            model = get_whisper_model()
            transcript_result = model.transcribe(audio_path, word_timestamps=True)
            words = _build_words(transcript_result)
            quality_result = _evaluate_transcript_quality(
                duration,
                transcript_result,
                words,
                quality_filter,
            )
            if not quality_result["passed"]:
                return {
                    "status": "skipped_filter",
                    "video_id": video_id,
                    "reason": quality_result["reason"],
                    "metrics": quality_result["metrics"],
                }

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
                "transcriptStats": quality_result["metrics"],
            }

            if isinstance(published_at, datetime):
                payload["publishedAt"] = published_at

            doc_ref = db.collection("videos").document(video_id)
            doc_ref.set(payload)

            return {"status": "ingested", "video_id": video_id, "title": title}
