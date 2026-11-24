"""Reel assembly: one encode pass per highlight, then a concat-copy of those segments."""
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
from services.clip_analyzer import Segment  # noqa: E402

OUTPUT_DIR = Path(r"D:\ClinicStudio\outputs")

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


def assemble_reel(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate already-encoded segments with the concat demuxer.

    Do not rewrite packet PTS here. setts=pts=N*3000 follows decode order and
    scrambles B-frame display order on High profile H.264.
    """
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
        assemble_reel(segment_paths, output_path)

    rendered_duration = probe_duration(output_path)
    print(f"Done: {output_path} ({rendered_duration:.2f}s)")
    return output_path, rendered_duration
