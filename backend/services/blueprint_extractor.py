"""Extract timing/pacing blueprints from reference videos using Gemini Vision.

Scans references/treatment_flow/ and references/voiceover_flow/ for .mp4 files,
uploads each to the Gemini Files API, requests a structured JSON blueprint
(schema per .cursor/skills/extract-blueprint/SKILL.md), and stores the result
in the local SQLite `blueprints` table.
"""
import os
import random
import sys
import time
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection, init_db  # noqa: E402

REFERENCES_DIR = Path(r"D:\ClinicStudio\references")
CATEGORY_FOLDERS = ["treatment_flow", "voiceover_flow"]
MODEL = "gemini-3.6-flash"
# Base backoff seconds for retrying transient Gemini 503/UNAVAILABLE errors.
# ~5s, 12s, 25s, 45s, 60s, each with +0-20% jitter.
RETRY_DELAYS = [5, 12, 25, 45, 60]

load_dotenv(BACKEND_DIR / ".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class Segment(BaseModel):
    timestamp_start: float
    timestamp_end: float
    role: str
    suggested_action: str


class Blueprint(BaseModel):
    blueprint_name: str
    total_duration: float
    average_cut_duration: float
    pacing: str
    segments: list[Segment]
    audio_style: str
    text_overlay_recommended: bool


PROMPT = (
    "Analyze this reference video for a beauty/aesthetics clinic social reel. "
    "Return a STRICT JSON blueprint describing cut timestamps, shot type/role, "
    "pacing, visual action, and audio role for each segment, matching exactly "
    "this schema: blueprint_name (string), total_duration (seconds), "
    "average_cut_duration (seconds, e.g. 0.6), pacing (fast|ultra-fast|smooth), "
    "segments (list of {timestamp_start, timestamp_end, role, suggested_action}), "
    "audio_style (chill_instrumental|trending_beat), text_overlay_recommended (bool)."
)


def find_mp4_files() -> list[tuple[Path, str]]:
    """Return (path, category) pairs for every .mp4 in the target folders."""
    found = []
    for category in CATEGORY_FOLDERS:
        folder = REFERENCES_DIR / category
        if not folder.is_dir():
            print(f"  [skip] {folder} does not exist")
            continue
        for mp4 in folder.glob("*.mp4"):
            found.append((mp4, category))
    return found


def upload_and_wait(client: genai.Client, path: Path) -> types.File:
    print(f"  Uploading {path.name}...")
    # The SDK sets an X-Goog-Upload-File-Name header from os.path.basename()
    # whenever `file` is a path string, and that header must be ASCII. Non-ASCII
    # filenames (e.g. Hebrew) crash httpx with no config to override it, so we
    # upload via a binary file handle instead to bypass that code path. The
    # real filename is still stored in our own SQLite `name` column.
    safe_alias = f"{uuid.uuid4().hex}{path.suffix}"
    with open(path, "rb") as f:
        uploaded = client.files.upload(
            file=f,
            config=types.UploadFileConfig(display_name=safe_alias, mime_type="video/mp4"),
        )
    while uploaded.state == types.FileState.PROCESSING:
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state != types.FileState.ACTIVE:
        raise RuntimeError(f"File {path.name} failed to process: state={uploaded.state}")
    return uploaded


def extract_blueprint(client: genai.Client, uploaded: types.File) -> Blueprint:
    """Request the structured blueprint, retrying with backoff+jitter on 503/UNAVAILABLE."""
    max_attempts = len(RETRY_DELAYS) + 1
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[uploaded, PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Blueprint,
                ),
            )
            return Blueprint.model_validate_json(response.text)
        except genai_errors.ServerError as e:
            is_unavailable = e.code == 503 or e.status == "UNAVAILABLE"
            if not is_unavailable or attempt == max_attempts:
                raise
            last_error = e
            base_delay = RETRY_DELAYS[attempt - 1]
            delay = base_delay + random.uniform(0, base_delay * 0.2)
            print(
                f"  [RETRY {attempt}/{len(RETRY_DELAYS)}] Gemini {e.code} {e.status}: "
                f"{e.message}. Waiting {delay:.1f}s..."
            )
            time.sleep(delay)
    raise last_error


def already_saved(name: str, category: str) -> bool:
    """Check whether a blueprint for this name+category is already in SQLite."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM blueprints WHERE name = ? AND category = ?",
            (name, category),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_blueprint(name: str, category: str, blueprint: Blueprint) -> None:
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM blueprints WHERE name = ? AND category = ?",
            (name, category),
        ).fetchone()
        data_json = blueprint.model_dump_json()
        if existing:
            conn.execute(
                "UPDATE blueprints SET data_json = ? WHERE id = ?",
                (data_json, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO blueprints (name, category, data_json) VALUES (?, ?, ?)",
                (name, category, data_json),
            )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY missing from backend/.env")

    init_db()
    client = genai.Client(api_key=GEMINI_API_KEY)

    videos = find_mp4_files()
    if not videos:
        print("No .mp4 files found in treatment_flow/ or voiceover_flow/.")
        return

    for path, category in videos:
        if already_saved(path.name, category):
            print(f"[SKIP] Already in database: {path.name}")
            continue

        print(f"\n=== {path.name} ({category}) ===")
        uploaded = upload_and_wait(client, path)
        try:
            blueprint = extract_blueprint(client, uploaded)
            save_blueprint(path.name, category, blueprint)
            print(
                f"  Saved blueprint: {blueprint.total_duration}s, "
                f"{len(blueprint.segments)} segments, pacing={blueprint.pacing}"
            )
        finally:
            client.files.delete(name=uploaded.name)
            print(f"  Cleaned up uploaded file {uploaded.name}")


if __name__ == "__main__":
    main()
