import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import db
from scorer_common import canonical_phonemes_for_word

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("speechpal.main")

# Default ON, per eval/phase3_protocol.md's "What ships by default": GOP
# z-score's measured child-slice FRR (19-20%, eval/baselines.json) already
# violates the project's own FRR<=0.05 constraint by ~4x; this pipeline's
# operating point respects that budget (FRR=0.0485, see RESULTS.md's
# "Phase 5 operating point, corrected"). Set USE_PHASE3_SCORER=0 to fall
# back to the GOP z-score path (USE_REAL_SCORER=1) or the stub.
USE_PHASE3_SCORER = os.environ.get("USE_PHASE3_SCORER", "1") == "1"
USE_REAL_SCORER = os.environ.get("USE_REAL_SCORER") == "1"
if USE_PHASE3_SCORER:
    from scorer_phase3 import score_word
    import child_calibration
    import decision

    logger.info(
        "Using PHASE 3 scorer (paired-LLR/GOP features -> frozen classifier -> "
        "abstention-heavy decision, see eval/phase3_protocol.md). Set USE_PHASE3_SCORER=0 to opt out."
    )
    # Force the frozen-artifact loads (and their hash/shape log lines - Part
    # 1c found these were correct but silent) to happen now, at boot, rather
    # than lazily on whichever request happens to be first.
    decision.warm_up()
    child_calibration.warm_up()
elif USE_REAL_SCORER:
    from scorer import score_word

    logger.info("Using REAL scorer (wav2vec2 phoneme recognizer, GOP + z-score) - known to exceed the FRR<=0.05 budget on the child slice.")
else:
    from scorer_stub import score_word

    logger.info("Using STUB scorer (fake results). Set USE_REAL_SCORER=1 or USE_PHASE3_SCORER=1 for a real one.")

DATA_DIR = Path(__file__).parent / "data"
with open(DATA_DIR / "levels.json") as f:
    LEVELS = json.load(f)
with open(DATA_DIR / "practice_tracks.json") as f:
    PRACTICE_TRACKS = json.load(f)

LEVEL_BY_NUMBER = {lvl["level"]: lvl for lvl in LEVELS}

# Phonemes that get a dedicated practice track and a recommendation card when
# a child struggles with them repeatedly in the leveled curriculum.
RECOMMENDABLE_PHONEMES = set(PRACTICE_TRACKS.keys())
RECOMMENDATION_THRESHOLD = 3

db.init_db()

# /api/health reports healthy only once this is true. USE_PHASE3_SCORER and
# USE_REAL_SCORER are the two paths that depend on gop_scorer's wav2vec2
# model (a ~1.2GB download when not already cached in the image); the stub
# scorer has nothing to warm up, so it's considered ready immediately.
_scorer_ready = {"value": not (USE_PHASE3_SCORER or USE_REAL_SCORER)}


def _warm_up_wav2vec2() -> None:
    """Loads the wav2vec2 phoneme recognizer and runs one dummy inference
    through the exact same code path a real request uses, so weight-loading
    and any first-call framework overhead (CPU kernel selection, etc.) both
    happen here rather than on whichever request happens to arrive first.
    Runs in a thread off the event loop (see lifespan below) so /api/health
    stays reachable - and correctly reports "not ready yet" - for the whole
    time this is in progress, instead of the port not even accepting
    connections until it finishes."""
    import numpy as np
    from gop_scorer import compute_log_probs, get_model

    logger.info("Warm-up: loading wav2vec2 phoneme recognizer (facebook/wav2vec2-lv-60-espeak-cv-ft)...")
    processor, model, *_ = get_model()
    logger.info("Warm-up: running one dummy inference...")
    compute_log_probs(processor, model, np.zeros(16000, dtype=np.float32))
    _scorer_ready["value"] = True
    logger.info("Warm-up complete - scorer is ready to serve requests.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _scorer_ready["value"]:
        loop = asyncio.get_event_loop()
        app.state.warmup_task = loop.run_in_executor(None, _warm_up_wav2vec2)
    yield


app = FastAPI(title="Echo API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _full_progress(user_id: str) -> dict:
    user = db.get_or_create_user(user_id)
    level_progress = db.get_level_progress(user_id)
    phoneme_errors = db.get_phoneme_errors(user_id)
    recommendations = [
        {"phoneme": pe["phoneme"], "error_count": pe["error_count"]}
        for pe in phoneme_errors
        if pe["phoneme"] in RECOMMENDABLE_PHONEMES and pe["error_count"] >= RECOMMENDATION_THRESHOLD
    ]
    return {
        "user": user,
        "level_progress": level_progress,
        "phoneme_errors": phoneme_errors,
        "recommendations": recommendations,
    }


@app.post("/api/login")
def login(payload: dict):
    user_id = (payload.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="An ID is required.")
    db.get_or_create_user(user_id)
    return _full_progress(user_id)


@app.get("/api/progress/{user_id}")
def get_progress(user_id: str):
    return _full_progress(user_id)


@app.get("/api/levels")
def get_levels():
    return LEVELS


@app.get("/api/practice-tracks")
def get_practice_tracks():
    return PRACTICE_TRACKS


@app.post("/api/settings")
def update_settings(payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required.")
    speak_aloud = 1 if payload.get("speak_aloud") else 0
    speech_rate = float(payload.get("speech_rate", 0.8))
    speech_rate = max(0.5, min(1.0, speech_rate))
    app_speech_enabled = 1 if payload.get("app_speech_enabled", True) else 0
    accent_tolerance_enabled = None
    if "accent_tolerance_enabled" in payload:
        accent_tolerance_enabled = 1 if payload.get("accent_tolerance_enabled") else 0
    db.update_settings(user_id, speak_aloud, speech_rate, app_speech_enabled, accent_tolerance_enabled)
    return db.get_or_create_user(user_id)


@app.post("/api/score")
async def score(
    user_id: str = Form(...),
    word: str = Form(...),
    level: str | None = Form(None),
    phonemes_override: str | None = Form(None),
    target_phoneme: str | None = Form(None),
    position: str | None = Form(None),
    audio: UploadFile = File(...),
):
    override_list = None
    if phonemes_override:
        try:
            override_list = json.loads(phonemes_override)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="phonemes_override must be JSON list.")

    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    user = db.get_or_create_user(user_id)
    accent_tolerance_enabled = bool(user.get("accent_tolerance_enabled", 1))

    try:
        try:
            result = score_word(
                tmp_path,
                word,
                phonemes_override=override_list,
                target_phoneme=target_phoneme,
                position=position,
                user_id=user_id,
                accent_tolerance_enabled=accent_tolerance_enabled,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    # An unusable recording (Phase 4's gate) was never actually scored - it
    # doesn't count as an attempt and has no percent_correct to record.
    if result.get("status") == "unclear_recording":
        return result

    db.record_attempt(user_id, word, level, result["percent_correct"], result["results"])

    # "wrong" is a confirmed error; "borderline" is genuinely ambiguous and
    # "accent_variant"/"correct" are explicitly not errors - only "wrong"
    # feeds the recommendation-card error count.
    for r in result["results"]:
        if r["status"] == "wrong" and r["expected"]:
            db.increment_phoneme_error(user_id, r["expected"])

    # Deliberately does NOT advance level_progress here: practice allows
    # unlimited retries on a word, so "attempted" and "done, move on" are
    # separate actions. See /api/levels/{level}/advance for the latter.
    return result


@app.post("/api/levels/{level}/advance")
def advance_level(level: int, payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required.")
    if level not in LEVEL_BY_NUMBER:
        raise HTTPException(status_code=404, detail="Level not found.")
    total_words = len(LEVEL_BY_NUMBER[level]["words"])
    progress = db.advance_level_progress(user_id, level, total_words, len(LEVELS))
    return progress


@app.get("/api/therapist/review-queue")
def therapist_review_queue(user_id: str | None = None):
    """Phase 5's CHILD-FACING-threshold events only (status="wrong",
    precision=0.500 at that operating point) - see backend/decision.py."""
    return db.get_therapist_review_queue(user_id)


@app.get("/api/therapist/top-k")
def therapist_top_k(k: int = 25, user_id: str | None = None):
    """Phase 5's THERAPIST-QUEUE operating point: no precision floor, every
    recorded attempt ranked by calibrated probability - a broader, lower-
    precision review list than /review-queue's child-facing-threshold
    events. See RESULTS.md's recall/precision-at-top-K table for what a
    given K actually catches."""
    return db.get_top_k_by_probability(k, user_id)


@app.get("/api/therapist/calibration/{user_id}")
def therapist_calibration(user_id: str):
    """This child's running per-phoneme baseline (child_calibration.py's
    Welford mean/std of GOP scores, updated after every scored attempt in
    decision.decide) - what their speaker-relative features are computed
    against. db.get_all_speaker_baselines already existed; this route
    (added after the frontend's therapist view was built against a
    mock-only stand-in - see frontend/DESIGN_NOTES.md's Part 8/Part 9
    notes) is the only piece that was missing."""
    return db.get_all_speaker_baselines(user_id)


@app.get("/api/phoneme-lookup")
def phoneme_lookup(word: str):
    phonemes = canonical_phonemes_for_word(word)
    return {"word": word, "found": phonemes is not None, "phonemes": phonemes}


@app.get("/api/custom-sets/{user_id}")
def list_custom_sets(user_id: str):
    return db.get_custom_sets(user_id)


@app.post("/api/custom-sets")
def create_custom_set(payload: dict):
    user_id = payload.get("user_id")
    name = (payload.get("name") or "").strip()
    if not user_id or not name:
        raise HTTPException(status_code=400, detail="user_id and name are required.")
    set_id = db.create_custom_set(user_id, name)
    return db.get_custom_set_by_id(set_id)


@app.post("/api/custom-sets/{set_id}/words")
def add_custom_word(set_id: int, payload: dict):
    custom_set = db.get_custom_set_by_id(set_id)
    if custom_set is None:
        raise HTTPException(status_code=404, detail="Custom set not found.")
    word = (payload.get("word") or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="word is required.")
    manual_override = payload.get("phonemes_override")
    found_phonemes = canonical_phonemes_for_word(word)
    override_to_store = None
    if found_phonemes is None:
        if manual_override:
            override_to_store = json.dumps(manual_override)
        # else: stored with no phonemes; scoring will fail clearly until one is added.
    db.add_custom_word(set_id, word, override_to_store)
    return {
        "custom_set": db.get_custom_set_by_id(set_id),
        "lookup": {"found": found_phonemes is not None, "phonemes": found_phonemes},
    }


@app.delete("/api/custom-sets/{set_id}")
def delete_custom_set(set_id: int):
    if db.get_custom_set_by_id(set_id) is None:
        raise HTTPException(status_code=404, detail="Custom set not found.")
    db.delete_custom_set(set_id)
    return {"deleted": True}


@app.delete("/api/custom-words/{word_id}")
def delete_custom_word(word_id: int):
    db.delete_custom_word(word_id)
    return {"deleted": True}


@app.get("/api/health")
def health():
    if not _scorer_ready["value"]:
        return JSONResponse(status_code=503, content={"status": "starting", "real_scorer": USE_REAL_SCORER})
    return {"status": "ok", "real_scorer": USE_REAL_SCORER}


# The Dockerfile builds the frontend and copies it to frontend_dist, a
# sibling of this backend/ directory - see the Dockerfile's final COPY.
# Mounted last (Starlette matches routes in registration order) so it never
# shadows any /api/* route above; it just serves index.html/assets for
# everything else. Absent entirely in local dev (no Docker build has run),
# which is fine - Vite's dev server serves the frontend there instead.
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend_dist"
if _FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info("Serving built frontend from %s", _FRONTEND_DIST)
