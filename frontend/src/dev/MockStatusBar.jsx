import { useEffect, useState } from "react";
import { getForcedStatus, isMockDetected, setForcedStatus } from "../lib/mockControl";

const OPTIONS = [
  { value: "random", label: "Random (measured mix)" },
  { value: "correct", label: "Force: correct" },
  { value: "unclear", label: "Force: unclear" },
  { value: "wrong", label: "Force: wrong" },
  { value: "unclear_recording", label: "Force: unclear_recording" },
];

// Renders only when the mock server answered /api/health with is_mock: true
// (checked once in App.jsx) - never visible against the real backend, so
// this component's own code shipping to production is harmless either way.
export default function MockStatusBar() {
  const [visible, setVisible] = useState(isMockDetected());
  const [forced, setForced] = useState(getForcedStatus());

  useEffect(() => {
    // isMockDetected() is set asynchronously by App.jsx's health check,
    // which may resolve after this component's first render.
    setVisible(isMockDetected());
    const id = setInterval(() => setVisible(isMockDetected()), 500);
    return () => clearInterval(id);
  }, []);

  if (!visible) return null;

  return (
    <div className="mock-status-bar" role="toolbar" aria-label="Mock verdict control (dev only)">
      <span className="mock-status-bar-label">MOCK API</span>
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`mock-status-btn ${forced === opt.value ? "mock-status-btn--active" : ""}`}
          onClick={() => {
            setForcedStatus(opt.value);
            setForced(opt.value);
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
