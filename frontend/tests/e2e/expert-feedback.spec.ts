import { test, expect } from "@playwright/test";

test("case pages hide approval controls when the draft is not authorized", async ({ page }) => {
  await page.goto("/cases/demo-draft");
  await expect(page.getByRole("heading", { name: "案例审核" })).toBeVisible();
  await expect(page.getByText(/专家不能替代案例审核人/)).toBeVisible();
  await expect(page.getByText(/案例不可访问/)).toBeVisible();
  await expect(page.getByRole("button", { name: "批准并提交发布" })).toHaveCount(0);
});

test("expert and repair pages expose append-only evidence fields", async ({ page }) => {
  await page.route("**/api/me", async route => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ roles: ["EXPERT", "FIELD_ENGINEER"] }) });
  });
  await page.goto("/expert/demo-review");
  await expect(page.getByRole("heading", { name: "专家接管与报告修订" })).toBeVisible();
  await expect(page.getByLabel("依据证据 ID（逗号分隔）")).toBeVisible();
  await page.goto("/incidents/demo-incident/repair");
  await expect(page.getByRole("heading", { name: "维修结果回填" })).toBeVisible();
  await expect(page.getByText(/没有复机证据时保持 UNVERIFIED/)).toBeVisible();
  await expect(page.getByLabel("复机证据 ID（逗号分隔）")).toBeVisible();
});

test("unauthorized repair and expert pages hide mutation controls", async ({ page }) => {
  await page.route("**/api/me", async route => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ roles: ["CASE_REVIEWER"] }) });
  });
  await page.goto("/expert/demo-review");
  await expect(page.getByText(/没有专家修订权限/)).toBeVisible();
  await expect(page.getByRole("button", { name: "追加专家版本" })).toHaveCount(0);
  await page.goto("/incidents/demo-incident/repair");
  await expect(page.getByText(/没有维修结果提交权限/)).toBeVisible();
  await expect(page.getByRole("button", { name: "保存维修反馈" })).toHaveCount(0);
});

test("authorized case reviewer sees scoped evidence and can submit review", async ({ page }) => {
  let reviewed = false;
  await page.route("**/api/case-drafts/demo-draft", async route => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        case_draft_id: "demo-draft", status: reviewed ? "APPROVED" : "DRAFT",
        payload: { confirmed_root_cause: "H1 可能开路", repair_action: "更换后复机", restart_validation: "PASSED" },
        requested_scope: { reader_user_ids: ["engineer-1"] }, publication_status: "NOT_REQUESTED", job: null,
      }) });
    } else {
      reviewed = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    }
  });
  await page.route("**/api/case-drafts/demo-draft/**", async route => {
    reviewed = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.goto("/cases/demo-draft");
  await expect(page.getByText("H1 可能开路")).toBeVisible();
  await page.getByLabel("审核说明").fill("已核对维修和复机证据");
  await page.getByLabel("engineer-1").check();
  await page.getByLabel(/确认脱敏通过/).check();
  await page.getByRole("button", { name: "仅批准案例" }).click();
  await expect(page.getByRole("status")).toContainText("已保存");
});
