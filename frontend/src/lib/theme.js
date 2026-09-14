// Local, per-device app skin (Part 7's four themes) - independent of the
// backend's per-user settings (speak-aloud/rate/etc), since a color theme
// isn't a clinical setting and has nowhere to live server-side. Persisted
// to localStorage the same way the login id is (see AppContext.jsx).
const STORAGE_KEY = "speechpal_theme";
export const THEMES = [
  { id: "default", label: "Sunny", swatch: "#e57226" },
  { id: "jungle", label: "Jungle", swatch: "#4d9a3f" },
  { id: "space", label: "Space", swatch: "#a06bff" },
  { id: "ocean", label: "Ocean", swatch: "#1f8fc2" },
  { id: "candy", label: "Candy", swatch: "#e2508f" },
];

export function getTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "default";
  } catch {
    return "default";
  }
}

export function applyTheme(id) {
  if (id === "default") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", id);
  }
}

export function setTheme(id) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Private-browsing/blocked storage: theme still applies for this
    // session via applyTheme, it just won't persist across reloads.
  }
  applyTheme(id);
}
