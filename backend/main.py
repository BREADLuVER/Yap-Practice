import os
import tempfile
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import whisper
import uvicorn

app = FastAPI()


def get_allowed_origins() -> list[str]:
    origins = os.getenv("ALLOWED_ORIGINS", "")
    if origins.strip():
        return [origin.strip() for origin in origins.split(",") if origin.strip()]
    return ["http://localhost:3000"]

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Whisper model (lazy loading or startup)
model = None

def get_model():
    global model
    if model is None:
        print("Loading Whisper model...")
        model = whisper.load_model("base") # Use base model for speed
    return model

class VideoRequest(BaseModel):
    url: str

@app.get("/")
def read_root():
    return {"message": "NorthernLingo Backend is running!"}

import shutil

def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg is not installed or not in PATH.")
        # In a real app, we might want to exit or warn
        return False
    return True

@app.on_event("startup")
async def startup_event():
    check_ffmpeg()
    # Preload model if desired, or keep lazy
    # get_model()

import json

TRANSCRIPTS_DIR = "transcripts"
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

@app.post("/api/process")
async def process_video(request: VideoRequest):
    url = request.url
    print(f"Processing URL: {url}")

    try:
        # 0. Extract Video ID first (fast)
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = info['id']
            title = info.get('title', 'Unknown Title')

        # Check cache
        cache_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
        if os.path.exists(cache_path):
            print(f"Loading from cache: {cache_path}")
            with open(cache_path, 'r') as f:
                return json.load(f)

        # 1. Download Audio
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

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # We already have info, but download needs to run
                ydl.download([url])
                audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
                
                # Check if file exists (sometimes extension might differ)
                if not os.path.exists(audio_path):
                     # fallback to find the file
                    for file in os.listdir(temp_dir):
                        if file.startswith(video_id):
                            audio_path = os.path.join(temp_dir, file)
                            break
                
                print(f"Audio downloaded to: {audio_path}")

                # 2. Transcribe
                model = get_model()
                result = model.transcribe(audio_path, word_timestamps=True)
                
                # 3. Format Response
                segments = result.get('segments', [])
                words = []
                for segment in segments:
                    for word_info in segment.get('words', []):
                        words.append({
                            "word": word_info['word'],
                            "start": word_info['start'],
                            "end": word_info['end']
                        })
                
                response_data = {
                    "video_id": video_id,
                    "title": title,
                    "words": words,
                    "full_text": result.get('text', '')
                }

                # Save to cache
                with open(cache_path, 'w') as f:
                    json.dump(response_data, f)
                
                return response_data

    except Exception as e:
        print(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
