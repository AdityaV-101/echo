import { useState } from "react";

// Results display for the forced-alignment + GOP scorer. Each result now
// carries: status (correct / borderline / wrong / accent_variant), and for
// anything not "correct", what was heard instead (the top competitor from
// GOP scoring) - plus, for the collapsible therapist panel, the raw GOP,
// z-score against the speaker's baseline, the aligned frame range in ms,
// and the top 3 competing phones with their posterior probabilities. The
// therapist panel exists so a therapist can see the actual evidence behind
// a verdict and disagree with the model rather than take it on faith.
const STATUS_LABEL = {
  correct: null,
  borderline: "borderline",
  wrong: null,
  accent_variant: "accent variant",
};

export default function PhonemeChips({ results, targetPhoneme }) {
  const [showEvidence, setShowEvidence] = useState(false);

  return (
    <div className="results-display">
      <div className="phoneme-chips">
        {results.map((r, i) => {
          const isTarget = targetPhoneme && r.expected === targetPhoneme;
          const statusClass = `chip-${r.status}`;
          return (
            <div key={i} className={`chip ${statusClass} ${isTarget ? "chip-target" : ""}`}>
              <span className="chip-label">{r.expected}</span>
              {r.status === "accent_variant" && <span className="chip-sub">accepted ({r.heard})</span>}
              {r.status === "wrong" && r.heard && <span className="chip-sub">sounded like {r.heard}</span>}
              {r.status === "wrong" && !r.heard && <span className="chip-sub">try adding this</span>}
              {r.status === "borderline" && (
                <span className="chip-sub">{r.heard ? `borderline, leaned ${r.heard}` : "borderline"}</span>
              )}
              {isTarget && <span className="chip-target-badge">target</span>}
            </div>
          );
        })}
      </div>

      <button className="explain-toggle" onClick={() => setShowEvidence((s) => !s)}>
        {showEvidence ? "Hide" : "Show"} therapist evidence {showEvidence ? "▲" : "▼"}
      </button>

      {showEvidence && (
        <div className="explain-panel therapist-panel">
          <p className="explain-note">
            Forced-alignment + Goodness-of-Pronunciation scoring, calibrated against this speaker's own
            history. GOP is always ≤ 0 (0 = perfect agreement); the status above is decided by the z-score
            of that GOP against the speaker's baseline (or a global starting prior for a new speaker), not
            by a fixed cutoff. This is an automatic estimate, not a diagnosis - use the evidence below to
            agree or disagree with it.
          </p>
          <div className="therapist-table">
            <div className="therapist-row therapist-row-head">
              <span>Sound</span>
              <span>Status</span>
              <span>GOP</span>
              <span>z-score</span>
              <span>Frames</span>
              <span>Top competitors</span>
            </div>
            {results.map((r, i) => (
              <div key={i} className="therapist-row">
                <span className="therapist-cell-phoneme">{r.expected}</span>
                <span>
                  {r.status}
                  {STATUS_LABEL[r.status] ? ` (${STATUS_LABEL[r.status]})` : ""}
                </span>
                <span>{r.gop?.toFixed(3)}</span>
                <span>{r.z_score?.toFixed(2)}</span>
                <span>
                  {Math.round(r.start_ms)}–{Math.round(r.end_ms)}ms
                </span>
                <span>
                  {(r.competitors || []).map(([label, p]) => `${label} (${(p * 100).toFixed(0)}%)`).join(", ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
