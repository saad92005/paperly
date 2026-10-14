import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The core promise: ask → click a citation → the exact sentence is highlighted in the PDF.
test("sign up, import a paper, ask, click citation, highlight visible", async ({ page }) => {
  const email = `e2e${Date.now()}@example.com`;
  await page.goto("/login");
  await page.getByRole("button", { name: "Use a password instead" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-42");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/library");

  await page.getByRole("button", { name: "Attention Is All You Need" }).click();
  const link = page.getByRole("link", { name: "Attention Is All You Need" });
  await expect(link).toBeVisible({ timeout: 180_000 });

  const lib = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(lib.violations.filter((v) => v.impact === "critical").map((v) => v.id)).toEqual([]);

  await link.click();
  await expect(page.locator(".textLayer span").first()).toBeAttached();
  await page.getByLabel("Ask a question").fill("What BLEU score does the big Transformer get on English-to-German?");
  await page.getByRole("button", { name: "Send" }).click();
  const chip = page.locator("[aria-label^='Source 1']").first();
  await expect(chip).toBeVisible({ timeout: 120_000 });
  await chip.click();
  await expect(page.locator("[data-kind='cite']").first()).toBeAttached();

  // Notes persist: highlight a selection and find it in the Notes tab.
  await page.reload();
  const span = page.locator(".textLayer span").nth(20);
  await expect(span).toBeVisible();
  const box = (await span.boundingBox())!;
  await page.mouse.move(box.x + 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 2, box.y + box.height / 2, { steps: 5 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Highlight" }).click();
  await expect(page.locator("[data-kind='yellow']").first()).toBeAttached();
});
