---
name: extract-blueprint
description: Analyze reference viral reels via Gemini Vision to create timing and pacing JSON blueprints
---

# Video Blueprint Extractor Playbook

When extracting blueprints from reference videos in \D:\ClinicStudio\references\:
1. Use Google Gemini 1.5 Pro API multimodal capabilities (pass raw MP4 directly).
2. Prompt Gemini to return STRICT JSON with this schema:
   \\\json
   {
     "blueprint_name": "string",
     "total_duration": "number (seconds)",
     "average_cut_duration": "number (e.g. 0.6)",
     "pacing": "fast | ultra-fast | smooth",
     "segments": [
       {"timestamp_start": 0.0, "timestamp_end": 2.5, "role": "hook_visual", "suggested_action": "macro close-up"},
       {"timestamp_start": 2.5, "timestamp_end": 26.0, "role": "treatment_flow", "suggested_action": "micro-cuts of steps"},
       {"timestamp_start": 26.0, "timestamp_end": 30.0, "role": "final_result", "suggested_action": "glowing skin reveal"}
     ],
     "audio_style": "chill_instrumental | trending_beat",
     "text_overlay_recommended": false
   }
   \\\
3. Store the output in SQLite (\D:\ClinicStudio\db\studio.db\) in the \lueprints\ table.
