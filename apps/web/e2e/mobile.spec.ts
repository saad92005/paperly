import { expect, test } from "@playwright/test";

test("landing and login fit a 375px screen without horizontal scroll", async ({ page }) => {
  for (const path of ["/", "/login"]) {
    await page.goto(path);
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(375);
  }
});
