"""Prepare the local web demo from downloaded CRIA data and saved model outputs."""
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SOURCE = ROOT / "data/videos/wrist/chunk-000/episode_000149.mp4"


def prepare():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("Install FFmpeg and add it to PATH.")
    if not SOURCE.is_file():
        raise SystemExit("Run python download_data.py --demo-only first.")

    for script in ("export_cria_review_demo.py", "export_cria_live_demo.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True)

    episode = WEB / "episode-149.mp4"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(SOURCE),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(episode),
    ], check=True)
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "10", "-i", str(episode),
        "-frames:v", "1", str(WEB / "poster.jpg"),
    ], check=True)


if __name__ == "__main__":
    prepare()
