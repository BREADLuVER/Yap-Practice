import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yt_dlp

from ingest_core import (
    build_base_ydl_opts,
    extract_video_metadata,
    parse_upload_date,
    process_video_url,
    video_exists,
)


@dataclass
class ClipCandidate:
    video_id: str
    title: str
    channel: str
    url: str
    view_count: int
    duration: int
    thumbnail: str
    upload_date: str | None
    published_at: datetime | None


def normalize_channels(raw_channels: list[str]) -> list[str]:
    channels: list[str] = []
    for value in raw_channels:
        for item in value.split(","):
            cleaned = item.strip()
            if cleaned:
                channels.append(cleaned)
    return channels


def _entry_url(entry: dict[str, Any]) -> str:
    video_id = entry.get("id", "")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return entry.get("url") or entry.get("webpage_url") or ""


def fetch_channel_candidates(channel_url: str, per_channel_fetch: int) -> list[ClipCandidate]:
    opts = {
        **build_base_ydl_opts(),
        "extract_flat": "in_playlist",
        "playlistend": per_channel_fetch,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        feed = ydl.extract_info(channel_url, download=False)

    entries = feed.get("entries", []) if isinstance(feed, dict) else []
    candidates: list[ClipCandidate] = []

    for entry in entries[:per_channel_fetch]:
        entry_url = _entry_url(entry)
        if not entry_url:
            continue

        try:
            details = extract_video_metadata(entry_url)
        except Exception as error:
            print(f"Failed metadata lookup for {entry_url}: {error}")
            continue

        video_id = details.get("id")
        if not video_id:
            continue

        upload_date = details.get("upload_date")
        candidate = ClipCandidate(
            video_id=video_id,
            title=details.get("title", "Unknown Title"),
            channel=details.get("channel") or details.get("uploader") or "Unknown Channel",
            url=details.get("webpage_url") or entry_url,
            view_count=int(details.get("view_count") or 0),
            duration=int(details.get("duration") or 0),
            thumbnail=details.get("thumbnail") or "",
            upload_date=upload_date,
            published_at=parse_upload_date(upload_date),
        )
        candidates.append(candidate)

    return candidates


def dedupe_candidates(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    unique: dict[str, ClipCandidate] = {}
    for candidate in candidates:
        existing = unique.get(candidate.video_id)
        if existing is None or candidate.view_count > existing.view_count:
            unique[candidate.video_id] = candidate
    return list(unique.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch ingest YouTube Shorts from channels")
    parser.add_argument(
        "--channels",
        action="append",
        required=True,
        help="Channel Shorts URL(s). Repeat flag or pass comma-separated values.",
    )
    parser.add_argument(
        "--max-new",
        type=int,
        default=4,
        help="Maximum number of new unseen clips to ingest per run.",
    )
    parser.add_argument(
        "--per-channel-fetch",
        type=int,
        default=15,
        help="How many shorts to fetch per channel before ranking.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select clips and print actions without transcribing or uploading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channels = normalize_channels(args.channels)

    if not channels:
        raise ValueError("No channels provided.")
    if args.max_new <= 0:
        raise ValueError("--max-new must be greater than 0.")
    if args.per_channel_fetch <= 0:
        raise ValueError("--per-channel-fetch must be greater than 0.")

    all_candidates: list[ClipCandidate] = []
    for channel_url in channels:
        print(f"Collecting shorts from: {channel_url}")
        candidates = fetch_channel_candidates(channel_url, args.per_channel_fetch)
        print(f"Found {len(candidates)} candidate shorts")
        all_candidates.extend(candidates)

    deduped_candidates = dedupe_candidates(all_candidates)
    ranked_candidates = sorted(deduped_candidates, key=lambda c: c.view_count, reverse=True)

    skipped_existing = 0
    ingested = 0
    failures = 0

    for candidate in ranked_candidates:
        if ingested >= args.max_new:
            break

        if video_exists(candidate.video_id):
            skipped_existing += 1
            continue

        print(
            f"Selected: {candidate.title} ({candidate.video_id}) "
            f"views={candidate.view_count} channel={candidate.channel}"
        )

        if args.dry_run:
            ingested += 1
            continue

        try:
            result = process_video_url(
                candidate.url,
                extra_metadata={
                    "viewCount": candidate.view_count,
                    "sourceChannel": candidate.channel,
                    "sourceUrl": candidate.url,
                    "publishedAt": candidate.published_at,
                    "thumbnailUrl": candidate.thumbnail,
                    "duration": candidate.duration,
                    "title": candidate.title,
                },
                skip_if_exists=True,
            )
            if result.get("status") == "ingested":
                ingested += 1
        except Exception as error:
            failures += 1
            print(f"Failed ingest for {candidate.video_id}: {error}")

    print("Batch summary")
    print(f"- channels: {len(channels)}")
    print(f"- candidates: {len(all_candidates)}")
    print(f"- unique_candidates: {len(deduped_candidates)}")
    print(f"- skipped_existing: {skipped_existing}")
    print(f"- selected_or_ingested: {ingested}")
    print(f"- failures: {failures}")
    if args.dry_run:
        print("Dry run complete. No transcriptions were executed.")


if __name__ == "__main__":
    main()
