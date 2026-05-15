import json
import os
from typing import Callable, Optional
from googleapiclient.http import MediaFileUpload
from auth.youtube_auth import get_youtube_service
import db.database as db

CATEGORY_ID = "22"  # People & Blogs — универсальная категория
CHUNK_SIZE = 256 * 1024 * 8  # 2 MB chunks


def upload_video(
    post_id: int,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> str:
    """
    Upload a scheduled post to YouTube.
    Returns the YouTube video URL on success.
    Raises on error.
    """
    post = db.get_scheduled_post(post_id)
    if not post:
        raise ValueError(f"Scheduled post {post_id} not found")

    credentials_json = post["credentials_json"]
    youtube, updated_creds = get_youtube_service(credentials_json)

    db.update_account_credentials(post["account_id"], json.dumps(updated_creds))

    tags = [t.strip() for t in post["tags"].split(",") if t.strip()]

    title = post["title"]
    if post["video_type"] == "short" and "#Shorts" not in title:
        title = title + " #Shorts"

    body = {
        "snippet": {
            "title": title[:100],
            "description": post["description"],
            "tags": tags,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": post["privacy"],
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        post["file_path"],
        chunksize=CHUNK_SIZE,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and progress_callback:
            pct = int(status.progress() * 100)
            progress_callback(pct)

    if progress_callback:
        progress_callback(100)

    video_id = response["id"]

    if post["thumbnail_path"] and os.path.exists(post["thumbnail_path"]):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(post["thumbnail_path"]),
            ).execute()
        except Exception:
            pass

    url = f"https://www.youtube.com/watch?v={video_id}"
    db.update_post_status(post_id, "done", youtube_video_id=video_id, post_url=url)
    return url
