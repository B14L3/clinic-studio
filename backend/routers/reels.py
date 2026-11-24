"""Reel pipeline endpoints: uploads, dynamic highlight analysis, and reel generation."""
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
    Segment,
    analyze_clip_for_highlights,
)
from services.copy_generator import generate_reel_copy  # noqa: E402
from services.jobs import JobAcceptedResponse, create_job, schedule_job  # noqa: E402
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
async def list_raw_clips() -> list[UploadResponse]:
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


def _run_analyze(source_path: str) -> dict:
    try:
        analysis = analyze_clip_for_highlights(source_path)
    except Exception as e:
        raise RuntimeError(f"Clip analysis failed: {e}") from e
    return AnalyzeReelResponse(
        segments=analysis.segments,
        visual_summary_hebrew=analysis.visual_summary_hebrew,
    ).model_dump()


@router.post("/reels/analyze", response_model=JobAcceptedResponse, status_code=202)
async def analyze_reel(req: AnalyzeReelRequest) -> JobAcceptedResponse:
    """Queue highlight detection so the phone can poll instead of holding the proxy open."""
    source_path = _resolve_source_path(req.source_video_path)
    job = create_job()
    schedule_job(job.job_id, _run_analyze, str(source_path))
    return JobAcceptedResponse(job_id=job.job_id, status="queued")


@router.get("/rules")
async def list_active_rules():
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


def _run_generate(
    source_path: str,
    segments: list[Segment],
    visual_summary: str | None,
    treatment_name: str,
    extra_notes: str | None,
    output_filename: str,
) -> dict:
    try:
        output_path, duration = render_from_segments(
            Path(source_path),
            segments,
            output_filename=output_filename,
        )
    except Exception as e:
        raise RuntimeError(f"Video assembly failed: {e}") from e

    try:
        copy = generate_reel_copy(
            treatment_name,
            extra_notes=extra_notes,
            visual_summary=visual_summary,
            segments=segments,
        )
    except Exception as e:
        raise RuntimeError(f"Copy generation failed: {e}") from e

    return GenerateReelResponse(
        status="success",
        video_path=str(output_path),
        filename=output_filename,
        video_url=f"/outputs/{output_filename}",
        duration=round(duration, 2),
        copywriting=CopyPayload(**copy.model_dump()),
    ).model_dump()


@router.post("/reels/generate", response_model=JobAcceptedResponse, status_code=202)
async def generate_reel(req: GenerateReelRequest) -> JobAcceptedResponse:
    """Queue the reel render and Hebrew copy, then let the client poll for the result."""
    if not req.segments:
        raise HTTPException(status_code=400, detail="At least one segment is required")

    source_path = _resolve_source_path(req.source_video_path)
    output_filename = f"reel_{uuid.uuid4().hex[:8]}.mp4"
    job = create_job()
    schedule_job(
        job.job_id,
        _run_generate,
        str(source_path),
        req.segments,
        req.visual_summary,
        req.treatment_name,
        req.extra_notes,
        output_filename,
    )
    return JobAcceptedResponse(job_id=job.job_id, status="queued")
