import { useState } from "react";
import Mascot from "../components/Mascot";

const STATES = ["idle", "listening", "thinking", "celebrating", "encouraging", "demonstrating", "speaking"];
const SIZES = [64, 120, 200];

// Dev-only route (see App.jsx: rendered when the URL hash is #mascot-lab)
// for the required screenshot-critique loop - one composite image instead
// of one capture per state, per the overnight run's screenshot-budget rule.
// Theme backgrounds are placeholders (Part 7 hasn't built the real themes
// yet) - swap the swatch colors below once eval/../themes land for real.
export default function MascotLab() {
  const [micLevel, setMicLevel] = useState(0.5);

  return (
    <div style={{ padding: 24, background: "#f5f1ea", minHeight: "100vh" }}>
      <h1 style={{ fontFamily: "sans-serif" }}>Mascot Lab</h1>
      <p style={{ fontFamily: "sans-serif", maxWidth: 640 }}>
        Echo at 3 sizes x 7 states, on light and dark, plus placeholder theme
        swatches. Critique in DESIGN_NOTES.md, not here.
      </p>

      <label style={{ display: "block", marginBottom: 16, fontFamily: "sans-serif" }}>
        Mic level (listening state ring): {micLevel.toFixed(2)}
        <input type="range" min="0" max="1" step="0.05" value={micLevel} onChange={(e) => setMicLevel(Number(e.target.value))} style={{ marginLeft: 8, width: 200 }} />
      </label>

      {["#f5f1ea (light)", "#241a2e (dark)"].map((bgLabel, bgIdx) => {
        const bg = bgIdx === 0 ? "#f5f1ea" : "#241a2e";
        const fg = bgIdx === 0 ? "#222" : "#eee";
        return (
          <div key={bgLabel} style={{ background: bg, padding: 20, marginBottom: 16, borderRadius: 12 }}>
            <h3 style={{ color: fg, fontFamily: "sans-serif", margin: "0 0 12px" }}>{bgLabel}</h3>
            {SIZES.map((size) => (
              <div key={size} style={{ display: "flex", gap: 18, marginBottom: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
                <span style={{ color: fg, fontFamily: "monospace", width: 40, fontSize: 12 }}>{size}px</span>
                {STATES.map((state) => (
                  <div key={state} style={{ textAlign: "center" }}>
                    <Mascot state={state} size={size} micLevel={micLevel} celebrateVariant={0} />
                    <div style={{ color: fg, fontFamily: "monospace", fontSize: 10, marginTop: 4 }}>{state}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        );
      })}

      <div style={{ background: "#fff", padding: 20, borderRadius: 12 }}>
        <h3 style={{ fontFamily: "sans-serif", margin: "0 0 12px" }}>Celebrating: 4 variants</h3>
        <div style={{ display: "flex", gap: 18 }}>
          {[0, 1, 2, 3].map((v) => (
            <div key={v} style={{ textAlign: "center" }}>
              <Mascot state="celebrating" size={120} celebrateVariant={v} />
              <div style={{ fontFamily: "monospace", fontSize: 10 }}>variant {v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
