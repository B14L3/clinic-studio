"""Raw Footage Matcher: recommends the best-fit blueprint for a raw clip via Gemini Vision.

Uploads a raw footage clip to the Gemini Files API, analyzes its audio
(dialogue vs ambient) and visual pacing (fast procedural cuts vs steady
continuous demonstration), and recommends the best-matching blueprint
already stored in SQLite.
"""
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL = "gemini-3.6-flash"
# Base backoff seconds for retrying transient Gemini 503/UNAVAILABLE errors.
RETRY_DELAYS = [5, 12, 25, 45, 60]


class BlueprintMatch(BaseModel):
    recommended_blueprint_id: int
    blueprint_name: str
    confidence: float
    reasoning: str


def _fetch_blueprint_options() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, category, data_json FROM blueprints ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    options = []
    for r in rows:
        data = json.loads(r["data_json"])
        options.append(
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "total_duration": data.get("total_duration"),
                "pacing": data.get("pacing"),
                "average_cut_duration": data.get("average_cut_duration"),
                "segment_count": len(data.get("segments", [])),
                "audio_style": data.get("audio_style"),
            }
        )
    return options


def upload_and_wait(client: genai.Client, path: Path) -> types.File:
    print(f"  Uploading {path.name}...")
    # The SDK sets an X-Goog-Upload-File-Name header from os.path.basename()
    # whenever `file` is a path string, and that header must be ASCII. Upload
    # via a binary file handle instead to avoid crashing on non-ASCII filenames.
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


def match_blueprint(client: genai.Client, uploaded: types.File, options: list[dict]) -> BlueprintMatch:
    """Ask Gemini which blueprint best matches this clip; retries on 503/UNAVAILABLE."""
    options_block = "\n".join(
        f'- id={o["id"]}, name="{o["name"]}", category={o["category"]}, '
        f'pacing={o["pacing"]}, avg_cut={o["average_cut_duration"]}s, '
        f'segments={o["segment_count"]}, audio_style={o["audio_style"]}'
        for o in options
    )
    prompt = (
        "You are matching a raw, unedited clinic footage clip to the best-fitting editing "
        "blueprint from the list below. Analyze the clip's:\n"
        "- Audio: is there talking/dialogue present, or just ambient clinic sound?\n"
        "- Visuals: fast procedural micro-cuts, or a steady continuous demonstration?\n\n"
        f"Available blueprints:\n{options_block}\n\n"
        "Pick exactly one blueprint id from the list above as recommended_blueprint_id, and "
        "set blueprint_name to that blueprint's exact name string. Write the reasoning in "
        "clear, natural Hebrew (1-2 sentences)."
    )

    max_attempts = len(RETRY_DELAYS) + 1
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BlueprintMatch,
                ),
            )
            return BlueprintMatch.model_validate_json(response.text)
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


def recommend_blueprint_for_clip(source_path: Path) -> BlueprintMatch:
    """Upload a raw clip and return the best-matching blueprint from SQLite."""
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY missing from backend/.env")

    options = _fetch_blueprint_options()
    if not options:
        raise SystemExit("No blueprints found in studio.db to match against.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    uploaded = upload_and_wait(client, source_path)
    try:
        return match_blueprint(client, uploaded, options)
    finally:
        client.files.delete(name=uploaded.name)
        print(f"  Cleaned up uploaded file {uploaded.name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Recommend the best-fit blueprint for a raw clip.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(r"D:\ClinicStudio\references\treatment_flow\copy_C9E6677C-B027-40FA-81B1-64C1BCD9FB67.mp4"),
    )
    args = parser.parse_args()

    result = recommend_blueprint_for_clip(args.source)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
