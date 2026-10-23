"""Reel pipeline endpoints: uploads, dynamic highlight analysis, and reel generation."""
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import get_connection  # noqa: E402
from services.clip_analyzer import (  # noqa: E402
    ClipAnalysisResult,
    Segment,
    analyze_clip_for_highlights,
)
from services.copy_generator import generate_reel_copy  # noqa: E402
from services.video_engine import OUTPUT_DIR, render_from_segments  # noqa: E402

CLINIC_STUDIO_ROOT = Path(r"D:\ClinicStudio")
RAW_CLIPS_DIR = CLINIC_STUDIO_ROOT / "raw_clips"
RAW_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".m4v"}

router = APIRouter()


class GenerateReelRequest(BaseModel):
    source_video_path: str
    segments: list[Segment]
    visual_summary: str | None = None
    treatment_name: str
    extra_notes: str | None = None


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


class AnalyzeReelResponse(BaseModel):
    segments: list[Segment]
    visual_summary_hebrew: str


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
async def analyze_reel(req: AnalyzeReelRequest):
    """Watch a raw clip and return editable highlight cuts plus a Hebrew visual summary."""
    source_path = _resolve_source_path(req.source_video_path)

    try:
        analysis: ClipAnalysisResult = analyze_clip_for_highlights(str(source_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clip analysis failed: {e}") from e

    return AnalyzeReelResponse(
        segments=analysis.segments,
        visual_summary_hebrew=analysis.visual_summary_hebrew,
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


def _resolve_source_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = CLINIC_STUDIO_ROOT / path
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Source video not found: {path}")
    return path


@router.post("/reels/generate", response_model=GenerateReelResponse)
async def generate_reel(req: GenerateReelRequest):
    """Slice the edited highlight list into a reel and write Hebrew copy from that context."""
    if not req.segments:
        raise HTTPException(status_code=400, detail="At least one segment is required")

    source_path = _resolve_source_path(req.source_video_path)
    output_filename = f"reel_{uuid.uuid4().hex[:8]}.mp4"

    try:
        output_path, duration = render_from_segments(
            source_path,
            req.segments,
            output_filename=output_filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video assembly failed: {e}") from e

    try:
        copy = generate_reel_copy(
            req.treatment_name,
            extra_notes=req.extra_notes,
            visual_summary=req.visual_summary,
            segments=req.segments,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copy generation failed: {e}") from e

    return GenerateReelResponse(
        status="success",
        video_path=str(output_path),
        filename=output_filename,
        video_url=f"/outputs/{output_filename}",
        duration=round(duration, 2),
        copywriting=CopyPayload(**copy.model_dump()),
    )
