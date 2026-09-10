import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
const baseURL = process.env.AIRLOCK_BROKER_URL || "http://127.0.0.1:8100";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  reducedMotion: "reduce",
  acceptDownloads: true,
});
page.setDefaultTimeout(15000);
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const run = Date.now();
const objectName = `ui_census_${run}.csv`;
const policyName = `UI birthday coordination ${run}`;
await fs.mkdir("../docs/screenshots", { recursive: true });
await page.goto(baseURL);
await page.getByRole("heading", { name: "Context under control." }).waitFor();
// Actual dashboard upload; no API shortcut.
await page.locator('input[accept=".csv,text/csv"]').setInputFiles({
  name: objectName,
  mimeType: "text/csv",
  buffer: await fs.readFile(
    process.env.AIRLOCK_TEST_CSV || "../demo-workspace/employee_census.csv",
  ),
});
await page.getByRole("heading", { name: objectName, exact: true }).waitFor();
const downloadPromise = page.waitForEvent("download");
await page.getByRole("button", { name: "Save .airlock file" }).click();
const download = await downloadPromise;
const referencePath = `../demo-workspace/ui-${run}.airlock`;
await download.saveAs(referencePath);
const reference = JSON.parse(
  (await fs.readFile(referencePath, "utf8"))
    .split("\n---AIRLOCK-ENCRYPTED-PAYLOAD---\n")[0]
    .slice(10),
);
expect(reference.object_id).toMatch(/^obj_/);
expect(JSON.stringify(reference)).not.toContain("000-00-0001");
await page.screenshot({
  path: "../docs/screenshots/object-detail.png",
  fullPage: true,
});
await page.getByRole("button", { name: "Add rule", exact: true }).click();
await page.getByLabel("Policy name", { exact: true }).fill(policyName);
await page
  .getByLabel("Policy instructions")
  .fill(
    "For birthday planning, disclose names and upcoming month/day only for employees with birthday_opt_in=true on the supplied user’s team. Do not expose birth years or ages. Allow aggregate department counts.",
  );
// Simulate one failed save: the user's draft must remain intact.
await page.route("**/admin/policies", (route) =>
  route.request().method() === "POST"
    ? route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Verification: temporary storage failure",
        }),
      })
    : route.continue(),
);
await page.getByRole("button", { name: "Save policy", exact: true }).click();
await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
  "temporary storage failure",
);
await expect(page.getByLabel("Policy name", { exact: true })).toHaveValue(
  policyName,
);
await page.unroute("**/admin/policies");
await page.getByRole("button", { name: "Save policy", exact: true }).click();
await expect(page.getByRole("dialog")).toHaveCount(0);
await page.getByRole("button", { name: "Policy studio", exact: true }).click();
// Create a natural-language organization policy in the UI as well.
await page.getByRole("button", { name: "New policy", exact: true }).click();
await page
  .getByLabel("Policy name", { exact: true })
  .fill(`Response clarity ${run}`);
await page
  .getByLabel("Policy instructions")
  .fill(
    "Write clear English responses. Explain withheld categories without quoting their values. Preserve useful permitted answers.",
  );
await page.getByRole("button", { name: "Save policy", exact: true }).click();
await expect(page.getByRole("dialog")).toHaveCount(0);
await page.screenshot({
  path: "../docs/screenshots/policies-populated.png",
  fullPage: true,
});
await page.getByRole("button", { name: "Playground", exact: true }).click();
await page
  .getByLabel("Protected object", { exact: true })
  .selectOption(reference.object_id);
await page
  .getByLabel("What does the agent need to know?")
  .fill(
    "Which employees have birthdays in the next 14 calendar dates, including today?",
  );
await page
  .getByRole("button", { name: "Send to Airlock", exact: true })
  .click();
await page
  .getByRole("button", { name: "Inspect record" })
  .waitFor({ timeout: 120000 });
await expect(page.locator(".answer-panel .response-text")).toContainText(
  "Maya Chen",
);
await expect(page.locator(".answer-panel .response-text")).toContainText(
  "Jordan Patel",
);
await expect(page.locator(".answer-panel .response-text")).not.toContainText(
  "000-00",
);
await page.screenshot({
  path: "../docs/screenshots/playground-answer.png",
  fullPage: true,
});
await page.getByRole("button", { name: "Inspect record" }).click();
await page.getByRole("heading", { name: "A closer look." }).waitFor();
const firstRequest = await page.locator(".record-id code").textContent();
await expect(page.getByRole("dialog")).toContainText(
  "CALLER-SUPPLIED · UNVERIFIED",
);
await expect(page.getByRole("dialog")).toContainText("REV 1");
await page.screenshot({
  path: "../docs/screenshots/access-record.png",
  fullPage: true,
});
await page.getByRole("button", { name: "Close access record" }).click();
// Edit the object policy, then issue a new request through the same UI.
await page.getByRole("button", { name: "Policy studio", exact: true }).click();
const card = page.locator(".policy-card").filter({
  has: page.getByRole("heading", { name: policyName, exact: true }),
});
await card.getByRole("button", { name: "Edit policy" }).click();
await page
  .getByLabel("Policy instructions")
  .fill(
    "For this object, disclose only aggregate employee counts. Never reveal employee names or individual birthday dates, even for birthday planning. If asked who has upcoming birthdays, provide only the count for opted-in employees on the supplied user’s team.",
  );
await page.getByRole("button", { name: "Save policy", exact: true }).click();
await expect(page.getByRole("dialog")).toHaveCount(0);
await expect(card).toContainText("REV 02");
await page.getByRole("button", { name: "Playground", exact: true }).click();
await page
  .getByRole("button", { name: "Send to Airlock", exact: true })
  .click();
await page
  .getByRole("button", { name: "Inspect record" })
  .waitFor({ timeout: 120000 });
await expect(page.locator(".answer-panel .response-text")).not.toContainText(
  "Maya Chen",
);
await expect(page.locator(".answer-panel .response-text")).not.toContainText(
  "Jordan Patel",
);
await page.getByRole("button", { name: "Inspect record" }).click();
await expect(page.getByRole("dialog")).toContainText("REV 2");
const secondRequest = await page.locator(".record-id code").textContent();
await page.getByRole("button", { name: "Close access record" }).click();
await page.getByRole("button", { name: "Access history", exact: true }).click();
await page.getByLabel("Filter by object").selectOption(reference.object_id);
await expect(page.locator(".history-row")).toHaveCount(2);
await page.screenshot({
  path: "../docs/screenshots/history.png",
  fullPage: true,
});
await page.locator(".history-row").last().click();
await expect(page.getByRole("dialog")).toContainText("REV 1");
await expect(page.getByRole("dialog")).toContainText("Maya Chen");
await page.getByRole("button", { name: "Close access record" }).click();
// Reload clears all browser-held bytes; explicitly reattach the downloaded file.
await page.reload();
await page.getByRole("heading", { name: "Context under control." }).waitFor();
await page.getByRole("button", { name: "Playground", exact: true }).click();
await page
  .getByLabel("Protected object", { exact: true })
  .selectOption(reference.object_id);
await expect(
  page.getByRole("button", { name: "Send to Airlock", exact: true }),
).toBeDisabled();
await page.getByLabel("Local encrypted file").setInputFiles(referencePath);
await expect(
  page.getByRole("button", { name: "Send to Airlock", exact: true }),
).toBeEnabled();
// Narrow viewport and all navigation destinations remain usable.
await page.setViewportSize({ width: 390, height: 844 });
await page.getByRole("button", { name: "Playground", exact: true }).click();
await page.screenshot({
  path: "../docs/screenshots/playground-mobile.png",
  fullPage: true,
});
expect(
  await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  ),
).toBe(true);
await page.getByRole("button", { name: "Policy studio", exact: true }).click();
await page.screenshot({
  path: "../docs/screenshots/policies-mobile.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Protected objects", exact: true })
  .click();
await page.screenshot({
  path: "../docs/screenshots/objects-mobile.png",
  fullPage: true,
});
expect(
  await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  ),
).toBe(true);
expect(errors).toEqual([]);
await fs.writeFile(
  "../demo-workspace/ui-verification.json",
  JSON.stringify(
    {
      object_id: reference.object_id,
      referencePath,
      firstRequest,
      secondRequest,
      policyName,
      browserErrors: errors,
      passed: true,
    },
    null,
    2,
  ),
);
console.log("UI workflow verified:", {
  object: reference.object_id,
  firstRequest,
  secondRequest,
  browserErrors: errors,
});
await browser.close();
