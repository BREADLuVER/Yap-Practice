import os
import tempfile
import json
import shutil
from urllib.parse import parse_qs, urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import firebase_admin
from firebase_admin import auth, credentials, firestore

app = FastAPI()

# Initialize Firebase
# Use service account if available locally, otherwise default credentials (Cloud Run)
service_account_path = "serviceAccountKey.json"
if os.path.exists(service_account_path):
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred)
else:
    firebase_admin.initialize_app()

db = firestore.client()

def get_allowed_origins() -> list[str]:
    origins = os.getenv("ALLOWED_ORIGINS", "")
    if origins.strip():
        return [origin.strip() for origin in origins.split(",") if origin.strip()]
    return ["http://localhost:3000"]


def get_allowed_origin_regex() -> str | None:
    regex = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip()
    if regex:
        return regex
    return None

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_origin_regex=get_allowed_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Whisper model (lazy loading or startup)
model = None

def get_model():
    global model
    if model is None:
        import whisper

        print("Loading Whisper model...")
        model = whisper.load_model("base") # Use base model for speed
    return model

class VideoRequest(BaseModel):
    url: str


class PracticedUpdateRequest(BaseModel):
    practiced: bool


def get_authenticated_uid(request: Request) -> str:
    authorization_header = request.headers.get("Authorization", "").strip()
    if not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    id_token = authorization_header.removeprefix("Bearer ").strip()
    if not id_token:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")

    try:
        decoded_token = auth.verify_id_token(id_token)
    except Exception as error:
        print(f"Invalid Firebase token: {error}")
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase ID token") from error

    uid = str(decoded_token.get("uid", "")).strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Authenticated token did not include a user id")

    return uid

@app.get("/")
def read_root():
    return {"message": "NorthernLingo Backend is running!"}

@app.get("/api/videos")
def list_videos():
    """List all available videos from Firestore."""
    try:
        docs = db.collection("videos").stream()
        videos = []
        for doc in docs:
            data = doc.to_dict()
            # Return only necessary fields for the list view
            videos.append({
                "video_id": data.get("video_id"),
                "title": data.get("title"),
                "thumbnailUrl": data.get("thumbnailUrl"),
                "duration": data.get("duration"),
                "createdAt": data.get("createdAt"),
                "viewCount": data.get("viewCount", 0),
            })

        videos.sort(
            key=lambda video: (
                int(video.get("viewCount") or 0),
                str(video.get("createdAt") or ""),
            ),
            reverse=True,
        )
        return videos
    except Exception as e:
        print(f"Error listing videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    """Get full details for a specific video."""
    try:
        doc_ref = db.collection("videos").document(video_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Video not found")
        return doc.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/me/practiced")
def get_practiced_videos(request: Request, videoIds: str | None = None):
    uid = get_authenticated_uid(request)
    progress_collection = db.collection("users").document(uid).collection("clip_progress")

    try:
        requested_video_ids: list[str] = []
        if videoIds:
            requested_video_ids = [
                video_id.strip()
                for video_id in videoIds.split(",")
                if video_id.strip()
            ]
            requested_video_ids = list(dict.fromkeys(requested_video_ids))

        practiced_video_ids: list[str] = []
        if requested_video_ids:
            for video_id in requested_video_ids:
                progress_doc = progress_collection.document(video_id).get()
                if not progress_doc.exists:
                    continue

                progress_data = progress_doc.to_dict() or {}
                if bool(progress_data.get("practiced")):
                    practiced_video_ids.append(video_id)
        else:
            for progress_doc in progress_collection.stream():
                progress_data = progress_doc.to_dict() or {}
                if bool(progress_data.get("practiced")):
                    practiced_video_ids.append(progress_doc.id)

        return {"practiced": practiced_video_ids}
    except HTTPException:
        raise
    except Exception as error:
        print(f"Error fetching practiced videos for user {uid}: {error}")
        raise HTTPException(status_code=500, detail="Unable to fetch practiced videos") from error


@app.put("/api/users/me/practiced/{video_id}")
def update_practiced_video(video_id: str, payload: PracticedUpdateRequest, request: Request):
    normalized_video_id = video_id.strip()
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="video_id is required")

    uid = get_authenticated_uid(request)
    progress_doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("clip_progress")
        .document(normalized_video_id)
    )

    try:
        if payload.practiced:
            progress_doc_ref.set(
                {
                    "video_id": normalized_video_id,
                    "practiced": True,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
        else:
            progress_doc_ref.delete()

        return {"video_id": normalized_video_id, "practiced": payload.practiced}
    except Exception as error:
        print(f"Error updating practiced state for user {uid}, video {normalized_video_id}: {error}")
        raise HTTPException(status_code=500, detail="Unable to update practiced state") from error

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

TRANSCRIPTS_DIR = "transcripts"
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def get_ytdlp_cookie_opts() -> dict:
    opts: dict = {}

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


def get_base_ydl_opts() -> dict:
    opts = {
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


def extract_video_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if "youtube.com" in host:
        query = parse_qs(parsed.query)
        video_ids = query.get("v", [])
        if video_ids and video_ids[0]:
            return video_ids[0]
        if path.startswith("shorts/"):
            return path.split("/", 1)[1]

    if "youtu.be" in host and path:
        return path.split("/")[0]

    return None

@app.post("/api/process")
async def process_video(request: VideoRequest):
    # Deprecated: This endpoint is kept for reference/admin use but the frontend will primarily use /api/videos
    url = request.url
    print(f"Processing URL: {url}")

    try:
        import yt_dlp

        # Fast path: if we can parse video id directly, check cache first
        parsed_video_id = extract_video_id_from_url(url)
        if parsed_video_id:
            parsed_cache_path = os.path.join(TRANSCRIPTS_DIR, f"{parsed_video_id}.json")
            if os.path.exists(parsed_cache_path):
                print(f"Loading from cache: {parsed_cache_path}")
                with open(parsed_cache_path, "r") as f:
                    return json.load(f)

        # 0. Extract Video ID first (fast)
        with yt_dlp.YoutubeDL(get_base_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = info["id"]
            title = info.get("title", "Unknown Title")

        # Check cache
        cache_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
        if os.path.exists(cache_path):
            print(f"Loading from cache: {cache_path}")
            with open(cache_path, "r") as f:
                return json.load(f)

        # 1. Download Audio
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                **get_base_ydl_opts(),
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
                with open(cache_path, "w") as f:
                    json.dump(response_data, f)
                
                return response_data

    except Exception as e:
        message = str(e)
        print(f"Error processing video: {message}")

        if "Sign in to confirm you're not a bot" in message or "cookies-from-browser" in message:
            raise HTTPException(
                status_code=400,
                detail=(
                    "YouTube blocked automated download for this request. "
                    "Set YTDLP_COOKIES_FROM_BROWSER (example: chrome or edge:Default) "
                    "or YTDLP_COOKIES_FILE in backend environment and retry."
                ),
            )

        raise HTTPException(status_code=500, detail=message)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
