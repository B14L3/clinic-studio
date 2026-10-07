"""Phase 3: Hebrew Copywriting Service.

Generates structured Hebrew social copy (on-screen hook, caption, CTA,
hashtags) for a given treatment type via Claude, grounded in the active
marketing rules in SQLite and optionally a blueprint's timing/pacing so
on-screen text can be aligned to the edit.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from database import get_connection  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-sonnet-4-6"

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


def _fetch_blueprint_timeline(blueprint_id: int) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data_json FROM blueprints WHERE id = ?", (blueprint_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        print(f"  [warn] blueprint_id={blueprint_id} not found; continuing without timing context")
        return None

    bp = json.loads(row["data_json"])
    segments = bp.get("segments", [])
    timeline = "\n".join(
        f"  {s['timestamp_start']}s-{s['timestamp_end']}s: {s['role']} - {s['suggested_action']}"
        for s in segments
    )
    return f"Video duration={bp.get('total_duration')}s, pacing={bp.get('pacing')}\n{timeline}"


def generate_reel_copy(
    treatment_type: str,
    blueprint_id: Optional[int] = None,
    extra_notes: Optional[str] = None,
) -> ReelCopy:
    """Generate structured Hebrew reel copy for a treatment, grounded in active SQLite rules."""
    if not ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY missing from backend/.env")

    rules = _fetch_active_rules()
    rules_block = "\n".join(f"- {r}" for r in rules) if rules else "(no active rules defined)"

    blueprint_block = ""
    if blueprint_id is not None:
        timeline = _fetch_blueprint_timeline(blueprint_id)
        if timeline:
            blueprint_block = f"\n\nAlign the on-screen hook timing to this edit:\n{timeline}"

    notes_block = f"\n\nAdditional notes: {extra_notes}" if extra_notes else ""

    system_prompt = (
        "You are a Hebrew social media copywriter for a luxury esthetics clinic in Israel. "
        "Follow the marketing rules strictly and write only natural, native Israeli Hebrew "
        "(never machine-translated). Call the generate_copy tool with your answer."
    )
    user_prompt = (
        f"Treatment: {treatment_type}\n\n"
        f"Marketing rules to follow:\n{rules_block}"
        f"{blueprint_block}"
        f"{notes_block}\n\n"
        "Write the on-screen hook, caption, call-to-action, and hashtags for this treatment's reel."
    )

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[COPY_TOOL],
        tool_choice={"type": "tool", "name": "generate_copy"},
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    return ReelCopy.model_validate(tool_use.input)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Hebrew reel copy for a treatment.")
    parser.add_argument("--treatment", type=str, default="טיפול זוהר והחדרת לחות")
    parser.add_argument("--blueprint-id", type=int, default=None)
    parser.add_argument("--notes", type=str, default=None)
    args = parser.parse_args()

    result = generate_reel_copy(args.treatment, args.blueprint_id, args.notes)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
