/** "p. 4", "pp. 3-5" for consecutive pages, or "pp. 2, 7" otherwise. */
export function pagesLabel(pages: number[]): string {
  if (pages.length === 0) return "";
  const first = pages[0]!;
  const last = pages[pages.length - 1]!;
  if (first === last) return `p. ${first}`;
  return last - first === pages.length - 1 ? `pp. ${first}-${last}` : `pp. ${pages.join(", ")}`;
}
