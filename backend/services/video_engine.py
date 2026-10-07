"""Phase 2: Video Assembly Engine.

Slices raw footage per a blueprint's segment timings, normalizes each slice to
a consistent 9:16 vertical format, and concatenates them into a single reel
using the system FFmpeg binary via `subprocess`.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection  # noqa: E402

OUTPUT_DIR = Path(r"D:\ClinicStudio\outputs")
REFERENCES_DIR = Path(r"D:\ClinicStudio\references")

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30


def run_ffmpeg(args: list[str]) -> None:
    """Run the system ffmpeg binary with the given args, raising on failure."""
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode}): {' '.join(cmd)}\n{result.stderr[-2000:]}"
        )


def normalize_clip(input_path: Path, output_path: Path) -> None:
    """Force 1080x1920 (9:16), 30fps, libx264/aac, scaling+padding cleanly."""
    scale_pad = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1"
    )
    run_ffmpeg(
        [
            "-i", str(input_path),
            "-vf", scale_pad,
            "-r", str(TARGET_FPS),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
    )


def slice_clip(input_path: Path, start_time: float, duration: float, output_path: Path) -> None:
    """Extract a clean sub-clip; re-encodes to avoid frame-freeze/desync from stream copy."""
    run_ffmpeg(
        [
            "-ss", f"{start_time}",
            "-i", str(input_path),
            "-t", f"{duration}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ]
    )


def assemble_reel(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate pre-normalized clips into a single MP4 via the concat demuxer."""
    if not segment_paths:
        raise ValueError("assemble_reel requires at least one segment path")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / f"_concat_{uuid.uuid4().hex}.txt"
    try:
        lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        run_ffmpeg(
            [
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]
        )
    finally:
        list_file.unlink(missing_ok=True)


def _fetch_blueprint_segments(blueprint_id: int) -> list[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data_json FROM blueprints WHERE id = ?", (blueprint_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"No blueprint found with id={blueprint_id}")
    data = json.loads(row["data_json"])
    return data["segments"]


def render_blueprint_test(
    blueprint_id: int,
    source_video_path: Path,
    output_path: Path,
    max_segments: int = 3,
) -> None:
    """Slice the first N segments of a blueprint from source footage, normalize, and stitch."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = _fetch_blueprint_segments(blueprint_id)[:max_segments]
    if not segments:
        raise ValueError(f"Blueprint id={blueprint_id} has no segments")

    print(f"Blueprint {blueprint_id}: rendering {len(segments)} segment(s) from {source_video_path.name}")

    with tempfile.TemporaryDirectory(prefix="clinicstudio_render_") as tmp:
        tmp_dir = Path(tmp)
        normalized_paths = []
        for i, seg in enumerate(segments):
            start = seg["timestamp_start"]
            duration = seg["timestamp_end"] - seg["timestamp_start"]
            sliced = tmp_dir / f"slice_{i}.mp4"
            normalized = tmp_dir / f"norm_{i}.mp4"

            print(f"  [{i + 1}/{len(segments)}] {seg['role']}: {start}s - {seg['timestamp_end']}s ({duration:.1f}s)")
            slice_clip(source_video_path, start, duration, sliced)
            normalize_clip(sliced, normalized)
            normalized_paths.append(normalized)

        print(f"  Assembling {len(normalized_paths)} segment(s) -> {output_path}")
        assemble_reel(normalized_paths, output_path)

    print(f"Done: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a test reel from a blueprint + source video.")
    parser.add_argument("--blueprint-id", type=int, default=1)
    parser.add_argument(
        "--source",
        type=Path,
        default=REFERENCES_DIR / "treatment_flow" / "copy_C9E6677C-B027-40FA-81B1-64C1BCD9FB67.mp4",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "test_assemble.mp4")
    parser.add_argument("--max-segments", type=int, default=3)
    args = parser.parse_args()

    render_blueprint_test(args.blueprint_id, args.source, args.output, args.max_segments)
