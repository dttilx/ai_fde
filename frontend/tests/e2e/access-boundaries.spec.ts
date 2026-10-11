import { test, expect } from "@playwright/test";

test("unauthenticated pages do not expose incident or diagnosis identifiers", async ({ page }) => {
  await page.goto("/incidents/private-run");
  await expect(page.getByText(/登录|现场诊断工作台/).first()).toBeVisible();
  await expect(page.locator("body")).not.toContainText("raw_description");
  await expect(page.locator("body")).not.toContainText("apx_session");
});
