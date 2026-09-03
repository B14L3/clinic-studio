---
name: ffmpeg-cutter
description: Trim, assemble, and render vertical reels from raw clips using FFmpeg
---

# FFmpeg Video Cutter Playbook

When cutting and assembling footage from \D:\ClinicStudio\raw\ into \D:\ClinicStudio\outputs\:
1. Video Specifications:
   - Aspect Ratio: Vertical 9:16 (1080x1920)
   - Codec: H.264 (libx264)
   - Pixel Format: yuv420p (for Instagram compatibility)
   - Frame Rate: 30 fps
2. Micro-Cut Logic:
   - For high-retention treatment reels, cut each raw clip to 0.4s–0.8s.
   - Use clean hard cuts (no wipes, dissolves, or cheesy transitions).
3. Scale & Crop Filter:
   - Force center crop to 1080x1920 if source resolution varies:
     \scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920\
4. Concat Execution:
   - Use FFmpeg concat demuxer or complex filtergraph.
   - Strip original shaky camera audio if chill music background is intended.
