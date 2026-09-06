import { describe, expect, it } from "vitest";
import {
  collectTags,
  formatTagInput,
  groupProfilesByTag,
  normalizeTag,
  parseTagInput,
} from "./profile-tags";

describe("normalizeTag", () => {
  it("lowercases and folds punctuation to a single dash", () => {
    expect(normalizeTag("Work Stuff")).toBe("work-stuff");
    expect(normalizeTag("  CODING  ")).toBe("coding");
    expect(normalizeTag("a//b")).toBe("a-b");
  });

  it("strips leading and trailing separators", () => {
    expect(normalizeTag("--weird--")).toBe("weird");
    expect(normalizeTag("_x_")).toBe("x");
  });

  it("returns empty for input with nothing usable", () => {
    expect(normalizeTag("")).toBe("");
    expect(normalizeTag("!!!")).toBe("");
    expect(normalizeTag("   ")).toBe("");
  });

  it("caps length without leaving a trailing separator", () => {
    expect(normalizeTag("x".repeat(50))).toHaveLength(32);
    // A cut landing on a separator must not yield "...-".
    expect(normalizeTag(`${"y".repeat(31)} tail`).endsWith("-")).toBe(false);
  });
});

describe("parseTagInput", () => {
  it("splits on commas only, folding inner whitespace", () => {
    expect(parseTagInput("work, coding ,research")).toEqual([
      "work",
      "coding",
      "research",
    ]);
    expect(parseTagInput("Work Stuff")).toEqual(["work-stuff"]);
  });

  it("de-duplicates while preserving first-seen order", () => {
    expect(parseTagInput("b, a, b")).toEqual(["b", "a"]);
    expect(parseTagInput("Work, work")).toEqual(["work"]);
  });

  it("drops empty entries from sloppy input", () => {
    expect(parseTagInput(",, work ,,")).toEqual(["work"]);
    expect(parseTagInput("")).toEqual([]);
  });

  it("caps the tag count", () => {
    const many = Array.from({ length: 30 }, (_, i) => `t${i}`).join(",");
    expect(parseTagInput(many)).toHaveLength(12);
  });

  it("round-trips through formatTagInput", () => {
    const tags = parseTagInput("Work Stuff, coding");
    expect(parseTagInput(formatTagInput(tags))).toEqual(tags);
  });
});

describe("formatTagInput", () => {
  it("renders a comma-separated editor value", () => {
    expect(formatTagInput(["work", "coding"])).toBe("work, coding");
  });

  it("treats a missing tag list as empty", () => {
    expect(formatTagInput(undefined)).toBe("");
    expect(formatTagInput([])).toBe("");
  });
});

describe("groupProfilesByTag", () => {
  it("sorts groups by tag and puts untagged last", () => {
    const groups = groupProfilesByTag([
      { name: "z", tags: ["work"] },
      { name: "plain" },
      { name: "a", tags: ["coding"] },
    ]);
    expect(groups.map((g) => g.tag)).toEqual(["coding", "work", null]);
  });

  it("lists a multi-tagged profile in each of its groups", () => {
    const groups = groupProfilesByTag([
      { name: "both", tags: ["work", "coding"] },
    ]);
    // Grouping is a view, not a partition.
    expect(groups.map((g) => g.tag)).toEqual(["coding", "work"]);
    for (const g of groups) expect(g.profiles.map((p) => p.name)).toEqual(["both"]);
  });

  it("omits the untagged group when every profile is tagged", () => {
    const groups = groupProfilesByTag([{ name: "a", tags: ["work"] }]);
    expect(groups.map((g) => g.tag)).toEqual(["work"]);
  });

  it("returns one untagged group when nothing is tagged", () => {
    // Lets the caller render the flat grid unchanged.
    const groups = groupProfilesByTag([{ name: "a" }, { name: "b", tags: [] }]);
    expect(groups).toHaveLength(1);
    expect(groups[0].tag).toBeNull();
    expect(groups[0].profiles.map((p) => p.name)).toEqual(["a", "b"]);
  });

  it("returns a single empty untagged group for no profiles", () => {
    expect(groupProfilesByTag([])).toEqual([{ tag: null, profiles: [] }]);
  });
});

describe("collectTags", () => {
  it("returns each distinct tag once, sorted", () => {
    expect(
      collectTags([
        { name: "a", tags: ["work", "coding"] },
        { name: "b", tags: ["work"] },
        { name: "c" },
      ]),
    ).toEqual(["coding", "work"]);
  });

  it("is empty when no profile carries a tag", () => {
    expect(collectTags([{ name: "a" }, { name: "b", tags: [] }])).toEqual([]);
  });
});
