/** Extract the "Report a problem" URL from the /api/health payload.
 *  Returns "" (link hidden) unless the value is an absolute http(s) URL. */
export function parseReportIssueUrl(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const raw = (data as { report_issue_url?: unknown }).report_issue_url;
  if (typeof raw !== "string") return "";
  const value = raw.trim();
  try {
    const { protocol } = new URL(value);
    return protocol === "https:" || protocol === "http:" ? value : "";
  } catch {
    return "";
  }
}

/** Fetch the configured URL from the unauthenticated health endpoint.
 *  The endpoint answers 503 when degraded but still includes the field. */
export async function fetchReportIssueUrl(): Promise<string> {
  try {
    const res = await fetch("/api/health");
    return parseReportIssueUrl(await res.json());
  } catch {
    return "";
  }
}
