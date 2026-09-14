import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const outDir = process.argv[2] || ".";
const themes = ["space", "ocean", "candy"];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 900, height: 900 } });

const shots = [];
for (const theme of themes) {
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem("speechpal_user_id", "Jamie"));
  await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Change theme" }).click();
  await page.waitForTimeout(150);
  await page.getByRole("button", { name: `${theme.charAt(0).toUpperCase() + theme.slice(1)} theme`, exact: true }).click();
  await page.waitForTimeout(400);
  const outfile = path.join(outDir, `theme-${theme}.png`);
  await page.screenshot({ path: outfile });
  shots.push(outfile);
  await page.close();
}

const compositePage = await context.newPage();
await compositePage.setViewportSize({ width: 900 * 3 + 40, height: 900 + 20 });
const html = `<!doctype html><html><body style="margin:0;display:flex;gap:20px;background:#222;padding:10px;">
${shots.map((s) => `<img src="file://${path.resolve(s)}" style="width:900px;display:block;" />`).join("\n")}
</body></html>`;
const tmpHtml = path.join(outDir, "_composite_themes.html");
fs.writeFileSync(tmpHtml, html);
await compositePage.goto(`file://${path.resolve(tmpHtml)}`);
await compositePage.waitForTimeout(200);
await compositePage.screenshot({ path: path.join(outDir, "themes-composite.png") });

await browser.close();
console.log("saved composite:", path.join(outDir, "themes-composite.png"));
