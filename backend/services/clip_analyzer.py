"""Dynamic clip analyzer: Gemini proposes highlight timestamps for one raw clip.

V2 additive service. It does not read or write the V1 blueprints table.
"""
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
from pydantic import BaseModel, Field, model_validator

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
CLINIC_STUDIO_ROOT = Path(r"D:\ClinicStudio")

load_dotenv(BACKEND_DIR / ".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL = "gemini-3.6-flash"
RETRY_DELAYS = [5, 12, 25, 45, 60]
MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/mp4",
}

PROMPT = (
    "You are an expert aesthetic clinic video editor. Watch this raw footage. "
    "Identify 5 to 10 of the most visually engaging moments (e.g., applying mask, "
    "device pulsing, client smiling, satisfying aesthetic details). Return the exact "
    "start and end timestamps in seconds for each moment, ensuring cuts are between "
    "1.0 and 3.0 seconds long for a fast-paced reel. Order the segments chronologically. "
    "Write visual_summary_hebrew as 2-3 sentences of natural Israeli Hebrew describing "
    "the treatment's visual vibe, for a copywriter who will not see the video."
)


class Segment(BaseModel):
    start_time: float = Field(ge=0, description="Highlight start in seconds.")
    end_time: float = Field(ge=0, description="Highlight end in seconds. Must be 1.0-3.0s after start_time.")
    action_description: str = Field(description="What is visually happening.")

    @model_validator(mode="after")
    def cut_is_fast_paced(self) -> "Segment":
        duration = self.end_time - self.start_time
        if duration < 1.0 or duration > 3.0:
            raise ValueError(
                f"Cut must be 1.0-3.0s, got {duration:.2f}s "
                f"({self.start_time}-{self.end_time})"
            )
        return self


class ClipAnalysisResult(BaseModel):
    segments: list[Segment] = Field(
        min_length=5,
        max_length=10,
        description="5-10 highlight cuts, each 1.0-3.0 seconds.",
    )
    visual_summary_hebrew: str = Field(
        min_length=1,
        description="2-3 sentence Hebrew summary of the treatment's visual vibe.",
    )


def _resolve_video_path(video_path: str) -> Path:
    path = Path(video_path)
    if not path.is_absolute():
        path = CLINIC_STUDIO_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"Source video not found: {path}")
    return path


def upload_and_wait(client: genai.Client, path: Path) -> types.File:
    """Upload via a binary handle so non-ASCII filenames never hit the ASCII header."""
    print(f"  Uploading {path.name}...")
    mime_type = MIME_BY_SUFFIX.get(path.suffix.lower(), "video/mp4")
    safe_alias = f"{uuid.uuid4().hex}{path.suffix}"
    with open(path, "rb") as handle:
        uploaded = client.files.upload(
            file=handle,
            config=types.UploadFileConfig(display_name=safe_alias, mime_type=mime_type),
        )
    while uploaded.state == types.FileState.PROCESSING:
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state != types.FileState.ACTIVE:
        raise RuntimeError(f"File {path.name} failed to process: state={uploaded.state}")
    return uploaded


def _generate_analysis(client: genai.Client, uploaded: types.File) -> ClipAnalysisResult:
    max_attempts = len(RETRY_DELAYS) + 1
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[uploaded, PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ClipAnalysisResult,
                ),
            )
            return ClipAnalysisResult.model_validate_json(response.text)
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
    raise last_error  # pragma: no cover


def analyze_clip_for_highlights(video_path: str) -> ClipAnalysisResult:
    """Upload a raw clip, ask Gemini for highlight cuts, then delete the remote file."""
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY missing from backend/.env")

    source = _resolve_video_path(video_path)
    client = genai.Client(api_key=GEMINI_API_KEY)
    uploaded = upload_and_wait(client, source)
    try:
        return _generate_analysis(client, uploaded)
    finally:
        client.files.delete(name=uploaded.name)
        print(f"  Cleaned up uploaded file {uploaded.name}")
