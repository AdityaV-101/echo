"""Part 2 Step 1 regression tests: the per-request diagnostic logging and
DEBUG_KEEP_AUDIO capture that Part 1 found completely missing (which is why
the real jamie incident couldn't be root-caused - the audio was deleted and
nothing was logged). Every test here targets a specific piece of that gap and
would fail against the pre-Step-1 code (no FeatureExplanation, no calibration
source info, no describe_received/describe_array, no debug_audio capture, no
artifact-load logging).
"""
import json
import shutil
import uuid

import pytest

import child_calibration
import decision
from audio_preprocess import describe_array, describe_received, probe_container
from features import PositionFeatures, WordFeatures

from conftest import EVAL_DIR, BACKEND_DIR


def _fake_position(expected="M", position="single", llr_best_origin="canonical", top_competitor=None) -> PositionFeatures:
    return PositionFeatures(
        index=0, expected=expected,
        llr_best=-0.5, llr_best_origin=llr_best_origin, llr_deletion=None,
        llr_second_best=-1.0, llr_margin=0.5,
        gop_i=-1.0, gop_lpr_i=1.0, top_competitor=top_competitor,
        dur_z=1.0, entropy=0.5, raw_span=(0, 5),
        position=position, syllable_count=1, frame_count_word=20,
    )


def _fake_word(canonical=("M",)) -> WordFeatures:
    pos = _fake_position()
    return WordFeatures(
        canonical=list(canonical), ll_canonical_per_frame=-0.5,
        free_decode_gap=0.2, frame_count=20, positions=[pos],
    )


# --- calibration source reporting (child_calibration.speaker_relative_features) ---

def test_fresh_user_reports_global_calibration_source():
    user_id = f"instr-test-{uuid.uuid4()}"
    raw = {"llr_best": -0.5, "gop_i": -1.0, "gop_lpr_i": 1.0, "dur_z": 1.0}
    relative, sources = child_calibration.speaker_relative_features(user_id, "M", raw)
    assert set(sources.keys()) == set(child_calibration.RELATIVE_FEATURES)
    for feat in child_calibration.RELATIVE_FEATURES:
        assert sources[feat]["source"] == "global"
        assert sources[feat]["n"] == 0
        assert f"{feat}_speaker_rel" in relative


def test_calibration_source_switches_to_speaker_after_min_samples():
    user_id = f"instr-test-{uuid.uuid4()}"
    raw = {"llr_best": -0.5, "gop_i": -1.0, "gop_lpr_i": 1.0, "dur_z": 1.0}
    for _ in range(child_calibration.MIN_SPEAKER_SAMPLES):
        child_calibration.update_baselines(user_id, "M", raw)
    _, sources = child_calibration.speaker_relative_features(user_id, "M", raw)
    for feat in child_calibration.RELATIVE_FEATURES:
        assert sources[feat]["source"] == "speaker"
        assert sources[feat]["n"] == child_calibration.MIN_SPEAKER_SAMPLES


def test_global_means_load_is_logged(caplog):
    child_calibration._GLOBAL_MEANS = None  # force a reload to observe the log line
    with caplog.at_level("INFO", logger="speechpal.child_calibration"):
        child_calibration._load_global_means()
    assert any("global calibration offset loaded" in r.message for r in caplog.records)


# --- decision.py: FeatureExplanation + artifact-load logging ---

def test_compute_error_probability_returns_full_explanation():
    user_id = f"instr-test-{uuid.uuid4()}"
    pos = _fake_position()
    word = _fake_word()
    p, explanation = decision.compute_error_probability(pos, word, user_id)
    model, scaler, encoder, metadata = decision._load()

    assert 0.0 <= p <= 1.0
    assert set(explanation.raw.keys()) == set(metadata["numeric_features"])
    assert set(explanation.scaled_numeric.keys()) == set(metadata["numeric_features"])
    assert set(explanation.categorical.keys()) == set(metadata["categorical_features"])
    assert set(explanation.calibration_sources.keys()) == set(child_calibration.RELATIVE_FEATURES)
    assert explanation.categorical["expected"] == "M"


def test_decide_attaches_explanation_to_attempt_decision():
    user_id = f"instr-test-{uuid.uuid4()}"
    pos = _fake_position()
    word = _fake_word()
    result = decision.decide(pos, word, user_id)
    assert result.explanation is not None
    assert result.explanation.raw  # non-empty
    assert result.status in ("correct", "unclear", "wrong")


def test_warm_up_functions_trigger_the_load_eagerly(caplog):
    # main.py calls these at process boot (not lazily on first request) so
    # the artifact-load confirmation actually appears in boot logs.
    decision._MODEL = decision._SCALER = decision._ENCODER = decision._METADATA = None
    child_calibration._GLOBAL_MEANS = None
    with caplog.at_level("INFO"):
        decision.warm_up()
        child_calibration.warm_up()
    messages = [r.message for r in caplog.records]
    assert any("phase3 classifier loaded" in m for m in messages)
    assert any("global calibration offset loaded" in m for m in messages)


def test_decision_artifact_load_is_logged(caplog):
    decision._MODEL = decision._SCALER = decision._ENCODER = decision._METADATA = None
    with caplog.at_level("INFO", logger="speechpal.decision"):
        decision._load()
    messages = [r.message for r in caplog.records]
    assert any("phase3 classifier loaded" in m and "sha256=" in m for m in messages)
    assert any("phase3 scaler loaded" in m and "sha256=" in m for m in messages)
    assert any("phase3 encoder loaded" in m and "sha256=" in m for m in messages)
    assert any("phase3 metadata loaded" in m and "sha256=" in m for m in messages)


def test_decide_logs_result_with_calibration_and_features(caplog):
    user_id = f"instr-test-{uuid.uuid4()}"
    pos = _fake_position()
    word = _fake_word()
    with caplog.at_level("INFO", logger="speechpal.decision"):
        decision.decide(pos, word, user_id)
    result_lines = [r.message for r in caplog.records if r.message.startswith("decide user_id=")]
    assert len(result_lines) == 1
    assert "calibration_sources=" in result_lines[0]
    assert "raw=" in result_lines[0]
    assert "scaled_numeric=" in result_lines[0]


# --- audio_preprocess.py: describe_received / describe_array / probe_container ---

def test_describe_array_on_known_signal():
    import numpy as np
    silence = np.zeros(16000, dtype=np.float32)
    stats = describe_array(silence)
    assert stats["duration_s"] == pytest.approx(1.0)
    assert stats["rms"] == 0.0
    assert stats["peak"] == 0.0

    tone = np.ones(8000, dtype=np.float32)
    stats2 = describe_array(tone)
    assert stats2["duration_s"] == pytest.approx(0.5)
    assert stats2["peak"] == pytest.approx(1.0)
    assert stats2["rms"] == pytest.approx(1.0)


def test_describe_received_reports_real_container_metadata():
    wav_path = str(EVAL_DIR / "audio" / "cat_correct.wav")
    stats = describe_received(wav_path)
    assert stats["sample_rate"] == 22050
    assert stats["channels"] == 1
    assert stats["duration_s"] == pytest.approx(0.985, abs=0.02)
    assert stats["rms"] is not None and stats["rms"] > 0


def test_probe_container_handles_missing_file_gracefully():
    # ffprobe exits nonzero on a missing file but still emits valid (empty)
    # JSON, so probe_container comes back with explicit None fields rather
    # than raising - assert it never raises and never fabricates a value.
    result = probe_container("/nonexistent/path/does_not_exist.wav")
    assert result.get("codec") is None
    assert result.get("sample_rate") is None
    # describe_received must not raise either, even with no valid container info
    stats = describe_received("/nonexistent/path/does_not_exist.wav")
    assert isinstance(stats, dict)


# --- DEBUG_KEEP_AUDIO end-to-end capture ---

def test_score_word_persists_debug_audio_only_when_flag_set(monkeypatch, tmp_path):
    import scorer_phase3

    debug_dir = tmp_path / "debug_audio"
    monkeypatch.setattr(scorer_phase3, "_DEBUG_AUDIO_DIR", debug_dir)
    wav_path = str(EVAL_DIR / "audio" / "cat_correct.wav")

    user_off = f"instr-debugoff-{uuid.uuid4()}"
    monkeypatch.setattr(scorer_phase3, "DEBUG_KEEP_AUDIO", False)
    scorer_phase3.score_word(wav_path, "cat", target_phoneme="K", position="initial", user_id=user_off)
    assert not (debug_dir / user_off).exists()

    user_on = f"instr-debugon-{uuid.uuid4()}"
    monkeypatch.setattr(scorer_phase3, "DEBUG_KEEP_AUDIO", True)
    scorer_phase3.score_word(wav_path, "cat", target_phoneme="K", position="initial", user_id=user_on)
    assert (debug_dir / user_on).exists()
    attempt_dirs = list((debug_dir / user_on).iterdir())
    assert len(attempt_dirs) == 1
    files = {p.name for p in attempt_dirs[0].iterdir()}
    assert "received.wav" in files
    assert "converted.wav" in files
    assert "record.json" in files

    record = json.loads((attempt_dirs[0] / "record.json").read_text())
    assert record["word"] == "cat"
    assert record["target_phoneme"] == "K"
    assert record["user_id"] == user_on
    assert record["received"]["sample_rate"] == 22050
    assert "raw_features" in record and record["raw_features"]
    assert "calibration_sources" in record and record["calibration_sources"]
