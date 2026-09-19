"""
Celery worker — background jobs (yt-dlp, image post-process, scheduled tasks)
"""
from celery import Celery
import os

BROKER = os.getenv("REDIS_URL", "redis://redis:6379/1")
BACKEND = os.getenv("REDIS_URL", "redis://redis:6379/2")

app = Celery("empire-worker", broker=BROKER, backend=BACKEND)


@app.task
def download_video(url: str, output_path: str):
    """Download video via yt-dlp."""
    import yt_dlp
    ydl_opts = {
        "outtmpl": output_path,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return {"status": "done", "output": output_path}


@app.task
def transcribe(audio_path: str):
    """Transcribe via whisper."""
    import subprocess
    result = subprocess.run(
        ["whisper", audio_path, "--model", "base", "--output_format", "json"],
        capture_output=True, text=True
    )
    return {"status": "done", "output": result.stdout}


@app.task
def send_email(to: str, subject: str, body: str):
    """Send email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", "noreply@empire.ai")
    msg["To"] = to

    host = os.getenv("SMTP_HOST")
    if not host:
        return {"status": "skipped", "reason": "SMTP not configured"}

    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
        s.send_message(msg)
    return {"status": "sent", "to": to}
