import { getForcedStatus } from "./mockControl";

const BASE_URL = "http://localhost:8000";

async function handleResponse(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore, keep statusText
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/api/health`);
  return handleResponse(res);
}

export async function getTherapistTopK(k = 25, userId) {
  const params = new URLSearchParams({ k: String(k) });
  if (userId) params.set("user_id", userId);
  const res = await fetch(`${BASE_URL}/api/therapist/top-k?${params}`);
  return handleResponse(res);
}

export async function getTherapistReviewQueue(userId) {
  const params = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  const res = await fetch(`${BASE_URL}/api/therapist/review-queue${params}`);
  return handleResponse(res);
}

export async function login(id) {
  const res = await fetch(`${BASE_URL}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  return handleResponse(res);
}

export async function getProgress(userId) {
  const res = await fetch(`${BASE_URL}/api/progress/${encodeURIComponent(userId)}`);
  return handleResponse(res);
}

export async function getLevels() {
  const res = await fetch(`${BASE_URL}/api/levels`);
  return handleResponse(res);
}

export async function getPracticeTracks() {
  const res = await fetch(`${BASE_URL}/api/practice-tracks`);
  return handleResponse(res);
}

export async function updateSettings(userId, speakAloud, speechRate, appSpeechEnabled) {
  const res = await fetch(`${BASE_URL}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      speak_aloud: speakAloud ? 1 : 0,
      speech_rate: speechRate,
      app_speech_enabled: appSpeechEnabled ? 1 : 0,
    }),
  });
  return handleResponse(res);
}

export async function scoreWord({ userId, word, level, phonemesOverride, targetPhoneme, position, audioBlob }) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("word", word);
  if (level !== undefined && level !== null) form.append("level", String(level));
  if (phonemesOverride) form.append("phonemes_override", JSON.stringify(phonemesOverride));
  if (targetPhoneme) form.append("target_phoneme", targetPhoneme);
  if (position) form.append("position", position);
  form.append("audio", audioBlob, "recording.webm");
  // Dev-only: the mock server reads this field to force a specific verdict
  // (see frontend/src/dev/MockStatusBar.jsx). The real backend ignores any
  // extra form field it doesn't recognize, so this is always safe to send.
  const forced = getForcedStatus();
  if (forced && forced !== "random") form.append("force", forced);
  const res = await fetch(`${BASE_URL}/api/score`, { method: "POST", body: form });
  return handleResponse(res);
}

export async function advanceLevel(userId, level) {
  const res = await fetch(`${BASE_URL}/api/levels/${level}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  return handleResponse(res);
}

export async function deleteCustomSet(setId) {
  const res = await fetch(`${BASE_URL}/api/custom-sets/${setId}`, { method: "DELETE" });
  return handleResponse(res);
}

export async function deleteCustomWord(wordId) {
  const res = await fetch(`${BASE_URL}/api/custom-words/${wordId}`, { method: "DELETE" });
  return handleResponse(res);
}

export async function phonemeLookup(word) {
  const res = await fetch(`${BASE_URL}/api/phoneme-lookup?word=${encodeURIComponent(word)}`);
  return handleResponse(res);
}

export async function getCustomSets(userId) {
  const res = await fetch(`${BASE_URL}/api/custom-sets/${encodeURIComponent(userId)}`);
  return handleResponse(res);
}

export async function createCustomSet(userId, name) {
  const res = await fetch(`${BASE_URL}/api/custom-sets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, name }),
  });
  return handleResponse(res);
}

export async function addCustomWord(setId, word, phonemesOverride) {
  const res = await fetch(`${BASE_URL}/api/custom-sets/${setId}/words`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word, phonemes_override: phonemesOverride || null }),
  });
  return handleResponse(res);
}
