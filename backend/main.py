import os
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
