"""SQLite connection helper and schema setup for Clinic Studio."""
import sqlite3
from pathlib import Path

DB_DIR = Path(r"D:\ClinicStudio\db")
DB_PATH = DB_DIR / "studio.db"


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection to studio.db, creating db/ if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the blueprints and rules tables if they don't already exist."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blueprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_text TEXT NOT NULL,
                category TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


DEFAULT_RULES: list[tuple[str, str]] = [
    (
        "tone",
        "Warm, professional, medical-esthetic authority, inviting, no aggressive sales jargon.",
    ),
    (
        "language",
        "Natural Israeli Hebrew (עברית טבעית ולא תרגום מכונה), feminine/neutral addressing "
        "where appropriate.",
    ),
    (
        "structure",
        "Hook (1-3s attention grabber), Value/Process (what the treatment solves), Result, "
        "and CTA (Direct message / booking link).",
    ),
    (
        "restrictions",
        'No unrealistic medical promises (e.g. "מעלים קמטים לתמיד"), focus on skin health, '
        "glow, and rejuvenation.",
    ),
]


def seed_rules() -> int:
    """Populate the rules table with default marketing guidelines if it's empty.

    Returns the number of rows inserted (0 if rules already exist).
    """
    conn = get_connection()
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM rules").fetchone()
        if count > 0:
            return 0
        conn.executemany(
            "INSERT INTO rules (rule_text, category) VALUES (?, ?)",
            [(rule_text, category) for category, rule_text in DEFAULT_RULES],
        )
        conn.commit()
        return len(DEFAULT_RULES)
    finally:
        conn.close()


BLUEPRINT_RENAMES: dict[int, str] = {
    1: "Ambient Treatment Flow (21 Micro-Cuts, Fast Paced)",
    2: "Voiceover Explainer (12 Cuts, Structured Pacing)",
}


def rename_blueprints() -> int:
    """Apply canonical display names to known blueprint ids. Returns rows updated."""
    conn = get_connection()
    try:
        updated = 0
        for blueprint_id, new_name in BLUEPRINT_RENAMES.items():
            cur = conn.execute(
                "UPDATE blueprints SET name = ? WHERE id = ?", (new_name, blueprint_id)
            )
            updated += cur.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")
    inserted = seed_rules()
    if inserted:
        print(f"Seeded {inserted} default rule(s) into the rules table.")
    else:
        print("rules table already has data; skipped seeding.")

    renamed = rename_blueprints()
    print(f"Renamed {renamed} blueprint(s).")
