import { expect, test } from "@playwright/test";

test("Studio Dashboard loads with core elements", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/Clinic Studio/);

  const header = page.getByRole("heading", { level: 1 });
  await expect(header).toContainText("Clinic Studio");

  await expect(page.getByTestId("blueprint-selection")).toBeVisible();
  await expect(page.getByTestId("generate-button")).toBeVisible();
});
