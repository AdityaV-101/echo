// Screenshot helper for the overnight run's required look-critique-fix
// loop. Usage: node mock-server/screenshot.mjs <url> <outfile> [width] [height] [waitMs]
import { chromium } from "playwright";

const [, , url, outfile, widthArg, heightArg, waitArg] = process.argv;
const width = Number(widthArg) || 1280;
const height = Number(heightArg) || 900;
const waitMs = Number(waitArg) || 800;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height } });
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForTimeout(waitMs);
await page.screenshot({ path: outfile, fullPage: true });
await browser.close();
console.log(`saved ${outfile}`);
