import os
import json
import argparse
import tempfile
import yt_dlp
import whisper
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_ytdlp_cookie_opts() -> dict:
    opts = {}
    cookies_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if cookies_browser:
        if ":" in cookies_browser:
            browser_name, browser_profile = cookies_browser.split(":", 1)
            opts["cookiesfrombrowser"] = (browser_name.strip(), browser_profile.strip())
        else:
            opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts

def process_video(url: str):
    print(f"Processing URL: {url}")

    with tempfile.TemporaryDirectory() as temp_dir:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        ydl_opts.update(get_ytdlp_cookie_opts())

        # 1. Download Audio & Get Metadata
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info['id']
            title = info.get('title', 'Unknown Title')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            
            audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
            if not os.path.exists(audio_path):
                 for file in os.listdir(temp_dir):
                    if file.startswith(video_id):
                        audio_path = os.path.join(temp_dir, file)
                        break
            
            print(f"Downloaded: {title} ({video_id})")

            # 2. Transcribe
            print("Transcribing...")
            model = whisper.load_model("base")
            result = model.transcribe(audio_path, word_timestamps=True)
            
            # 3. Format Transcript
            segments = result.get('segments', [])
            words = []
            for segment in segments:
                for word_info in segment.get('words', []):
                    words.append({
                        "word": word_info['word'],
                        "start": word_info['start'],
                        "end": word_info['end']
                    })
            
            # 4. Upload to Firestore
            doc_ref = db.collection("videos").document(video_id)
            doc_ref.set({
                "video_id": video_id,
                "title": title,
                "thumbnailUrl": thumbnail,
                "duration": duration,
                "words": words,
                "full_text": result.get('text', ''),
                "createdAt": firestore.SERVER_TIMESTAMP
            })
            
            print(f"Successfully uploaded {video_id} to Firestore!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest YouTube video to Firestore")
    parser.add_argument("url", help="YouTube URL to process")
    args = parser.parse_args()
    
    process_video(args.url)
