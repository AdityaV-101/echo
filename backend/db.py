"""SQLite persistence layer for SpeechPal. Plain sqlite3, no ORM."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# DATABASE_PATH points at Render's persistent disk (mounted at /var/data) in
# production - see render.yaml - so the sqlite file survives redeploys
# instead of living in the container's ephemeral filesystem. Defaults to the
# old next-to-this-file location for local/dev runs.
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(Path(__file__).parent / "speechpal.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    current_level INTEGER NOT NULL DEFAULT 1,
    speak_aloud INTEGER NOT NULL DEFAULT 1,
    speech_rate REAL NOT NULL DEFAULT 0.8,
    app_speech_enabled INTEGER NOT NULL DEFAULT 1,
    accent_tolerance_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    word TEXT NOT NULL,
    level TEXT,
    percent_correct INTEGER NOT NULL,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phoneme_errors (
    user_id TEXT NOT NULL,
    phoneme TEXT NOT NULL,
    error_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, phoneme)
);

CREATE TABLE IF NOT EXISTS custom_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    phonemes_override TEXT
);

CREATE TABLE IF NOT EXISTS level_progress (
    user_id TEXT NOT NULL,
    level TEXT NOT NULL,
    words_completed INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, level)
);

-- Per-speaker, per-phoneme running GOP baseline (Step 4 of the GOP rebuild:
-- score against the speaker's own voice, not a fixed reference). mean_gop
-- and std_gop are exactly what their names say; m2 is Welford's-algorithm
-- scratch state (sum of squared deviations from the running mean) needed to
-- update mean/std incrementally without ever re-scanning history - it isn't
-- meant to be read directly, std_gop is already the derived, queryable
-- value. See calibration.py's welford_update.
CREATE TABLE IF NOT EXISTS speaker_baseline (
    user_id TEXT NOT NULL,
    phoneme TEXT NOT NULL,
    mean_gop REAL NOT NULL,
    std_gop REAL NOT NULL,
    n INTEGER NOT NULL,
    m2 REAL NOT NULL,
    PRIMARY KEY (user_id, phoneme)
);

-- Per-user counts of confirmed phonological-process errors (see
-- hypothesis_scorer.py's Bayesian prior). "Confirmed" means the hypothesis
-- scorer's own verdict on an attempt was definitive (word_status="wrong",
-- not "unclear") and the winning candidate came from this named process -
-- there's no separate therapist-confirmation step. Used to raise that
-- process's prior for this user's future attempts, since a child's errors
-- tend to be systematic: if they front K->T once they likely do it
-- consistently, and the system should become more (not less) willing to
-- believe that hypothesis again for them specifically.
CREATE TABLE IF NOT EXISTS user_process_counts (
    user_id TEXT NOT NULL,
    process TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (user_id, process)
);

-- Phase 3/5: per-user, per-phoneme running baseline for each of the
-- classifier's speaker-relative features (llr_best, gop_i, gop_lpr_i,
-- dur_z - see backend/child_calibration.py), Welford accumulator per
-- (user, phoneme, feature) triple. Generic (feature name is a column, not
-- a dedicated table per feature) since Phase 3 defines exactly these four
-- but a future phase adding a fifth shouldn't need a schema migration.
CREATE TABLE IF NOT EXISTS feature_baseline (
    user_id TEXT NOT NULL,
    phoneme TEXT NOT NULL,
    feature TEXT NOT NULL,
    n INTEGER NOT NULL,
    mean_value REAL NOT NULL,
    m2 REAL NOT NULL,
    PRIMARY KEY (user_id, phoneme, feature)
);

-- Phase 5: k-of-n evidence aggregation history. One row per single-attempt
-- verdict at a given target phoneme, oldest-first per (user, phoneme) -
-- backend/decision.py windows the last n to decide whether a tentative
-- "candidate_wrong" verdict is corroborated enough to confirm.
CREATE TABLE IF NOT EXISTS attempt_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    phoneme TEXT NOT NULL,
    status TEXT NOT NULL,
    probability REAL NOT NULL,
    word TEXT,
    created_at TEXT NOT NULL
);

-- Phase 5: confirmed errors (k-of-n corroborated), for the therapist panel.
-- Never populated from a single attempt - see backend/decision.py.
CREATE TABLE IF NOT EXISTS therapist_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    phoneme TEXT NOT NULL,
    n_wrong INTEGER NOT NULL,
    n_window INTEGER NOT NULL,
    mean_probability REAL NOT NULL,
    word TEXT,
    created_at TEXT NOT NULL,
    reviewed INTEGER NOT NULL DEFAULT 0
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Without this, a connection that finds the database locked by another
    # concurrent writer raises sqlite3.OperationalError immediately instead
    # of waiting - a short wait is enough given each get_conn() block is a
    # single short-lived write, and makes any concurrent-write path in this
    # file (not just get_or_create_user's fix below) more robust.
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Lightweight migration for databases created before this column
        # existed: CREATE TABLE IF NOT EXISTS above is a no-op on a table
        # that already exists, so an already-running app's existing users.db
        # needs the column added explicitly. Safe to attempt unconditionally
        # since sqlite raises (harmlessly, caught below) if it's already there.
        try:
            conn.execute("ALTER TABLE users ADD COLUMN app_speech_enabled INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN accent_tolerance_enabled INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE attempt_history ADD COLUMN word TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE therapist_review_queue ADD COLUMN word TEXT")
        except sqlite3.OperationalError:
            pass


def get_or_create_user(user_id: str) -> dict:
    """SELECT-then-INSERT used to race: two concurrent requests for the
    same brand-new user_id (which React StrictMode's double-effect-
    invocation triggers on every first login in dev, and a double-tap or
    a second tab could trigger in production) could both see no row and
    both attempt the INSERT, and the second raised
    sqlite3.IntegrityError: UNIQUE constraint failed: users.id -
    reproduced directly with two concurrent requests before this fix.
    ON CONFLICT DO NOTHING makes the insert atomic and idempotent: if a
    concurrent request already created the row, this one is a no-op
    instead of an error, and the SELECT below always finds a row either
    way."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (id, created_at, current_level, speak_aloud, speech_rate, app_speech_enabled, accent_tolerance_enabled) "
            "VALUES (?, ?, 1, 1, 0.8, 1, 1) ON CONFLICT (id) DO NOTHING",
            (user_id, now_iso()),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


def update_settings(
    user_id: str,
    speak_aloud: int,
    speech_rate: float,
    app_speech_enabled: int,
    accent_tolerance_enabled: int | None = None,
):
    with get_conn() as conn:
        if accent_tolerance_enabled is None:
            conn.execute(
                "UPDATE users SET speak_aloud = ?, speech_rate = ?, app_speech_enabled = ? WHERE id = ?",
                (speak_aloud, speech_rate, app_speech_enabled, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET speak_aloud = ?, speech_rate = ?, app_speech_enabled = ?, accent_tolerance_enabled = ? WHERE id = ?",
                (speak_aloud, speech_rate, app_speech_enabled, accent_tolerance_enabled, user_id),
            )


def get_speaker_baseline(user_id: str, phoneme: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT phoneme, mean_gop, std_gop, n, m2 FROM speaker_baseline WHERE user_id = ? AND phoneme = ?",
            (user_id, phoneme),
        ).fetchone()
        return dict(row) if row else None


def get_all_speaker_baselines(user_id: str) -> dict[str, dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT phoneme, mean_gop, std_gop, n, m2 FROM speaker_baseline WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["phoneme"]: dict(r) for r in rows}


def get_user_process_counts(user_id: str) -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT process, count FROM user_process_counts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["process"]: r["count"] for r in rows}


def increment_user_process_count(user_id: str, process: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_process_counts (user_id, process, count) VALUES (?, ?, 1)
            ON CONFLICT (user_id, process) DO UPDATE SET count = count + 1
            """,
            (user_id, process),
        )


def upsert_speaker_baseline(user_id: str, phoneme: str, mean_gop: float, std_gop: float, n: int, m2: float):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO speaker_baseline (user_id, phoneme, mean_gop, std_gop, n, m2) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, phoneme) DO UPDATE SET mean_gop = ?, std_gop = ?, n = ?, m2 = ?
            """,
            (user_id, phoneme, mean_gop, std_gop, n, m2, mean_gop, std_gop, n, m2),
        )


def get_feature_baseline(user_id: str, phoneme: str, feature: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT n, mean_value, m2 FROM feature_baseline WHERE user_id = ? AND phoneme = ? AND feature = ?",
            (user_id, phoneme, feature),
        ).fetchone()
        return dict(row) if row else None


def upsert_feature_baseline(user_id: str, phoneme: str, feature: str, n: int, mean_value: float, m2: float):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO feature_baseline (user_id, phoneme, feature, n, mean_value, m2) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, phoneme, feature) DO UPDATE SET n = ?, mean_value = ?, m2 = ?
            """,
            (user_id, phoneme, feature, n, mean_value, m2, n, mean_value, m2),
        )


def record_attempt_history(user_id: str, phoneme: str, status: str, probability: float, word: str | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attempt_history (user_id, phoneme, status, probability, word, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, phoneme, status, probability, word, now_iso()),
        )


def get_recent_attempt_history(user_id: str, phoneme: str, limit: int) -> list[dict]:
    """Most recent `limit` attempts at this phoneme, oldest first (the
    order k-of-n windowing expects)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, probability, created_at FROM attempt_history "
            "WHERE user_id = ? AND phoneme = ? ORDER BY id DESC LIMIT ?",
            (user_id, phoneme, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def add_to_therapist_review_queue(
    user_id: str, phoneme: str, n_wrong: int, n_window: int, mean_probability: float, word: str | None = None
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO therapist_review_queue (user_id, phoneme, n_wrong, n_window, mean_probability, word, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, phoneme, n_wrong, n_window, mean_probability, word, now_iso()),
        )


def get_therapist_review_queue(user_id: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM therapist_review_queue WHERE user_id = ? ORDER BY created_at DESC", (user_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM therapist_review_queue ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_top_k_by_probability(k: int, user_id: str | None = None) -> list[dict]:
    """Phase 5's therapist-queue point: no precision floor, just a ranking
    of every recorded attempt by calibrated probability - the caller
    decides how deep to review (K=10/25/50, see RESULTS.md's recall/
    precision-at-top-K table). Distinct from therapist_review_queue, which
    only ever holds "wrong" (child-facing-threshold, nameable) events."""
    with get_conn() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM attempt_history WHERE user_id = ? ORDER BY probability DESC LIMIT ?",
                (user_id, k),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM attempt_history ORDER BY probability DESC LIMIT ?", (k,),
            ).fetchall()
        return [dict(r) for r in rows]


def update_current_level(user_id: str, level: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET current_level = ? WHERE id = ?", (level, user_id))


def record_attempt(user_id: str, word: str, level, percent_correct: int, results: list):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attempts (user_id, word, level, percent_correct, results_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, word, str(level) if level is not None else None, percent_correct, json.dumps(results), now_iso()),
        )


def increment_phoneme_error(user_id: str, phoneme: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO phoneme_errors (user_id, phoneme, error_count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, phoneme) DO UPDATE SET error_count = error_count + 1
            """,
            (user_id, phoneme),
        )


def get_phoneme_errors(user_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT phoneme, error_count FROM phoneme_errors WHERE user_id = ? ORDER BY error_count DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_level_progress(user_id: str) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT level, words_completed, completed FROM level_progress WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["level"]: dict(r) for r in rows}


def bump_level_progress(user_id: str, level: int, total_words: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT words_completed FROM level_progress WHERE user_id = ? AND level = ?",
            (user_id, str(level)),
        ).fetchone()
        if row is None:
            words_completed = 1
            conn.execute(
                "INSERT INTO level_progress (user_id, level, words_completed, completed) VALUES (?, ?, ?, ?)",
                (user_id, str(level), words_completed, 1 if words_completed >= total_words else 0),
            )
        else:
            words_completed = min(row["words_completed"] + 1, total_words)
            completed = 1 if words_completed >= total_words else 0
            conn.execute(
                "UPDATE level_progress SET words_completed = ?, completed = ? WHERE user_id = ? AND level = ?",
                (words_completed, completed, user_id, str(level)),
            )
        return words_completed


def create_custom_set(user_id: str, name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO custom_sets (user_id, name) VALUES (?, ?)", (user_id, name))
        return cur.lastrowid


def get_custom_sets(user_id: str) -> list:
    with get_conn() as conn:
        sets = conn.execute(
            "SELECT id, name FROM custom_sets WHERE user_id = ?", (user_id,)
        ).fetchall()
        result = []
        for s in sets:
            words = conn.execute(
                "SELECT id, word, phonemes_override FROM custom_words WHERE set_id = ?", (s["id"],)
            ).fetchall()
            result.append({"id": s["id"], "name": s["name"], "words": [dict(w) for w in words]})
        return result


def add_custom_word(set_id: int, word: str, phonemes_override: str | None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO custom_words (set_id, word, phonemes_override) VALUES (?, ?, ?)",
            (set_id, word, phonemes_override),
        )
        return cur.lastrowid


def get_custom_set_by_id(set_id: int) -> dict | None:
    with get_conn() as conn:
        s = conn.execute("SELECT id, user_id, name FROM custom_sets WHERE id = ?", (set_id,)).fetchone()
        if s is None:
            return None
        words = conn.execute(
            "SELECT id, word, phonemes_override FROM custom_words WHERE set_id = ?", (set_id,)
        ).fetchall()
        return {"id": s["id"], "user_id": s["user_id"], "name": s["name"], "words": [dict(w) for w in words]}


def delete_custom_set(set_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM custom_words WHERE set_id = ?", (set_id,))
        conn.execute("DELETE FROM custom_sets WHERE id = ?", (set_id,))


def delete_custom_word(word_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM custom_words WHERE id = ?", (word_id,))


def advance_level_progress(user_id: str, level: int, total_words: int, max_level: int) -> dict:
    """Mark one more word as completed for this level. Called exactly once per
    word transition (when the user chooses to move on), never once per score
    attempt, so unlimited retries on a single word don't skip ahead."""
    words_completed = bump_level_progress(user_id, level, total_words)
    completed = words_completed >= total_words
    if completed:
        user = get_or_create_user(user_id)
        if user["current_level"] == level:
            update_current_level(user_id, min(level + 1, max_level))
    return {"words_completed": words_completed, "completed": completed}
