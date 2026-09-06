/**
 * Profile tag helpers.
 *
 * Tags are free-form grouping labels stored in `<profile>/profile.yaml` and
 * surfaced on `ProfileInfo.tags`. The backend
 * (`hermes_cli/profiles.py::normalize_tags`) is the authority on canonical
 * form; these helpers mirror it closely enough that the dashboard doesn't
 * flash a differently-cased tag between save and refetch.
 */

const TAG_MAX_LEN = 32;
const TAG_MAX_COUNT = 12;

/** Canonicalize one tag; returns "" when nothing usable remains. */
export function normalizeTag(raw: string): string {
  return (raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, TAG_MAX_LEN)
    .replace(/^[-_]+|[-_]+$/g, "");
}

/**
 * Parse a comma-separated tag input field into canonical tags.
 * Whitespace inside one tag folds to `-` ("Work Stuff" -> "work-stuff"), so
 * only commas split entries. De-duplicated, order-preserving, capped.
 */
export function parseTagInput(raw: string): string[] {
  const out: string[] = [];
  for (const part of (raw ?? "").split(",")) {
    const tag = normalizeTag(part);
    if (tag && !out.includes(tag)) out.push(tag);
    if (out.length >= TAG_MAX_COUNT) break;
  }
  return out;
}

/** Render a tag list back into the editor's comma-separated form. */
export function formatTagInput(tags: string[] | undefined): string {
  return (tags ?? []).join(", ");
}

export interface TaggedLike {
  name: string;
  tags?: string[];
}

export interface ProfileTagGroup<T extends TaggedLike> {
  /** Canonical tag, or null for the untagged bucket. */
  tag: string | null;
  profiles: T[];
}

/**
 * Group profiles by tag for the dashboard grid.
 *
 * A profile with several tags appears in each of its groups — grouping is a
 * view, not a partition. Groups are sorted alphabetically by tag; the untagged
 * bucket is always last and is omitted when empty. With no tags anywhere, the
 * result is a single untagged group, which lets the caller render the flat grid
 * unchanged.
 */
export function groupProfilesByTag<T extends TaggedLike>(
  profiles: T[],
): ProfileTagGroup<T>[] {
  const byTag = new Map<string, T[]>();
  const untagged: T[] = [];

  for (const p of profiles) {
    const tags = (p.tags ?? []).filter(Boolean);
    if (tags.length === 0) {
      untagged.push(p);
      continue;
    }
    for (const tag of tags) {
      const bucket = byTag.get(tag);
      if (bucket) bucket.push(p);
      else byTag.set(tag, [p]);
    }
  }

  const groups: ProfileTagGroup<T>[] = [...byTag.keys()]
    .sort((a, b) => a.localeCompare(b))
    .map((tag) => ({ tag, profiles: byTag.get(tag) as T[] }));

  if (untagged.length > 0 || groups.length === 0) {
    groups.push({ tag: null, profiles: untagged });
  }
  return groups;
}

/** Every distinct tag in use, sorted — the filter chip row. */
export function collectTags(profiles: TaggedLike[]): string[] {
  const seen = new Set<string>();
  for (const p of profiles) {
    for (const tag of p.tags ?? []) if (tag) seen.add(tag);
  }
  return [...seen].sort((a, b) => a.localeCompare(b));
}
