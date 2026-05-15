from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import db.database as db
from api.youtube_uploader import upload_video

_scheduler = BackgroundScheduler(timezone="UTC")
_status_callback = None  # callable(post_id, status, message)


def set_status_callback(cb):
    global _status_callback
    _status_callback = cb


def _notify(post_id, status, message=""):
    if _status_callback:
        _status_callback(post_id, status, message)


def _run_upload(post_id: int):
    db.update_post_status(post_id, "uploading")
    _notify(post_id, "uploading")
    try:
        url = upload_video(post_id)
        _notify(post_id, "done", url)
    except Exception as e:
        db.update_post_status(post_id, "failed", error_message=str(e))
        _notify(post_id, "failed", str(e))


def schedule_post(post_id: int, run_at: datetime):
    job_id = f"post_{post_id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    _scheduler.add_job(
        _run_upload,
        trigger=DateTrigger(run_date=run_at),
        args=[post_id],
        id=job_id,
        misfire_grace_time=300,
    )


def cancel_post(post_id: int):
    job_id = f"post_{post_id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)


def load_pending_posts():
    posts = db.get_scheduled_posts(status="pending")
    now = datetime.utcnow()
    for post in posts:
        run_at = datetime.fromisoformat(post["scheduled_at"])
        if run_at > now:
            schedule_post(post["id"], run_at)


def start():
    if not _scheduler.running:
        _scheduler.start()
    load_pending_posts()


def shutdown():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
