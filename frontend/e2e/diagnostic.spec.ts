import { expect, test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

/**
 * Standalone diagnostic script — NOT part of the regular CI test suite.
 * Captures console/network/runtime/visual state of the live dashboard for
 * manual inspection. Run with: npx playwright test e2e/diagnostic.spec.ts
 */

test("live diagnostic audit", async ({ page }) => {
  test.setTimeout(120_000); // the real /api/reels/analyze call hits Gemini and can take a while

  const consoleMessages: { type: string; text: string }[] = [];
  const pageErrors: string[] = [];
  const failedRequests: { url: string; failure: string | null }[] = [];
  const nonOkResponses: { url: string; status: number }[] = [];

  page.on("console", (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  page.on("pageerror", (err) => {
    pageErrors.push(err.message + "\n" + (err.stack ?? ""));
  });

  page.on("requestfailed", (req) => {
    failedRequests.push({ url: req.url(), failure: req.failure()?.errorText ?? null });
  });

  page.on("response", (res) => {
    if (res.status() >= 400) {
      nonOkResponses.push({ url: res.url(), status: res.status() });
    }
  });

  console.log("\n========== NAVIGATING TO http://localhost:3000 ==========");
  const navResponse = await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  console.log(`Navigation response status: ${navResponse?.status()}`);

  await page.waitForTimeout(1000); // settle any late hydration/console activity

  // ---- 1. CSS / Tailwind compilation sanity check ----
  console.log("\n========== COMPUTED STYLE CHECK ==========");
  const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  console.log(`body font-family: ${bodyFont}`);

  const mainStyles = await page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return null;
    const cs = getComputedStyle(main);
    return {
      backgroundColor: cs.backgroundColor,
      direction: cs.direction,
      minHeight: cs.minHeight,
      padding: cs.padding,
      display: cs.display,
    };
  });
  console.log("main computed styles:", JSON.stringify(mainStyles, null, 2));

  const uploadButtonStyles = await page.evaluate(() => {
    const btn = document.querySelector('[data-testid="upload-button"]');
    if (!btn) return null;
    const cs = getComputedStyle(btn);
    return {
      borderStyle: cs.borderStyle,
      borderColor: cs.borderColor,
      borderWidth: cs.borderWidth,
      borderRadius: cs.borderRadius,
      backgroundColor: cs.backgroundColor,
      color: cs.color,
      padding: cs.padding,
      display: cs.display,
      width: cs.width,
    };
  });
  console.log("upload-button computed styles:", JSON.stringify(uploadButtonStyles, null, 2));

  // Does the page actually have a compiled stylesheet (not just raw unstyled HTML)?
  const stylesheetInfo = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(
      (l) => (l as HTMLLinkElement).href,
    );
    const styleTags = document.querySelectorAll("style").length;
    let totalRules = 0;
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        totalRules += sheet.cssRules.length;
      } catch {
        // cross-origin sheet, ignore
      }
    }
    return { links, styleTagCount: styleTags, totalCssRules: totalRules };
  });
  console.log("stylesheet info:", JSON.stringify(stylesheetInfo, null, 2));

  // ---- 2. Hydration mismatch detection ----
  const hydrationWarnings = consoleMessages.filter(
    (m) =>
      /hydrat/i.test(m.text) ||
      /did not match/i.test(m.text) ||
      /Text content does not match/i.test(m.text),
  );

  // ---- 3. Screenshot ----
  const screenshotDir = path.resolve(__dirname, "..", "test-results");
  fs.mkdirSync(screenshotDir, { recursive: true });
  const screenshotPath = path.join(screenshotDir, "live_audit.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`\nScreenshot saved to: ${screenshotPath}`);

  // ---- 4. Click-through flow attempt ----
  console.log("\n========== CLICK-THROUGH FLOW ATTEMPT ==========");
  const flowLog: string[] = [];
  try {
    const toggle = page.getByTestId("toggle-manual-source");
    await toggle.click({ timeout: 5000 });
    flowLog.push("Clicked toggle-manual-source: OK");

    const pathInput = page.getByTestId("source-path-input");
    await pathInput.fill("references/treatment_flow/copy_C9E6677C-B027-40FA-81B1-64C1BCD9FB67.mp4", {
      timeout: 5000,
    });
    flowLog.push("Filled source-path-input: OK");

    const analyzeBtn = page.getByTestId("analyze-button");
    await analyzeBtn.click({ timeout: 5000 });
    flowLog.push("Clicked analyze-button: OK");

    // Wait for either the recommendation card or an error message, whichever comes first.
    const result = await Promise.race([
      page
        .getByTestId("ai-recommendation-card")
        .waitFor({ state: "visible", timeout: 45000 })
        .then(() => "recommendation-card-visible"),
      page
        .locator("text=/שגיאה|נכשל/")
        .first()
        .waitFor({ state: "visible", timeout: 45000 })
        .then(() => "error-message-visible"),
    ]).catch((e) => `timeout-or-error: ${e.message}`);
    flowLog.push(`Analyze outcome: ${result}`);

    if (result === "recommendation-card-visible") {
      const cardText = await page.getByTestId("ai-recommendation-card").innerText();
      flowLog.push(`Recommendation card content: ${cardText}`);
    }
  } catch (e) {
    flowLog.push(`FLOW ERROR: ${e instanceof Error ? e.message : String(e)}`);
  }
  console.log(flowLog.join("\n"));

  // ---- Final report dump ----
  console.log("\n========== CONSOLE MESSAGES ==========");
  for (const m of consoleMessages) {
    console.log(`[${m.type}] ${m.text}`);
  }

  console.log("\n========== PAGE ERRORS (unhandled exceptions) ==========");
  for (const e of pageErrors) {
    console.log(e);
  }
  if (pageErrors.length === 0) console.log("(none)");

  console.log("\n========== FAILED REQUESTS ==========");
  for (const f of failedRequests) {
    console.log(`${f.url} -> ${f.failure}`);
  }
  if (failedRequests.length === 0) console.log("(none)");

  console.log("\n========== NON-2xx/3xx RESPONSES ==========");
  for (const n of nonOkResponses) {
    console.log(`${n.status} ${n.url}`);
  }
  if (nonOkResponses.length === 0) console.log("(none)");

  console.log("\n========== HYDRATION WARNINGS ==========");
  for (const h of hydrationWarnings) {
    console.log(`[${h.type}] ${h.text}`);
  }
  if (hydrationWarnings.length === 0) console.log("(none)");

  // This diagnostic always "passes" structurally — its value is the console
  // dump and screenshot above, not pass/fail assertions.
  expect(navResponse?.status()).toBe(200);
});
