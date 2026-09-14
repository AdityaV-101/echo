// Lists every word in levels.json + practice_tracks.json that still lacks
// real art (falls back to the themed initial-letter card). Run:
//   node mock-server/check_word_art.mjs
// Output count is what DESIGN_NOTES.md reports.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const levels = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "backend/data/levels.json"), "utf8"));
const tracks = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "backend/data/practice_tracks.json"), "utf8"));

// Kept in sync by hand with wordArt.jsx's WORD_ART_COVERAGE - duplicated
// here (rather than imported) since this is a plain Node script and
// wordArt.jsx is a .jsx module meant for the Vite/React build.
const COVERED = new Set([
  "ball", "bed", "bus", "cup", "dog", "door", "duck", "ham", "hat", "hen",
  "man", "map", "moon", "mud", "mug", "net", "nose", "pen", "pig", "pot",
  "pup", "top", "web",
]);

const allWords = new Set();
for (const lvl of levels) for (const w of lvl.words) allWords.add(w.word.toLowerCase());
for (const track of Object.values(tracks)) {
  for (const tier of track.tiers) {
    for (const phrase of tier.words) {
      for (const w of phrase.toLowerCase().split(/\s+/)) allWords.add(w);
    }
  }
}

const missing = [...allWords].filter((w) => !COVERED.has(w)).sort();
console.log(`Total distinct words across levels.json + practice_tracks.json: ${allWords.size}`);
console.log(`Have real art: ${COVERED.size}`);
console.log(`Missing (themed fallback card): ${missing.length}`);
console.log(missing.join(", "));
