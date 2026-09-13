import { useEffect, useState } from "react";
import { useApp } from "../lib/AppContext";
import FloatingDecor from "../components/FloatingDecor";
import * as api from "../lib/api";
import WordPractice from "./WordPractice";

export default function TherapistMode({ onExit }) {
  const { userId } = useApp();
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
