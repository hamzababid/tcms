import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Choose `text` in a searchable picker (components/ui/combobox.tsx): open it, type to narrow when it has a
 * search box, then click the matching option. Looks only inside the popover this trigger opened
 * (`aria-controls`), not at other lists on the page.
 */
export async function pick(page: Page, trigger: Locator, text: string): Promise<void> {
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  const id = await trigger.getAttribute("aria-controls");
  if (!id) throw new Error("picker did not open");
  const panel = page.locator(`[id="${id}"]`);
  await expect(panel.getByRole("listbox")).toBeVisible();
  const search = panel.getByRole("combobox");
  if (await search.count()) await search.fill(text);
  await panel.getByRole("option", { name: text }).first().click();
  await expect(panel).toBeHidden();
}
