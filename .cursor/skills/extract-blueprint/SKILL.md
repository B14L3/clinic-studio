---
name: extract-blueprint
description: Analyze reference viral reels via Gemini Vision to create timing and pacing JSON blueprints
---

# Video Blueprint Extractor Playbook

When extracting blueprints from reference videos in \D:\ClinicStudio\references\:
1. Use Google Gemini API multimodal capabilities (pass raw MP4 directly). Prefer the Pro tier (`gemini-3.1-pro`, aliased by `gemini-3.6-pro`/`gemini-2.5-pro`/`gemini-pro-latest`) for best video reasoning quality; fall back to `gemini-3.6-flash` if the Pro tier returns a quota/billing error (429 RESOURCE_EXHAUSTED) or a 404 on the current API key.
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
