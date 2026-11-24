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
from typing import NamedTuple

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection  # noqa: E402
from services.clip_analyzer import Segment  # noqa: E402

OUTPUT_DIR = Path(r"D:\ClinicStudio\outputs")
REFERENCES_DIR = Path(r"D:\ClinicStudio\references")

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30
VIDEO_PRESET = "fast"
VIDEO_CRF = "19"
VIDEO_PROFILE = "high"
VIDEO_LEVEL = "4.1"
AUDIO_BITRATE = "128k"
AUDIO_RATE = "48000"
AUDIO_CHANNELS = "2"
HDR_TRANSFERS = frozenset({"arib-std-b67", "smpte2084"})
FRAME_FILTER = (
    f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1,fps={TARGET_FPS}"
)
HDR_TONEMAP_FILTER = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


class SourceProbe(NamedTuple):
    color_transfer: str | None
    has_audio: bool

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in HDR_TRANSFERS


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


def assemble_reel(
    segment_paths: list[Path],
    output_path: Path,
    *,
    lock_30fps: bool = False,
) -> None:
    """Concatenate pre-normalized clips into a single MP4 via the concat demuxer."""
    if not segment_paths:
        raise ValueError("assemble_reel requires at least one segment path")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / f"_concat_{uuid.uuid4().hex}.txt"
    try:
        lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        args = [
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
        ]
        if lock_30fps:
            # AAC priming gaps make concat copy report a non-30 avg_frame_rate.
            # Rewrite video timestamps onto a 90000/3000 grid without re-encoding.
            args.extend(
                [
                    "-bsf:v", "setts=pts=N*3000:dts=N*3000",
                    "-video_track_timescale", "90000",
                ]
            )
        args.extend(["-movflags", "+faststart", str(output_path)])
        run_ffmpeg(args)
    finally:
        list_file.unlink(missing_ok=True)


def _run_ffprobe(args: list[str], video_path: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["ffprobe", *args], capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "(no output)").strip()
        raise RuntimeError(f"ffprobe failed for {video_path.name}: {detail}")
    return result


def probe_duration(video_path: Path) -> float:
    """Return the container duration in seconds via ffprobe."""
    result = _run_ffprobe(
        [
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        video_path,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"ffprobe returned no duration for {video_path.name}")
    return float(result.stdout.strip())


def probe_source(video_path: Path) -> SourceProbe:
    """Read color_transfer and whether any audio stream exists. One probe per render."""
    result = _run_ffprobe(
        [
            "-v", "error",
            "-show_entries", "stream=codec_type,color_transfer",
            "-of", "json",
            str(video_path),
        ],
        video_path,
    )
    payload = json.loads(result.stdout or "{}")
    color_transfer: str | None = None
    has_audio = False
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "audio":
            has_audio = True
        elif stream.get("codec_type") == "video" and color_transfer is None:
            value = stream.get("color_transfer")
            if isinstance(value, str) and value:
                color_transfer = value
    return SourceProbe(color_transfer=color_transfer, has_audio=has_audio)


def video_filter_for(is_hdr: bool) -> str:
    """9:16 cover-crop. HDR sources are tone-mapped to bt709 before the scale."""
    if is_hdr:
        return f"{HDR_TONEMAP_FILTER},{FRAME_FILTER}"
    return FRAME_FILTER


def audio_filter_for(duration: float) -> str:
    fade_out_at = max(0.0, duration - 0.02)
    return f"afade=t=in:st=0:d=0.02,afade=t=out:st={fade_out_at:.3f}:d=0.02"


def render_segment(
    source: Path,
    start: float,
    duration: float,
    output_path: Path,
    *,
    is_hdr: bool,
    has_audio: bool,
) -> None:
    """Single-pass cut, tone-map, scale, and encode one segment for iOS Safari."""
    args: list[str] = [
        "-ss", f"{start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-vf", video_filter_for(is_hdr),
    ]
    if has_audio:
        args.extend(["-af", audio_filter_for(duration)])
    args.extend(
        [
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", VIDEO_CRF,
            "-profile:v", VIDEO_PROFILE,
            "-level", VIDEO_LEVEL,
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            # libx264 on this build writes the matrix from -colorspace, but
            # leaves primaries/transfer unset unless the VUI is stamped.
            "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
            "-video_track_timescale", "90000",
            "-avoid_negative_ts", "make_zero",
        ]
    )
    if has_audio:
        args.extend(
            [
                "-c:a", "aac",
                "-b:a", AUDIO_BITRATE,
                "-ar", AUDIO_RATE,
                "-ac", AUDIO_CHANNELS,
            ]
        )
    else:
        args.append("-an")
    args.append(str(output_path))
    run_ffmpeg(args)


def write_analysis_proxy(source: Path, dest: Path) -> None:
    """Small silent 480p proxy so Gemini is not sent the raw camera file."""
    run_ffmpeg(
        [
            "-i", str(source),
            "-vf", "scale=-2:480,fps=2",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-an",
            str(dest),
        ]
    )


def render_from_segments(
    source_video_path: Path,
    segments: list[Segment],
    output_filename: str | None = None,
) -> tuple[Path, float]:
    """Cut each highlight in one encode pass and concatenate into outputs/.

    Returns the output path and the probed duration of the finished reel.
    """
    if not segments:
        raise ValueError("render_from_segments requires at least one segment")
    if not source_video_path.is_file():
        raise FileNotFoundError(f"Source video not found: {source_video_path}")

    media = probe_source(source_video_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = output_filename or f"reel_v2_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / filename

    print(
        f"Rendering {len(segments)} segment(s) from {source_video_path.name} "
        f"(color_transfer={media.color_transfer}, hdr={media.is_hdr}, audio={media.has_audio})"
    )
    with tempfile.TemporaryDirectory(prefix="clinicstudio_v2_") as tmp:
        tmp_dir = Path(tmp)
        segment_paths: list[Path] = []
        for i, segment in enumerate(segments):
            start = segment.start_time
            duration = segment.end_time - segment.start_time
            rendered = tmp_dir / f"segment_{i}.mp4"
            print(
                f"  [{i + 1}/{len(segments)}] {start:.2f}s-{segment.end_time:.2f}s "
                f"({duration:.2f}s) {segment.action_description}"
            )
            render_segment(
                source_video_path,
                start,
                duration,
                rendered,
                is_hdr=media.is_hdr,
                has_audio=media.has_audio,
            )
            segment_paths.append(rendered)

        print(f"  Assembling {len(segment_paths)} segment(s) -> {output_path}")
        assemble_reel(segment_paths, output_path, lock_30fps=True)

    rendered_duration = probe_duration(output_path)
    print(f"Done: {output_path} ({rendered_duration:.2f}s)")
    return output_path, rendered_duration


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
