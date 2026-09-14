import { useEffect, useState } from "react";
import { useApp } from "../lib/AppContext";
import FloatingDecor from "../components/FloatingDecor";
import * as api from "../lib/api";
import WordPractice from "./WordPractice";

const TABS = [
  { id: "queue", label: "Review Queue" },
  { id: "stats", label: "Phoneme Stats" },
  { id: "sets", label: "Custom Sets" },
  { id: "calibration", label: "Calibration" },
];

export default function TherapistMode({ onExit }) {
  const { userId, phonemeErrors } = useApp();
  const [tab, setTab] = useState("queue");
  const [sets, setSets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newSetName, setNewSetName] = useState("");
  const [activeSetId, setActiveSetId] = useState(null);
  const [practicingSet, setPracticingSet] = useState(null);
  const [confirmDeleteSetId, setConfirmDeleteSetId] = useState(null);

  const refreshSets = () => api.getCustomSets(userId).then(setSets);

  useEffect(() => {
    refreshSets().finally(() => setLoading(false));
  }, [userId]);

  const activeSet = sets.find((s) => s.id === activeSetId);

  const handleCreateSet = async (e) => {
    e.preventDefault();
    const name = newSetName.trim();
    if (!name) return;
    await api.createCustomSet(userId, name);
    setNewSetName("");
    refreshSets();
  };

  const handleDeleteSet = async (setId) => {
    await api.deleteCustomSet(setId);
    setConfirmDeleteSetId(null);
    refreshSets();
  };

  if (practicingSet) {
    const words = practicingSet.words.map((w) => ({
      word: w.word,
      phonemes_override: w.phonemes_override ? JSON.parse(w.phonemes_override) : undefined,
    }));
    return <WordPractice title={practicingSet.name} words={words} levelNumber={null} onExit={() => setPracticingSet(null)} />;
  }

  if (activeSet) {
    return (
      <CustomSetDetail
        customSet={activeSet}
        onBack={() => setActiveSetId(null)}
        onRefresh={refreshSets}
        onPractice={() => setPracticingSet(activeSet)}
      />
    );
  }

  return (
    <div className="screen screen-therapist">
      <FloatingDecor variant="home" />
      <div className="practice-top">
        <button className="btn-icon" onClick={onExit} aria-label="Back">
          ←
        </button>
        <h2 className="practice-title">Therapist Mode</h2>
      </div>

      <div className="therapist-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`therapist-tab ${tab === t.id ? "therapist-tab--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "queue" && <ReviewQueueTab userId={userId} />}
      {tab === "stats" && <PhonemeStatsTab phonemeErrors={phonemeErrors} />}
      {tab === "calibration" && <CalibrationTab userId={userId} />}

      {tab === "sets" && (
        <>
          <p className="therapist-help">
            Coverage for children with severe or atypical needs that the built-in curriculum does not cover. Build a
            custom word list for anything the standard levels don't address.
          </p>

          <form className="new-set-form" onSubmit={handleCreateSet}>
            <input
              className="text-input"
              placeholder="New word set name (e.g. Family names)"
              value={newSetName}
              onChange={(e) => setNewSetName(e.target.value)}
            />
            <button className="btn btn-secondary" type="submit">
              Create set
            </button>
          </form>

          {loading ? (
            <p>Loading...</p>
          ) : sets.length === 0 ? (
            <p className="empty-state">No custom sets yet. Create one above.</p>
          ) : (
            <div className="custom-set-list">
              {sets.map((s) => (
                <div key={s.id} className="custom-set-card">
                  <button className="custom-set-main" onClick={() => setActiveSetId(s.id)}>
                    <span className="custom-set-name">{s.name}</span>
                    <span className="custom-set-count">{s.words.length} words</span>
                  </button>
                  {confirmDeleteSetId === s.id ? (
                    <span className="confirm-delete-inline">
                      <button className="btn-danger-sm" onClick={() => handleDeleteSet(s.id)}>
                        Delete it
                      </button>
                      <button className="btn-cancel-sm" onClick={() => setConfirmDeleteSetId(null)}>
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      className="delete-icon-btn"
                      onClick={() => setConfirmDeleteSetId(s.id)}
                      aria-label={`Delete ${s.name}`}
                      title="Delete this set"
                    >
                      🗑
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Phase 5's therapist-queue operating point (no precision floor, ranked by
// probability - see RESULTS.md's "Therapist-queue point") has nowhere to
// live in the UI until now. `attempt_history` doesn't store audio (nothing
// in this system does - recordings are scored in memory and discarded), so
// "recording playback" is shown as an honest disabled state, not faked.
function ReviewQueueTab({ userId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setRows(null);
    api
      .getTherapistTopK(25, userId)
      .then(setRows)
      .catch((e) => setError(e.message || "Could not load the review queue."));
  }, [userId]);

  if (error) return <p className="error-text">{error}</p>;
  if (rows === null) return <p>Loading...</p>;
  if (rows.length === 0) {
    return <p className="empty-state">No attempts recorded yet for this child - the queue fills in as they practice.</p>;
  }

  return (
    <div className="review-queue">
      <p className="therapist-help">
        Every recorded attempt, ranked by the model's calibrated probability of error - not filtered to the
        child-facing threshold, so this is where lower-confidence signal that's too unreliable to name to a child
        directly still has value for a clinician reviewing it.
      </p>
      <div className="review-queue-list">
        {rows.map((r, i) => (
          <div key={i} className="review-queue-row">
            <span className="review-queue-prob" title="Calibrated P(error)">
              {(r.probability * 100).toFixed(0)}%
            </span>
            <div className="review-queue-main">
              <span className="review-queue-word">{r.word || "—"}</span>
              <span className="review-queue-phoneme">/{r.phoneme}/</span>
            </div>
            <div className="review-queue-detail">
              <span className={`review-queue-status review-queue-status--${r.status}`}>
                {r.status === "wrong" ? "named" : r.status === "unclear" ? "abstained (not named)" : r.status}
              </span>
              {r.top_competitor && (
                <span className="review-queue-competitor">top competitor: /{r.top_competitor}/</span>
              )}
            </div>
            <button className="btn-icon review-queue-playback" disabled title="Recording not saved - audio is scored in memory and discarded">
              🔇
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PhonemeStatsTab({ phonemeErrors }) {
  if (!phonemeErrors || phonemeErrors.length === 0) {
    return <p className="empty-state">No phoneme error data yet - this fills in as the child practices.</p>;
  }
  const max = Math.max(...phonemeErrors.map((p) => p.error_count));
  return (
    <div className="phoneme-stats">
      <p className="therapist-help">Wrong-verdict counts by target phoneme, across every level and practice track.</p>
      {phonemeErrors.map((p) => (
        <div key={p.phoneme} className="phoneme-stat-row">
          <span className="phoneme-stat-label">/{p.phoneme}/</span>
          <div className="phoneme-stat-bar-track">
            <div className="phoneme-stat-bar-fill" style={{ width: `${(p.error_count / max) * 100}%` }} />
          </div>
          <span className="phoneme-stat-count">{p.error_count}</span>
        </div>
      ))}
    </div>
  );
}

// backend/main.py exposes db.get_all_speaker_baselines() (the per-speaker
// Welford running mean/std that child_calibration.py's speaker-relative
// features are built from) at GET /api/therapist/calibration/:userId.
// api.getTherapistCalibration still degrades to null on a fetch failure
// rather than throwing, so a transient network error shows a clean
// message instead of an error screen.
function CalibrationTab({ userId }) {
  const [data, setData] = useState(undefined);

  useEffect(() => {
    setData(undefined);
    api.getTherapistCalibration(userId).then(setData);
  }, [userId]);

  if (data === undefined) return <p>Loading...</p>;
  if (data === null) {
    return <p className="empty-state">Couldn't load calibration data - please try again.</p>;
  }
  const phonemes = Object.keys(data);
  if (phonemes.length === 0) {
    return <p className="empty-state">No calibration data yet for this child.</p>;
  }
  return (
    <div className="calibration-table">
      <p className="therapist-help">
        This child's running per-phoneme baseline (Welford mean/std of GOP scores) - what their speaker-relative
        features are computed against.
      </p>
      <div className="calibration-header-row">
        <span>phoneme</span>
        <span>n attempts</span>
        <span>mean GOP</span>
        <span>std GOP</span>
      </div>
      {phonemes.map((p) => (
        <div key={p} className="calibration-row">
          <span>/{p}/</span>
          <span>{data[p].n}</span>
          <span>{data[p].mean_gop.toFixed(3)}</span>
          <span>{data[p].std_gop.toFixed(3)}</span>
        </div>
      ))}
    </div>
  );
}

function CustomSetDetail({ customSet, onBack, onRefresh, onPractice }) {
  const [word, setWord] = useState("");
  const [lookup, setLookup] = useState(null);
  const [override, setOverride] = useState("");
  const [checking, setChecking] = useState(false);
  const [confirmDeleteWordId, setConfirmDeleteWordId] = useState(null);

  const handleDeleteWord = async (wordId) => {
    await api.deleteCustomWord(wordId);
    setConfirmDeleteWordId(null);
    onRefresh();
  };

  const handleCheck = async () => {
    const trimmed = word.trim();
    if (!trimmed) return;
    setChecking(true);
    try {
      const res = await api.phonemeLookup(trimmed);
      setLookup(res);
    } finally {
      setChecking(false);
    }
  };

  const handleAdd = async () => {
    const trimmed = word.trim();
    if (!trimmed) return;
    const overrideList =
      lookup && !lookup.found && override.trim() ? override.trim().split(/[\s,]+/).map((s) => s.toUpperCase()) : null;
    await api.addCustomWord(customSet.id, trimmed, overrideList);
    setWord("");
    setLookup(null);
    setOverride("");
    onRefresh();
  };

  return (
    <div className="screen screen-therapist">
      <div className="practice-top">
        <button className="btn-icon" onClick={onBack} aria-label="Back">
          ←
        </button>
        <h2 className="practice-title">{customSet.name}</h2>
      </div>

      <div className="add-word-form">
        <input
          className="text-input"
          placeholder="Add a word"
          value={word}
          onChange={(e) => {
            setWord(e.target.value);
            setLookup(null);
          }}
        />
        <button className="btn btn-secondary" onClick={handleCheck} disabled={checking || !word.trim()}>
          {checking ? "Checking..." : "Check"}
        </button>
      </div>

      {lookup && lookup.found && (
        <div className="lookup-result lookup-result--found">
          <p>
            Found it! Phonemes: <strong>{lookup.phonemes.join(" ")}</strong>
          </p>
          <button className="btn btn-primary" onClick={handleAdd}>
            Add "{lookup.word}"
          </button>
        </div>
      )}

      {lookup && !lookup.found && (
        <div className="lookup-result lookup-result--missing">
          <p>
            "{lookup.word}" isn't in the pronunciation dictionary. Scoring will not work for it unless you provide
            the phoneme sequence yourself.
          </p>
          <input
            className="text-input"
            placeholder="Manual phonemes, e.g. R AE B AH T"
            value={override}
            onChange={(e) => setOverride(e.target.value)}
          />
          <button className="btn btn-primary" onClick={handleAdd}>
            Add anyway
          </button>
        </div>
      )}

      <div className="custom-word-list">
        {customSet.words.map((w) => (
          <div key={w.id} className="custom-word-row">
            <span>{w.word}</span>
            <span className="custom-word-row-right">
              {w.phonemes_override ? (
                <span className="custom-word-badge custom-word-badge--manual">
                  manual: {JSON.parse(w.phonemes_override).join(" ")}
                </span>
              ) : (
                <span className="custom-word-badge">dictionary</span>
              )}
              {confirmDeleteWordId === w.id ? (
                <span className="confirm-delete-inline">
                  <button className="btn-danger-sm" onClick={() => handleDeleteWord(w.id)}>
                    Delete
                  </button>
                  <button className="btn-cancel-sm" onClick={() => setConfirmDeleteWordId(null)}>
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  className="delete-icon-btn"
                  onClick={() => setConfirmDeleteWordId(w.id)}
                  aria-label={`Delete ${w.word}`}
                  title="Delete this word"
                >
                  🗑
                </button>
              )}
            </span>
          </div>
        ))}
      </div>

      {customSet.words.length > 0 && (
        <button className="btn btn-primary btn-large" onClick={onPractice}>
          Practice this set
        </button>
      )}
    </div>
  );
}
