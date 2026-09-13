// A top-level on/off switch for whether the app ever speaks a word aloud at
// all. Some therapists read the target word to the child themselves and
// only want the app to listen and evaluate - for that session the "Hear it
// first" / "Read it myself" choice and the speech-rate slider aren't just
// unnecessary, they're clutter. This is the master switch above that
// per-session choice: off hides all of it and the app never talks.
export default function SpeechModeToggle({ enabled, onChange, compact = false }) {
  return (
    <button
      type="button"
      className={`speech-mode-switch ${enabled ? "speech-mode-switch--on" : "speech-mode-switch--off"} ${compact ? "speech-mode-switch--compact" : ""}`}
      onClick={() => onChange(!enabled)}
      aria-pressed={enabled}
      title={enabled ? "App speaks words aloud. Tap to switch to silent, evaluate-only mode." : "Silent mode: the app never speaks, it only listens and scores. Tap to re-enable speech."}
    >
      <span className="speech-mode-switch-icon" aria-hidden="true">
        {enabled ? "🔊" : "🔇"}
      </span>
      {!compact && (
        <span className="speech-mode-switch-label">
          {enabled ? "App speaks" : "Silent mode"}
        </span>
      )}
      <span className="speech-mode-switch-track" aria-hidden="true">
        <span className="speech-mode-switch-thumb" />
      </span>
    </button>
  );
}
