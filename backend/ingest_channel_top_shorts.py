import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from firebase_admin import firestore

from ingest_core import get_firestore_client, process_video_url, video_exists

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_CHANNEL_URL = "https://www.youtube.com/@TheLibraryofLetourneau/shorts"


@dataclass
class CatalogEntry:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    source_url: str
    thumbnail_url: str
    duration_seconds: int
    view_count: int
    published_at: datetime | None


def _read_env_value(file_path: Path, key: str) -> str | None:
    if not file_path.exists():
        return None

    try:
        with file_path.open("r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                env_key, env_value = line.split("=", 1)
                if env_key.strip() != key:
                    continue

                value = env_value.strip().strip("'").strip('"')
                if value:
                    return value
    except OSError:
        return None

    return None


def _resolve_api_key(cli_api_key: str) -> str:
    if cli_api_key.strip():
        return cli_api_key.strip()

    from_env = os.getenv("YOUTUBE_API_KEY", "").strip()
    if from_env:
        return from_env

    repo_root = Path(__file__).resolve().parent.parent
    candidate_env_files = [
        repo_root / ".env",
        repo_root / ".env.local",
        repo_root / "backend" / ".env",
        repo_root / "backend" / ".env.local",
        repo_root / "frontend" / ".env.local",
    ]
    for env_path in candidate_env_files:
        value = _read_env_value(env_path, "YOUTUBE_API_KEY")
        if value:
            return value

    return ""


def _http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params)
    req = Request(f"{url}?{query}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _extract_handle_or_channel_id(channel_url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(channel_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    channel_id: str | None = None
    handle: str | None = None

    if len(segments) >= 2 and segments[0] == "channel":
        channel_id = segments[1]
    else:
        for segment in segments:
            if segment.startswith("@") and len(segment) > 1:
                handle = segment[1:]
                break

    return handle, channel_id


def _resolve_channel_id(api_key: str, channel_url: str) -> str:
    handle, explicit_channel_id = _extract_handle_or_channel_id(channel_url)
    if explicit_channel_id:
        return explicit_channel_id

    if handle:
        resp = _http_get_json(
            f"{YOUTUBE_API_BASE}/channels",
            {"part": "id", "forHandle": handle, "maxResults": 1, "key": api_key},
        )
        items = resp.get("items", [])
        if items:
            channel_id = items[0].get("id", "")
            if channel_id:
                return channel_id

    parsed = urlparse(channel_url)
    query = parse_qs(parsed.query)
    q = query.get("q", [""])[0].strip() or (handle or parsed.path.strip("/"))
    if not q:
        raise ValueError(f"Unable to resolve channel from URL: {channel_url}")

    search_resp = _http_get_json(
        f"{YOUTUBE_API_BASE}/search",
        {"part": "snippet", "type": "channel", "q": q, "maxResults": 1, "key": api_key},
    )
    search_items = search_resp.get("items", [])
    if not search_items:
        raise ValueError(f"No channel found for URL: {channel_url}")

    found_channel_id = search_items[0].get("snippet", {}).get("channelId", "")
    if not found_channel_id:
        raise ValueError(f"Search did not return channelId for URL: {channel_url}")
    return found_channel_id


def _get_uploads_playlist_id(api_key: str, channel_id: str) -> tuple[str, str]:
    resp = _http_get_json(
        f"{YOUTUBE_API_BASE}/channels",
        {"part": "contentDetails,snippet", "id": channel_id, "maxResults": 1, "key": api_key},
    )
    items = resp.get("items", [])
    if not items:
        raise ValueError(f"Channel not found: {channel_id}")

    item = items[0]
    uploads_playlist_id = (
        item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
    )
    if not uploads_playlist_id:
        raise ValueError(f"Uploads playlist not available for channel: {channel_id}")

    channel_title = item.get("snippet", {}).get("title", "")
    return uploads_playlist_id, channel_title


def _fetch_all_upload_video_ids(api_key: str, playlist_id: str) -> list[str]:
    video_ids: list[str] = []
    page_token = ""

    while True:
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = _http_get_json(f"{YOUTUBE_API_BASE}/playlistItems", params)
        for item in resp.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId", "")
            if video_id:
                video_ids.append(video_id)

        page_token = resp.get("nextPageToken", "")
        if not page_token:
            break

    return list(dict.fromkeys(video_ids))


def _parse_iso8601_duration_to_seconds(duration: str) -> int:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        duration or "",
    )
    if not match:
        return 0

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _best_thumbnail(thumbnails: dict[str, Any]) -> str:
    for key in ("maxres", "standard", "high", "medium", "default"):
        url = thumbnails.get(key, {}).get("url", "")
        if url:
            return url
    return ""


def _fetch_video_entries(api_key: str, video_ids: list[str], duration_max: int) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start : start + 50]
        resp = _http_get_json(
            f"{YOUTUBE_API_BASE}/videos",
            {
                "part": "contentDetails,statistics,snippet",
                "id": ",".join(chunk),
                "maxResults": 50,
                "key": api_key,
            },
        )

        for item in resp.get("items", []):
            content_details = item.get("contentDetails", {})
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})

            duration_seconds = _parse_iso8601_duration_to_seconds(content_details.get("duration", ""))
            if duration_seconds <= 0 or duration_seconds > duration_max:
                continue

            video_id = item.get("id", "")
            if not video_id:
                continue

            source_url = f"https://www.youtube.com/watch?v={video_id}"
            entries.append(
                CatalogEntry(
                    video_id=video_id,
                    title=snippet.get("title", "Unknown Title"),
                    channel_id=snippet.get("channelId", ""),
                    channel_title=snippet.get("channelTitle", "Unknown Channel"),
                    source_url=source_url,
                    thumbnail_url=_best_thumbnail(snippet.get("thumbnails", {})),
                    duration_seconds=duration_seconds,
                    view_count=int(stats.get("viewCount", "0")),
                    published_at=_parse_published_at(snippet.get("publishedAt")),
                )
            )

    return entries


def _upsert_catalog(entries: list[CatalogEntry], channel_id: str) -> None:
    db = get_firestore_client()
    collection = db.collection("channelShortsCatalog")
    now = firestore.SERVER_TIMESTAMP

    for start in range(0, len(entries), 400):
        chunk = entries[start : start + 400]
        batch = db.batch()
        for entry in chunk:
            doc_ref = collection.document(entry.video_id)
            payload: dict[str, Any] = {
                "video_id": entry.video_id,
                "channelId": channel_id,
                "channelTitle": entry.channel_title,
                "title": entry.title,
                "sourceUrl": entry.source_url,
                "thumbnailUrl": entry.thumbnail_url,
                "duration": entry.duration_seconds,
                "viewCount": entry.view_count,
                "lastCatalogedAt": now,
            }
            if isinstance(entry.published_at, datetime):
                payload["publishedAt"] = entry.published_at
            batch.set(doc_ref, payload, merge=True)
        batch.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover a channel's top Shorts by views via YouTube Data API and ingest top unseen."
    )
    parser.add_argument(
        "--channel-url",
        default=DEFAULT_CHANNEL_URL,
        help="Channel URL (handle or /channel/{id}). Defaults to TheLibraryofLetourneau shorts URL.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="YouTube Data API key. Falls back to env and local .env files.",
    )
    parser.add_argument(
        "--duration-max",
        type=int,
        default=180,
        help="Maximum duration in seconds to treat as Shorts. Default 180.",
    )
    parser.add_argument(
        "--max-new",
        type=int,
        default=4,
        help="Maximum number of unseen top-ranked videos to ingest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected videos without running transcription/upload.",
    )
    parser.add_argument(
        "--skip-catalog-write",
        action="store_true",
        help="Skip writing ranked metadata into Firestore catalog collection.",
    )
    parser.add_argument(
        "--check-existing-in-dry-run",
        action="store_true",
        help="In dry-run mode, check Firestore for already ingested video IDs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = _resolve_api_key(args.api_key)

    if not api_key:
        raise ValueError(
            "Missing YouTube API key. Set --api-key, export YOUTUBE_API_KEY, or add it to frontend/.env.local."
        )
    if args.duration_max <= 0:
        raise ValueError("--duration-max must be greater than 0.")
    if args.max_new <= 0:
        raise ValueError("--max-new must be greater than 0.")

    channel_id = _resolve_channel_id(api_key, args.channel_url)
    uploads_playlist_id, channel_title = _get_uploads_playlist_id(api_key, channel_id)

    print(f"Resolved channel: {channel_title} ({channel_id})")
    print(f"Uploads playlist: {uploads_playlist_id}")

    video_ids = _fetch_all_upload_video_ids(api_key, uploads_playlist_id)
    print(f"Fetched upload ids: {len(video_ids)}")

    entries = _fetch_video_entries(api_key, video_ids, args.duration_max)
    ranked = sorted(entries, key=lambda item: item.view_count, reverse=True)
    print(f"Filtered shorts (<= {args.duration_max}s): {len(ranked)}")

    should_write_catalog = not args.skip_catalog_write and not args.dry_run
    if should_write_catalog:
        _upsert_catalog(ranked, channel_id)
        print(f"Catalog upserted: {len(ranked)} records -> channelShortsCatalog")
    elif args.dry_run and not args.skip_catalog_write:
        print("Dry run: skipped catalog write to avoid Firestore dependency.")

    selected = 0
    skipped_existing = 0
    failures = 0
    for entry in ranked:
        if selected >= args.max_new:
            break

        if not args.dry_run or args.check_existing_in_dry_run:
            if video_exists(entry.video_id):
                skipped_existing += 1
                continue

        print(
            f"Selected: {entry.title} ({entry.video_id}) "
            f"views={entry.view_count} duration={entry.duration_seconds}s"
        )

        if args.dry_run:
            selected += 1
            continue

        try:
            result = process_video_url(
                entry.source_url,
                extra_metadata={
                    "viewCount": entry.view_count,
                    "sourceChannel": entry.channel_title,
                    "sourceUrl": entry.source_url,
                    "publishedAt": entry.published_at,
                    "thumbnailUrl": entry.thumbnail_url,
                    "duration": entry.duration_seconds,
                    "title": entry.title,
                },
                skip_if_exists=True,
            )
            if result.get("status") == "ingested":
                selected += 1
        except Exception as error:
            failures += 1
            print(f"Failed ingest for {entry.video_id}: {error}")

    print("Top shorts ingest summary")
    print(f"- channel: {channel_title}")
    print(f"- uploads_scanned: {len(video_ids)}")
    print(f"- shorts_ranked: {len(ranked)}")
    print(f"- skipped_existing: {skipped_existing}")
    print(f"- selected_or_ingested: {selected}")
    print(f"- failures: {failures}")
    if args.dry_run:
        print("Dry run complete. No transcriptions were executed.")


if __name__ == "__main__":
    main()
