import argparse
from typing import Iterable

from ingest_core import get_firestore_client


def _chunked(items: list[str], chunk_size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), chunk_size):
        yield items[start : start + chunk_size]


def _delete_collection_docs(collection_path: str, dry_run: bool, batch_size: int) -> int:
    db = get_firestore_client()
    doc_refs = list(db.collection(collection_path).list_documents())
    doc_ids = [doc_ref.id for doc_ref in doc_refs]
    if not doc_ids:
        return 0

    if dry_run:
        return len(doc_ids)

    deleted = 0
    for chunk in _chunked(doc_ids, batch_size):
        batch = db.batch()
        for doc_id in chunk:
            batch.delete(db.collection(collection_path).document(doc_id))
        batch.commit()
        deleted += len(chunk)
    return deleted


def _delete_users_clip_progress(dry_run: bool, batch_size: int) -> int:
    db = get_firestore_client()
    user_refs = list(db.collection("users").list_documents())
    progress_refs = []

    for user_ref in user_refs:
        progress_refs.extend(list(user_ref.collection("clip_progress").list_documents()))

    if not progress_refs:
        return 0

    if dry_run:
        return len(progress_refs)

    deleted = 0
    for chunk in _chunked([ref.path for ref in progress_refs], batch_size):
        batch = db.batch()
        for path in chunk:
            batch.delete(db.document(path))
        batch.commit()
        deleted += len(chunk)
    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete ingestion-related Firestore data for a blank restart."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation flag to run destructive deletes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print how many records would be deleted without deleting them.",
    )
    parser.add_argument(
        "--keep-catalog",
        action="store_true",
        help="Keep channelShortsCatalog collection documents.",
    )
    parser.add_argument(
        "--keep-user-progress",
        action="store_true",
        help="Keep users/*/clip_progress documents.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=300,
        help="Firestore batch size (<= 500). Default 300.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.batch_size <= 0 or args.batch_size > 500:
        raise ValueError("--batch-size must be between 1 and 500.")

    if not args.yes and not args.dry_run:
        raise ValueError("Refusing to delete data without --yes. Use --dry-run first to preview.")

    print("Resetting ingest data collections")
    print(f"- mode: {'dry-run' if args.dry_run else 'delete'}")

    videos_deleted = _delete_collection_docs("videos", args.dry_run, args.batch_size)
    print(f"- videos: {videos_deleted}")

    if args.keep_catalog:
        print("- channelShortsCatalog: kept")
    else:
        catalog_deleted = _delete_collection_docs("channelShortsCatalog", args.dry_run, args.batch_size)
        print(f"- channelShortsCatalog: {catalog_deleted}")

    if args.keep_user_progress:
        print("- users/*/clip_progress: kept")
    else:
        clip_progress_deleted = _delete_users_clip_progress(args.dry_run, args.batch_size)
        print(f"- users/*/clip_progress: {clip_progress_deleted}")

    if args.dry_run:
        print("Dry run complete. No documents were deleted.")
    else:
        print("Delete complete. Ingest-related data is now reset.")


if __name__ == "__main__":
    main()
