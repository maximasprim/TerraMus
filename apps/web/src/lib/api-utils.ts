/**
 * Pure helpers shared by the tenant and platform-admin API clients (no
 * browser/React dependencies, so they're trivially unit-testable).
 */

interface ValidationIssue {
  loc?: unknown[];
  msg?: string;
}

/**
 * Turns the `detail` of an error response into text a person can read.
 *
 * FastAPI answers validation failures (HTTP 422) with an ARRAY of
 * `{ loc: ["body", "farm_id"], msg: "Field required", type: ... }` objects.
 * Without this, forms displayed that array as raw JSON. Plain string details
 * (everything else the backend raises) pass through untouched, and any other
 * shape falls back to JSON exactly as before.
 */
export function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (
    Array.isArray(detail) &&
    detail.length > 0 &&
    detail.every((d) => d !== null && typeof d === "object" && "msg" in (d as object))
  ) {
    const lines = (detail as ValidationIssue[]).map((issue) => {
      const field = (issue.loc ?? [])
        .filter((p): p is string => typeof p === "string" && p !== "body" && p !== "query" && p !== "path")
        .pop();
      const message = String(issue.msg ?? "Invalid value").replace(/^Value error, /, "");
      return field ? `${field.replace(/_/g, " ")}: ${message}` : message;
    });
    return [...new Set(lines)].join("; ");
  }
  return JSON.stringify(detail);
}

export interface FetchAllOptions {
  /** Rows requested per page. Must not exceed the endpoint's own maximum. */
  pageSize?: number;
  /** Hard stop so a runaway/huge table can never loop forever. */
  maxPages?: number;
  /** "page": ?page=N&page_size=M (livestock, crops, platform orgs). "offset": ?limit=M&offset=K (inquiries). */
  style?: "page" | "offset";
}

/**
 * Several backend list endpoints return ONE page only (default 25-50 rows,
 * no total count), so a plain GET silently drops everything after the first
 * page. This walks the pages until one comes back short and returns the lot.
 */
export async function fetchAllPages<T>(
  path: string,
  fetchPage: (url: string) => Promise<T[]>,
  { pageSize = 200, maxPages = 25, style = "page" }: FetchAllOptions = {},
): Promise<T[]> {
  const joiner = path.includes("?") ? "&" : "?";
  const all: T[] = [];
  for (let i = 0; i < maxPages; i++) {
    const query = style === "page" ? `page=${i + 1}&page_size=${pageSize}` : `limit=${pageSize}&offset=${i * pageSize}`;
    const batch = await fetchPage(`${path}${joiner}${query}`);
    all.push(...batch);
    if (batch.length < pageSize) break;
  }
  return all;
}
