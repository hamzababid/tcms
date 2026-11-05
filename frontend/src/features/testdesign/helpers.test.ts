import { describe, expect, it } from "vitest";

import type { Folder } from "./api";
import { renderMentions } from "./CommentThread";
import { wordDiff } from "./DiffView";
import { buildTree, subtreeIds } from "./FolderTree";
import { parsePastedSteps } from "./StepGrid";

const folder = (id: string, parent: string | null, position = 1, name = id): Folder => ({
  id,
  parent_id: parent,
  name,
  description: null,
  position,
  depth: 1,
  case_count: 0,
  total_count: 0,
  archived: false,
  row_version: 1,
});

describe("wordDiff", () => {
  it("marks inserted and removed words and keeps the rest", () => {
    const parts = wordDiff("Dashboard shown in 3 s", "Dashboard shown within 3 s");
    expect(parts.filter((p) => p.kind === "del").map((p) => p.text.trim())).toEqual(["in"]);
    expect(parts.filter((p) => p.kind === "add").map((p) => p.text.trim())).toEqual(["within"]);
    expect(parts.map((p) => (p.kind === "del" ? "" : p.text)).join("")).toBe("Dashboard shown within 3 s");
  });

  it("handles empty sides", () => {
    expect(wordDiff("", "new")).toEqual([{ text: "new", kind: "add" }]);
    expect(wordDiff("old", "")).toEqual([{ text: "old", kind: "del" }]);
  });
});

describe("parsePastedSteps", () => {
  it("splits spreadsheet rows into action and expected result", () => {
    expect(parsePastedSteps("Open page\tForm shown\r\nSubmit\tDashboard\n")).toEqual([
      { action: "Open page", expected_result: "Form shown" },
      { action: "Submit", expected_result: "Dashboard" },
    ]);
  });

  it("leaves a single plain line to the textarea", () => {
    expect(parsePastedSteps("just text")).toBeNull();
  });
});

describe("folder tree", () => {
  const folders = [folder("b", "a", 2), folder("a", null), folder("c", "a", 1), folder("d", "c")];

  it("nests by parent and orders by position", () => {
    const tree = buildTree(folders);
    expect(tree.map((n) => n.folder.id)).toEqual(["a"]);
    expect(tree[0]?.children.map((n) => n.folder.id)).toEqual(["c", "b"]);
  });

  it("collects a subtree (drop targets that would create a cycle)", () => {
    expect([...subtreeIds(folders, "c")].sort()).toEqual(["c", "d"]);
  });
});

describe("renderMentions", () => {
  it("shows mention tokens as bold names", () => {
    expect(renderMentions("Hi @[Sana Malik](user:0193a1b2-0000-7000-8000-000000000001) please check")).toBe(
      "Hi **@Sana Malik** please check",
    );
  });
});

describe("deviceName", () => {
  it("summarises common user agents", async () => {
    const { deviceName } = await import("@/features/profile/ProfilePage");
    expect(
      deviceName(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      ),
    ).toBe("Chrome on Windows");
    expect(
      deviceName("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605 Version/17 Safari/605"),
    ).toBe("Safari on macOS");
    expect(deviceName(null)).toBe("Unknown device");
  });
});
