import argparse
from ingest_core import process_video_url

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest YouTube video to Firestore")
    parser.add_argument("url", help="YouTube URL to process")
    args = parser.parse_args()

    print(f"Processing URL: {args.url}")
    result = process_video_url(args.url)
    if result.get("status") == "ingested":
        print(f"Successfully uploaded {result['video_id']} to Firestore!")
