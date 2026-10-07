"""Reel pipeline endpoints: blueprints, rules, and end-to-end reel generation."""
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import get_connection  # noqa: E402
from services.copy_generator import generate_reel_copy  # noqa: E402
from services.video_engine import OUTPUT_DIR, render_blueprint_test  # noqa: E402

CLINIC_STUDIO_ROOT = Path(r"D:\ClinicStudio")

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
