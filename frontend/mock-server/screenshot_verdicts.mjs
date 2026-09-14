import { chromium } from "playwright";
import fs from "fs";
import path from "path";

// Captures the practice screen in each forced verdict state (wrong, unclear,
// unclear_recording) and composites them side by side into one image, so
// review stays within the screenshot budget (1 image read instead of 3).
const outDir = process.argv[2] || ".";
const states = ["wrong", "unclear", "unclear_recording"];

// Headless Chromium's fake-device media stack is flaky (hangs rather than
// resolving/rejecting in this environment) - instead of fighting it, stub
// getUserMedia/MediaRecorder in-page so handleMicClick's start()/stop() flow
// runs for real, producing a real (tiny, silent) Blob for /api/score.
function stubMedia() {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const dest = ctx.createMediaStreamDestination();
  const osc = ctx.createOscillator();
  osc.frequency.value = 0.0001;
  osc.connect(dest);
  osc.start();
  navigator.mediaDevices.getUserMedia = async () => dest.stream;

  class FakeRecorder {
    constructor(stream, opts) {
      this.stream = stream;
      this.mimeType = (opts && opts.mimeType) || "audio/webm";
      this.state = "inactive";
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      if (this.ondataavailable) this.ondataavailable({ data: new Blob([new Uint8Array(16)], { type: this.mimeType }) });
      if (this.onstop) this.onstop();
    }
  }
  FakeRecorder.isTypeSupported = () => true;
  window.MediaRecorder = FakeRecorder;
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
});

const shots = [];
for (const state of states) {
  const page = await context.newPage();
  await page.addInitScript(stubMedia);
  await page.addInitScript(() => localStorage.setItem("speechpal_user_id", "demo_kid"));
  await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.locator(".level-bubble").first().click();
  await page.waitForTimeout(400);

  // Force the verdict via the mock status bar.
  await page.getByRole("button", { name: `Force: ${state}`, exact: true }).click();
  await page.waitForTimeout(150);

  // Record: click mic to start, wait, click again to stop -> triggers /api/score.
  // force: true - the mic button has a continuous idle pulse animation,
  // which Playwright's actionability check (waits for the element to stop
  // moving) never considers "stable".
  const micLocator = page.locator(".mic-button");
  await micLocator.click({ force: true });
  await page.waitForTimeout(600);
  await micLocator.click({ force: true });
  await page.waitForTimeout(700);

  const outfile = path.join(outDir, `verdict-${state}.png`);
  await page.screenshot({ path: outfile });
  shots.push(outfile);
  await page.close();
}

// Composite the 3 shots side by side using a small HTML page + one more screenshot.
const compositePage = await context.newPage();
await compositePage.setViewportSize({ width: 390 * 3 + 40, height: 844 + 20 });
const html = `<!doctype html><html><body style="margin:0;display:flex;gap:20px;background:#222;padding:10px;">
${shots.map((s) => `<img src="file://${path.resolve(s)}" style="width:390px;display:block;" />`).join("\n")}
</body></html>`;
const tmpHtml = path.join(outDir, "_composite.html");
fs.writeFileSync(tmpHtml, html);
await compositePage.goto(`file://${path.resolve(tmpHtml)}`);
await compositePage.waitForTimeout(200);
await compositePage.screenshot({ path: path.join(outDir, "verdicts-composite.png") });

await browser.close();
console.log("saved composite:", path.join(outDir, "verdicts-composite.png"));
