// Lets the dev-only MockStatusBar force /api/score's next verdict. A plain
// module-level variable (not React state) so api.js's plain fetch functions
// can read it without needing to be components themselves; the status bar
// itself is a component and re-renders on its own clicks.
let forcedStatus = "random";
const listeners = new Set();

export function getForcedStatus() {
  return forcedStatus;
}

export function setForcedStatus(status) {
  forcedStatus = status;
  listeners.forEach((fn) => fn(status));
}

export function subscribeForcedStatus(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// Health-checked once at startup (App.jsx) - only the mock server ever
// returns is_mock: true, so the status bar can stay invisible against the
// real backend without a build-time flag.
let mockDetected = false;
export function setMockDetected(value) {
  mockDetected = value;
}
export function isMockDetected() {
  return mockDetected;
}
