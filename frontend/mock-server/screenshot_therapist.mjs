import { chromium } from "playwright";

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
    start() { this.state = "recording"; }
    stop() {
      this.state = "inactive";
      if (this.ondataavailable) this.ondataavailable({ data: new Blob([new Uint8Array(16)], { type: this.mimeType }) });
      if (this.onstop) this.onstop();
    }
  }
  FakeRecorder.isTypeSupported = () => true;
  window.MediaRecorder = FakeRecorder;
}

const [, , outfile, tab] = process.argv;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
await page.addInitScript(stubMedia);
await page.addInitScript(() => localStorage.setItem("speechpal_user_id", "Jamie"));
await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
await page.waitForTimeout(500);

// Generate a few attempts first so the queue/stats/calibration tabs have data:
// force a "wrong" verdict and click through a level's mic a few times.
await page.getByRole("button", { name: "Force: wrong", exact: true }).click();
await page.locator(".level-bubble").first().click({ force: true });
await page.waitForTimeout(400);
for (let i = 0; i < 3; i++) {
  const mic = page.locator(".mic-button");
  await mic.click({ force: true });
  await page.waitForTimeout(300);
  await mic.click({ force: true });
  await page.waitForTimeout(500);
  const nextBtn = page.getByRole("button", { name: /Next word|Finish/ });
  if (await nextBtn.count()) await nextBtn.click({ force: true });
  await page.waitForTimeout(300);
}

// Back to home, then into Therapist Mode.
await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
await page.waitForTimeout(400);
await page.getByRole("button", { name: "Therapist Mode" }).click();
await page.waitForTimeout(400);
if (tab) {
  await page.getByRole("tab", { name: tab }).click();
  await page.waitForTimeout(400);
}
await page.screenshot({ path: outfile, fullPage: true });
await browser.close();
console.log(`saved ${outfile}`);
