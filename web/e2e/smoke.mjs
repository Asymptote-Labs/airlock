import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
const baseURL = process.env.AIRLOCK_BROKER_URL || "http://127.0.0.1:8100";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.goto(baseURL);
await expect(
  page.getByRole("heading", { name: "Context under control." }),
).toBeVisible();
await expect(
  page.getByText("Local broker connected", { exact: true }),
).toBeVisible();
await expect(page.getByLabel("Admin credential")).toHaveCount(0);
await expect(page.getByRole("button", { name: "Lock workspace" })).toHaveCount(
  0,
);
for (const name of [
  "Policy studio",
  "Playground",
  "Access history",
  "Protected objects",
]) {
  await page.getByRole("button", { name, exact: true }).click();
}
await page.reload();
await expect(
  page.getByText("Local broker connected", { exact: true }),
).toBeVisible();
const status = await page.request.get(`${baseURL}/admin/status`);
expect(status.status()).toBe(200);
expect((await status.json()).identity).toBe("local-dashboard");
// Invalid form still passes automatic admin authentication and reaches validation.
const form = await page.request.post(`${baseURL}/admin/playground`);
expect(form.status()).toBe(422);
const agent = await page.request.post(`${baseURL}/v1/context/request`);
expect(agent.status()).toBe(401);
await expect(page.getByRole("alert")).toHaveCount(0);
await fs.mkdir("../docs/screenshots", { recursive: true });
await page.screenshot({
  path: "../docs/screenshots/dashboard-direct-entry.png",
});
expect(errors).toEqual([]);
await browser.close();
console.log(
  "Direct entry, automatic session, navigation, reload, and agent credential separation passed.",
);
