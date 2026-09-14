import { chromium } from "playwright";

const [, , outfile, width, height] = process.argv;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: Number(width) || 1280, height: Number(height) || 900 } });
await page.addInitScript(() => localStorage.setItem("speechpal_user_id", "Jamie"));
await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
await page.waitForTimeout(700);
await page.screenshot({ path: outfile, fullPage: true });
await browser.close();
console.log(`saved ${outfile}`);
