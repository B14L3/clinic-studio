---
name: copy-generator
description: Generate localized Hebrew hooks, captions, and city hashtags using Claude API
---

# Hebrew Copywriter Playbook

When generating social copy via Claude API, use model `claude-sonnet-4-6` (or `claude-haiku-4-5-20251001` for lightweight/low-latency JSON generation):
1. Target Audience: Local Israeli women looking for professional skincare/esthetics treatments.
2. Tone of Voice: Professional, warm, clean, no cheap sales hype or tacky emojis.
3. Required Output Format (Strict JSON):
   \\\json
   {
     "hooks": [
       "Option 1: Problem-focused (e.g., ??? ???? ???? ??????)",
       "Option 2: Treatment-focused (e.g., ??? ???? ????? ????? ??????)",
       "Option 3: Result-focused (e.g., ?????? ?????? ????)"
     ],
     "caption": "Concise Hebrew body text explaining what the treatment does and who it suits.",
     "cta": "Direct booking call to action pointing to link in bio or WhatsApp.",
     "hashtags": ["#?????_????", "#????????_???_??????", "#[City/Region]"]
   }
   \\\
4. Strict Rules:
   - Natural Hebrew phrasing only. Never translate literally from English.
   - Avoid generic spam tags. Keep hashtags under 8, focused on region and treatment.
