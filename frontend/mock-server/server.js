// Dev-only mock of backend/main.py's API, for frontend work without loading
// the real 1.2GB wav2vec2 model. Zero dependencies (Node's built-in http/fs
// only) so it never needs its own npm install. Serves real content from
// backend/data/levels.json and practice_tracks.json so the UI is built
// against real words, not placeholders.
//
// Verdict distribution for the "random" force mode is not a guess - it's
// derived from the measured child-facing operating point
// (eval/phase5_two_points.json / RESULTS.md's "Phase 5 operating points"):
// T_ERROR=0.71, precision=0.500, recall=0.061, n_pos=293/16422 on the child
// dev slice. tp=fp=18 (precision 0.5 => equal counts), abstain=13.2%.
//   correct:            (16422 - 36 - 2169) / 16422 = 86.6%
//   unclear:             2169 / 16422               = 13.2%
//   wrong (named):          36 / 16422               =  0.2%
// unclear_recording is not part of that measurement (speechocean762 clips
// are all clean) - set separately, small, illustrative of "bad mic day".
import http from "http";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8000;
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const LEVELS = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "backend/data/levels.json"), "utf8"));
const TRACKS = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "backend/data/practice_tracks.json"), "utf8"));
const PHON_PROCESSES = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "backend/data/phonological_processes.json"), "utf8"));

const VERDICT_WEIGHTS = { correct: 0.866, unclear: 0.132, wrong: 0.002 };
const UNCLEAR_RECORDING_RATE = 0.03;

// A named substitution needs a plausible "heard" phone - reuse the same
// documented phonological-process substitutions the real scorer draws from,
// picking uniformly among rules whose "from" matches the target.
function plausibleSubstitution(targetPhoneme) {
  const candidates = [];
  for (const rules of Object.values(PHON_PROCESSES)) {
    if (!Array.isArray(rules)) continue;
    for (const rule of rules) {
      if (rule.from === targetPhoneme) candidates.push(rule.to);
    }
  }
  if (candidates.length === 0) return "W"; // harmless fallback for untargeted/rare phones
  return candidates[Math.floor(Math.random() * candidates.length)];
}

// --- in-memory state, reset on server restart (a mock, not real persistence) ---
const users = new Map(); // id -> user row
const levelProgress = new Map(); // id -> { [level]: {words_completed, completed} }
const phonemeErrorCounts = new Map(); // id -> { [phoneme]: count }
const attemptHistory = []; // {user_id, phoneme, status, probability, word, created_at}
const therapistQueue = []; // {id, user_id, phoneme, n_wrong, n_window, mean_probability, created_at, reviewed}
const customSets = new Map(); // id -> {id, user_id, name, words: [{id, word, phonemes_override}]}
let nextCustomSetId = 1;
let nextCustomWordId = 1;

function getOrCreateUser(id) {
  if (!users.has(id)) {
    users.set(id, {
      id, created_at: new Date().toISOString(), current_level: 1,
      speak_aloud: 1, speech_rate: 0.8, app_speech_enabled: 1, accent_tolerance_enabled: 1,
    });
    levelProgress.set(id, {});
    phonemeErrorCounts.set(id, {});
    // Seed some realistic progress/stats so no screen renders empty.
    levelProgress.get(id)["1"] = { words_completed: 10, completed: 1 };
    levelProgress.get(id)["2"] = { words_completed: 4, completed: 0 };
    phonemeErrorCounts.get(id)["R"] = 5;
    phonemeErrorCounts.get(id)["S"] = 2;
  }
  return users.get(id);
}

function fullProgress(id) {
  const user = getOrCreateUser(id);
  const pe = phonemeErrorCounts.get(id) || {};
  const phoneme_errors = Object.entries(pe)
    .map(([phoneme, error_count]) => ({ phoneme, error_count }))
    .sort((a, b) => b.error_count - a.error_count);
  const recommendable = new Set(Object.keys(TRACKS));
  const recommendations = phoneme_errors.filter((p) => recommendable.has(p.phoneme) && p.error_count >= 3);
  return {
    user, level_progress: levelProgress.get(id) || {},
    phoneme_errors, recommendations,
  };
}

function pickVerdict(forced) {
  if (forced && forced !== "random") return forced;
  const r = Math.random();
  if (r < UNCLEAR_RECORDING_RATE) return "unclear_recording";
  const rest = (r - UNCLEAR_RECORDING_RATE) / (1 - UNCLEAR_RECORDING_RATE);
  let acc = 0;
  for (const [status, weight] of Object.entries(VERDICT_WEIGHTS)) {
    acc += weight;
    if (rest < acc) return status;
  }
  return "correct";
}

function scoreResult({ word, targetPhoneme, canonical, forced, userId }) {
  const status = pickVerdict(forced);
  if (status === "unclear_recording") {
    return {
      word, canonical: canonical || [], target_phoneme: targetPhoneme,
      status: "unclear_recording", probability: null, heard: null,
      percent_correct: null, results: [], worst_phoneme: null,
      feedback: "I didn't quite hear that - can you try again a bit closer to the microphone?",
    };
  }
  const probability = status === "wrong" ? 0.71 + Math.random() * 0.29
    : status === "unclear" ? 0.10 + Math.random() * 0.61
    : Math.random() * 0.10;
  // top_competitor exists on every attempt in the real pipeline (features.py
  // computes it regardless of status) - only whether it's SHOWN to the
  // child as "heard" is gated by the naming rule (status=="wrong" only).
  // The therapist queue is allowed to see it always, which is the whole
  // point of a therapist-facing view versus the child-facing one.
  const topCompetitor = plausibleSubstitution(targetPhoneme);
  const heard = status === "wrong" ? topCompetitor : null;
  const percent_correct = { correct: 100, unclear: 50, wrong: 0 }[status];
  const feedback = {
    correct: `Nice work on "${word}"!`,
    unclear: `Good try on "${word}" - let's try that one more time.`,
    wrong: `So close! Let's practice the ${targetPhoneme} sound in "${word}".`,
  }[status];

  const targetIndex = (canonical || []).indexOf(targetPhoneme);
  const result = {
    word, canonical: canonical || [], target_phoneme: targetPhoneme,
    status, probability: Number(probability.toFixed(4)), heard,
    percent_correct,
    results: [{
      index: targetIndex >= 0 ? targetIndex : 0, expected: targetPhoneme,
      status, heard, probability: Number(probability.toFixed(4)),
    }],
    worst_phoneme: status !== "correct" ? targetPhoneme : null,
    feedback,
  };

  attemptHistory.push({
    user_id: userId, phoneme: targetPhoneme, status, probability: result.probability,
    word, top_competitor: topCompetitor, heard,
    // No audio is stored anywhere in this system, mock or real - scoring
    // reads the recording in memory and discards it. Explicit false here
    // rather than omitting the field, so the UI can render an honest
    // "recording not saved" state instead of guessing.
    has_recording: false,
    created_at: new Date().toISOString(),
  });
  if (status === "wrong") {
    if (!phonemeErrorCounts.has(userId)) phonemeErrorCounts.set(userId, {});
    const pe = phonemeErrorCounts.get(userId);
    pe[targetPhoneme] = (pe[targetPhoneme] || 0) + 1;
    therapistQueue.push({
      id: therapistQueue.length + 1, user_id: userId, phoneme: targetPhoneme,
      word, top_competitor: topCompetitor, heard,
      n_wrong: 1, n_window: 1, mean_probability: result.probability,
      has_recording: false,
      created_at: new Date().toISOString(), reviewed: 0,
    });
  }
  return result;
}

// --- minimal multipart/form-data parsing (only what /api/score needs - field
// values, audio bytes discarded since the mock never scores real audio) ---
function parseMultipart(buffer, contentType) {
  const match = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType || "");
  const boundary = match ? "--" + (match[1] || match[2]) : null;
  const fields = {};
  if (!boundary) return fields;
  const parts = buffer.toString("binary").split(boundary).slice(1, -1);
  for (const part of parts) {
    const headerEnd = part.indexOf("\r\n\r\n");
    if (headerEnd === -1) continue;
    const header = part.slice(0, headerEnd);
    const nameMatch = /name="([^"]+)"/.exec(header);
    if (!nameMatch || header.includes("filename=")) continue; // skip the audio file field itself
    const value = part.slice(headerEnd + 4, part.length - 2); // trim trailing \r\n
    fields[nameMatch[1]] = Buffer.from(value, "binary").toString("utf8");
  }
  return fields;
}

function sendJson(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
  res.end(data);
}

function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    return res.end();
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  const parts = url.pathname.split("/").filter(Boolean);

  try {
    if (req.method === "GET" && url.pathname === "/api/health") {
      return sendJson(res, 200, { status: "ok", real_scorer: false, is_mock: true });
    }

    if (req.method === "GET" && url.pathname === "/api/levels") return sendJson(res, 200, LEVELS);
    if (req.method === "GET" && url.pathname === "/api/practice-tracks") return sendJson(res, 200, TRACKS);

    if (req.method === "POST" && url.pathname === "/api/login") {
      const body = JSON.parse((await readBody(req)).toString("utf8") || "{}");
      const id = (body.id || "").trim();
      if (!id) return sendJson(res, 400, { detail: "An ID is required." });
      return sendJson(res, 200, fullProgress(id));
    }

    if (req.method === "GET" && parts[0] === "api" && parts[1] === "progress") {
      return sendJson(res, 200, fullProgress(decodeURIComponent(parts[2])));
    }

    if (req.method === "POST" && url.pathname === "/api/settings") {
      const body = JSON.parse((await readBody(req)).toString("utf8") || "{}");
      const user = getOrCreateUser(body.user_id);
      user.speak_aloud = body.speak_aloud ? 1 : 0;
      user.speech_rate = Math.max(0.5, Math.min(1.0, Number(body.speech_rate) || 0.8));
      user.app_speech_enabled = body.app_speech_enabled ? 1 : 0;
      if ("accent_tolerance_enabled" in body) user.accent_tolerance_enabled = body.accent_tolerance_enabled ? 1 : 0;
      return sendJson(res, 200, user);
    }

    if (req.method === "POST" && url.pathname === "/api/score") {
      const raw = await readBody(req);
      const fields = parseMultipart(raw, req.headers["content-type"]);
      const forced = url.searchParams.get("force") || fields.force || "random";
      let canonical = null;
      if (fields.phonemes_override) {
        try { canonical = JSON.parse(fields.phonemes_override); } catch { /* ignore */ }
      }
      const result = scoreResult({
        word: fields.word, targetPhoneme: (fields.target_phoneme || "").toUpperCase(),
        canonical, forced, userId: fields.user_id,
      });
      return sendJson(res, 200, result);
    }

    if (req.method === "POST" && parts[0] === "api" && parts[1] === "levels" && parts[3] === "advance") {
      const level = Number(parts[2]);
      const body = JSON.parse((await readBody(req)).toString("utf8") || "{}");
      const id = body.user_id;
      if (!levelProgress.has(id)) levelProgress.set(id, {});
      const lp = levelProgress.get(id);
      const lvl = LEVELS.find((l) => l.level === level);
      const total = lvl ? lvl.words.length : 10;
      const existing = lp[String(level)] || { words_completed: 0, completed: 0 };
      const words_completed = Math.min(existing.words_completed + 1, total);
      const completed = words_completed >= total ? 1 : 0;
      lp[String(level)] = { words_completed, completed };
      if (completed) {
        const user = getOrCreateUser(id);
        if (user.current_level === level) user.current_level = Math.min(level + 1, LEVELS.length);
      }
      return sendJson(res, 200, { words_completed, completed: !!completed });
    }

    if (req.method === "GET" && url.pathname === "/api/phoneme-lookup") {
      const word = url.searchParams.get("word") || "";
      // Mock has no cmudict - treat anything as "found" with a plausible-looking fake sequence.
      return sendJson(res, 200, { word, found: true, phonemes: word.toUpperCase().split("").filter((c) => /[A-Z]/.test(c)) });
    }

    if (req.method === "GET" && parts[0] === "api" && parts[1] === "custom-sets" && parts.length === 3) {
      const id = decodeURIComponent(parts[2]);
      const sets = [...customSets.values()].filter((s) => s.user_id === id);
      return sendJson(res, 200, sets);
    }
    if (req.method === "POST" && url.pathname === "/api/custom-sets") {
      const body = JSON.parse((await readBody(req)).toString("utf8") || "{}");
      const set = { id: nextCustomSetId++, user_id: body.user_id, name: body.name, words: [] };
      customSets.set(set.id, set);
      return sendJson(res, 200, set);
    }
    if (req.method === "POST" && parts[0] === "api" && parts[1] === "custom-sets" && parts[3] === "words") {
      const setId = Number(parts[2]);
      const body = JSON.parse((await readBody(req)).toString("utf8") || "{}");
      const set = customSets.get(setId);
      if (!set) return sendJson(res, 404, { detail: "Custom set not found." });
      set.words.push({ id: nextCustomWordId++, word: body.word, phonemes_override: body.phonemes_override ? JSON.stringify(body.phonemes_override) : null });
      return sendJson(res, 200, { custom_set: set, lookup: { found: true, phonemes: ["MOCK"] } });
    }
    if (req.method === "DELETE" && parts[0] === "api" && parts[1] === "custom-sets") {
      customSets.delete(Number(parts[2]));
      return sendJson(res, 200, { deleted: true });
    }
    if (req.method === "DELETE" && parts[0] === "api" && parts[1] === "custom-words") {
      const wordId = Number(parts[2]);
      for (const set of customSets.values()) set.words = set.words.filter((w) => w.id !== wordId);
      return sendJson(res, 200, { deleted: true });
    }

    if (req.method === "GET" && url.pathname === "/api/therapist/review-queue") {
      const userId = url.searchParams.get("user_id");
      return sendJson(res, 200, userId ? therapistQueue.filter((q) => q.user_id === userId) : therapistQueue);
    }
    if (req.method === "GET" && url.pathname === "/api/therapist/top-k") {
      const k = Number(url.searchParams.get("k") || 25);
      const userId = url.searchParams.get("user_id");
      const pool = userId ? attemptHistory.filter((a) => a.user_id === userId) : attemptHistory;
      const ranked = [...pool].sort((a, b) => b.probability - a.probability).slice(0, k);
      return sendJson(res, 200, ranked);
    }

    // A real GET /api/therapist/calibration/:userId now exists too
    // (backend/main.py, added post-Part-9), returning actual accumulated
    // speaker_baseline rows. This mock version stays as its own simulated
    // route rather than proxying the real shape 1:1, since it needs to
    // fabricate plausible-looking baseline numbers for phonemes this mock
    // user has never actually attempted (dev/screenshot review needs
    // something to show even for a fresh mock user with no real history).
    if (req.method === "GET" && parts[0] === "api" && parts[1] === "therapist" && parts[2] === "calibration") {
      const userId = decodeURIComponent(parts[3] || "");
      const pe = phonemeErrorCounts.get(userId) || {};
      const phonemes = Object.keys(pe).length ? Object.keys(pe) : ["R", "S", "TH", "L"];
      const baselines = {};
      for (const p of phonemes) {
        const n = 8 + Math.floor(Math.random() * 40);
        baselines[p] = {
          phoneme: p, n,
          mean_gop: Number((-2.5 + Math.random() * 1.5).toFixed(3)),
          std_gop: Number((0.4 + Math.random() * 0.6).toFixed(3)),
        };
      }
      return sendJson(res, 200, baselines);
    }

    sendJson(res, 404, { detail: "Not found (mock server)" });
  } catch (err) {
    console.error(err);
    sendJson(res, 500, { detail: String(err) });
  }
});

server.listen(PORT, () => {
  console.log(`Echo mock API server on http://localhost:${PORT}`);
  console.log(`Verdict distribution (random mode): correct ${(VERDICT_WEIGHTS.correct * 100).toFixed(1)}%, `
    + `unclear ${(VERDICT_WEIGHTS.unclear * 100).toFixed(1)}%, wrong ${(VERDICT_WEIGHTS.wrong * 100).toFixed(1)}%, `
    + `unclear_recording ${(UNCLEAR_RECORDING_RATE * 100).toFixed(1)}% - derived from RESULTS.md's measured operating point.`);
});
