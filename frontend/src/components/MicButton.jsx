export default function MicButton({ isRecording, level, onClick, disabled }) {
  const ringScale = 1 + level * 0.6;
  return (
    <button
      type="button"
      className={`mic-button ${isRecording ? "mic-button--recording" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={isRecording}
      aria-label={isRecording ? "Stop recording" : "Start recording"}
    >
      {isRecording && (
        <span className="mic-level-ring" style={{ transform: `scale(${ringScale})` }} aria-hidden="true" />
      )}
      <span className="mic-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="46" height="46" fill="none">
          <rect x="9" y="2" width="6" height="12" rx="3" fill="white" />
          <path d="M5 11a7 7 0 0 0 14 0" stroke="white" strokeWidth="2" strokeLinecap="round" />
          <path d="M12 18v3" stroke="white" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </span>
    </button>
  );
}
