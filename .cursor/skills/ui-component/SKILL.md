---
name: ui-component
description: Guidelines for building sleek Next.js UI components tailored for an aesthetics clinic
---

# UI Component Playbook

When creating Next.js (App Router) + Tailwind CSS components:
1. Theme & Aesthetic:
   - Luxury, minimal esthetics palette (soft neutral stones, warm zinc, subtle gold/rose accents).
   - Clean dark/light mode toggle.
2. Component Requirements:
   - Use Lucide React icons (\lucide-react\).
   - Drag-and-drop file uploaders with file size/count counters.
   - Native HTML5 vertical video player (9:16 aspect preview).
   - 1-Click action buttons ('Faster cuts', 'Shorter caption', 'Copy Caption', 'Download MP4').
3. Error Handling:
   - Show clean toast notifications for uploads, renders, and clipboard actions.
   - Never break page layout if video metadata takes time to parse.
