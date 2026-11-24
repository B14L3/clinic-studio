"""Hebrew copywriting for a rendered reel.

Generates a hook, caption, call to action, and hashtags via Claude, grounded in
the active marketing rules in SQLite and the visual summary from clip analysis.
"""
import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from anthropic.types import Message
from dotenv import load_dotenv
from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection  # noqa: E402
from services.clip_analyzer import Segment  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# claude-sonnet-5-5 rejects forced tool_choice type "tool". tool_choice "auto"
# plus an explicit tool instruction returns a valid ReelCopy with no 400.
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

COPY_TOOL = {
    "name": "generate_copy",
    "description": "Structured Hebrew social media copy for a clinic treatment reel.",
    "input_schema": {
        "type": "object",
        "properties": {
            "on_screen_hook": {
                "type": "string",
                "description": "Short, punchy Hebrew headline for the video text overlay, max 5 words.",
            },
            "caption": {
                "type": "string",
                "description": (
                    "Engaging 3-4 sentence Instagram caption in natural Hebrew, with emojis "
                    "and paragraph breaks."
                ),
            },
            "call_to_action": {
                "type": "string",
                "description": "Clean Hebrew call-to-action pointing to booking/consultation.",
            },
            "hashtags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 5,
                "maxItems": 8,
                "description": "5-8 relevant Hebrew and English hashtags.",
            },
        },
        "required": ["on_screen_hook", "caption", "call_to_action", "hashtags"],
    },
}


class ReelCopy(BaseModel):
    on_screen_hook: str
    caption: str
    call_to_action: str
    hashtags: list[str]


def _fetch_active_rules() -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT rule_text FROM rules WHERE is_active = 1").fetchall()
    finally:
        conn.close()
    return [r["rule_text"] for r in rows]


def generate_reel_copy(
    treatment_type: str,
    extra_notes: str | None = None,
    visual_summary: str | None = None,
    segments: list[Segment] | None = None,
) -> ReelCopy:
    """Generate structured Hebrew reel copy for a treatment, grounded in active SQLite rules."""
    if not ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY missing from backend/.env")

    rules = _fetch_active_rules()
    rules_block = "\n".join(f"- {r}" for r in rules) if rules else "(no active rules defined)"

    vision_block = ""
    if visual_summary and segments:
        scene_lines = "\n".join(f"  - {segment.action_description}" for segment in segments)
        vision_block = (
            "\n\nThe video contains the following scenes:\n"
            f"{scene_lines}\n"
            f"Overall visual summary: {visual_summary}\n"
            "Ground the caption in these specific visual moments."
        )

    notes_block = f"\n\nAdditional notes: {extra_notes}" if extra_notes else ""

    system_prompt = (
        "You are a Hebrew social media copywriter for a luxury esthetics clinic in Israel. "
        "Follow the marketing rules strictly and write only natural, native Israeli Hebrew "
        "(never machine-translated). You must call the generate_copy tool. Do not answer with prose."
    )
    user_prompt = (
        f"Treatment: {treatment_type}\n\n"
        f"Marketing rules to follow:\n{rules_block}"
        f"{vision_block}"
        f"{notes_block}\n\n"
        "Write the on-screen hook, caption, call-to-action, and hashtags for this treatment's reel."
    )

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = _create_copy_message(client, system_prompt, user_prompt)
    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None or tool_use.name != "generate_copy":
        raise RuntimeError("Claude did not call generate_copy")
    return ReelCopy.model_validate(tool_use.input)


def _create_copy_message(client: Anthropic, system_prompt: str, user_prompt: str) -> Message:
    return client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[COPY_TOOL],
        tool_choice={"type": "auto"},
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Hebrew reel copy for a treatment.")
    parser.add_argument("--treatment", type=str, default="טיפול זוהר והחדרת לחות")
    parser.add_argument("--notes", type=str, default=None)
    args = parser.parse_args()

    result = generate_reel_copy(args.treatment, extra_notes=args.notes)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
