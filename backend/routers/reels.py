"""Reel pipeline endpoints: blueprints, rules, uploads, and end-to-end reel generation."""
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import get_connection  # noqa: E402
from services.blueprint_matcher import recommend_blueprint  # noqa: E402
from services.copy_generator import generate_reel_copy  # noqa: E402
from services.video_engine import OUTPUT_DIR, render_blueprint_test  # noqa: E402

CLINIC_STUDIO_ROOT = Path(r"D:\ClinicStudio")
RAW_CLIPS_DIR = CLINIC_STUDIO_ROOT / "raw_clips"
RAW_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".m4v"}

router = APIRouter()


class GenerateReelRequest(BaseModel):
    blueprint_id: int
    source_video_path: str
    treatment_type: str
    extra_notes: Optional[str] = None


class CopyPayload(BaseModel):
    on_screen_hook: str
    caption: str
    call_to_action: str
    hashtags: list[str]


class GenerateReelResponse(BaseModel):
    status: str
    video_path: str
    filename: str
    video_url: str
    duration: float
    copywriting: CopyPayload


class AnalyzeReelRequest(BaseModel):
    source_video_path: str


class BlueprintOption(BaseModel):
    id: int
    name: str
    category: str
    duration: Optional[float] = None
    segment_count: int


class AnalyzeReelResponse(BaseModel):
    recommended_blueprint_id: int
    blueprint_name: str
    confidence: float
    reasoning: str
    blueprints: list[BlueprintOption]


class UploadResponse(BaseModel):
    filename: str
    file_path: str
    size_mb: float


def _sanitize_filename(name: str) -> str:
    """Strip path separators and keep only safe filename characters."""
    base = Path(name).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return safe or "clip"


@router.post("/upload", response_model=UploadResponse)
async def upload_raw_clip(file: UploadFile = File(...)):
    """Accept a raw video upload (mobile camera roll or local file) and store it in raw_clips/."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_filename(file.filename or "clip")
    filename = f"{timestamp}_{uuid.uuid4().hex[:8]}_{safe_name}"
    dest_path = RAW_CLIPS_DIR / filename

    size_bytes = 0
    with open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
            size_bytes += len(chunk)

    return UploadResponse(
        filename=filename,
        file_path=f"raw_clips/{filename}",
        size_mb=round(size_bytes / (1024 * 1024), 2),
    )


@router.get("/raw-clips", response_model=list[UploadResponse])
def list_raw_clips():
    """List previously uploaded raw clips in raw_clips/, newest first."""
    files = sorted(RAW_CLIPS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        UploadResponse(
            filename=f.name,
            file_path=f"raw_clips/{f.name}",
            size_mb=round(f.stat().st_size / (1024 * 1024), 2),
        )
        for f in files
        if f.is_file()
    ]


@router.get("/blueprints")
def list_blueprints():
    """Return all extracted blueprints: id, name, category, duration, segment count."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, category, data_json FROM blueprints ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        data = json.loads(r["data_json"])
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "duration": data.get("total_duration"),
                "segment_count": len(data.get("segments", [])),
            }
        )
    return result


@router.post("/reels/analyze", response_model=AnalyzeReelResponse)
def analyze_reel(req: AnalyzeReelRequest):
    """Analyze a raw clip via Gemini and recommend the best-fit blueprint,
    returning the full blueprint list too so the frontend can override it."""
    source_path = _resolve_source_path(req.source_video_path)

    try:
        match = recommend_blueprint(str(source_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blueprint matching failed: {e}") from e

    return AnalyzeReelResponse(
        recommended_blueprint_id=match.recommended_blueprint_id,
        blueprint_name=match.blueprint_name,
        confidence=match.confidence,
        reasoning=match.reasoning,
        blueprints=[BlueprintOption(**b) for b in list_blueprints()],
    )


@router.get("/rules")
def list_active_rules():
    """Return all active copywriting rules."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, rule_text, category, is_active FROM rules WHERE is_active = 1 ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _fetch_blueprint_data(blueprint_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data_json FROM blueprints WHERE id = ?", (blueprint_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Blueprint id={blueprint_id} not found")
    return json.loads(row["data_json"])


def _resolve_source_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = CLINIC_STUDIO_ROOT / path
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Source video not found: {path}")
    return path


def _ffprobe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


@router.post("/reels/generate", response_model=GenerateReelResponse)
def generate_reel(req: GenerateReelRequest):
    """Assemble the full blueprint into a reel and generate matching Hebrew copy."""
    source_path = _resolve_source_path(req.source_video_path)
    blueprint_data = _fetch_blueprint_data(req.blueprint_id)
    segment_count = len(blueprint_data.get("segments", []))
    if segment_count == 0:
        raise HTTPException(status_code=400, detail=f"Blueprint id={req.blueprint_id} has no segments")

    output_filename = f"reel_{req.blueprint_id}_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / output_filename

    try:
        render_blueprint_test(
            blueprint_id=req.blueprint_id,
            source_video_path=source_path,
            output_path=output_path,
            max_segments=segment_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video assembly failed: {e}") from e

    try:
        copy = generate_reel_copy(req.treatment_type, req.blueprint_id, req.extra_notes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copy generation failed: {e}") from e

    duration = _ffprobe_duration(output_path)

    return GenerateReelResponse(
        status="success",
        video_path=str(output_path),
        filename=output_filename,
        video_url=f"/outputs/{output_filename}",
        duration=round(duration, 2),
        copywriting=CopyPayload(**copy.model_dump()),
    )
