import { describe, it, expect } from "vitest";
import { parseReportIssueUrl } from "./reportIssue";

describe("parseReportIssueUrl", () => {
  it("returns a configured https URL", () => {
    expect(parseReportIssueUrl({ report_issue_url: "https://example.com/new" })).toBe(
      "https://example.com/new",
    );
  });
  it("hides the link for an empty value", () => {
    expect(parseReportIssueUrl({ report_issue_url: "" })).toBe("");
  });
  it("hides the link when the field is missing or the payload is invalid", () => {
    expect(parseReportIssueUrl({})).toBe("");
    expect(parseReportIssueUrl(null)).toBe("");
    expect(parseReportIssueUrl("x")).toBe("");
  });
  it("rejects non-http(s) schemes", () => {
    expect(parseReportIssueUrl({ report_issue_url: "javascript:alert(1)" })).toBe("");
    expect(parseReportIssueUrl({ report_issue_url: "not a url" })).toBe("");
  });
});
