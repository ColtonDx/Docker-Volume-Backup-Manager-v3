import { describe, it, expect } from "vitest";
import type { RcloneStatus } from "@/api/types";
import { describeRcloneStatus, needsRcloneOverwriteConfirm } from "./rcloneStatus";

const base: RcloneStatus = {
  config_path: "/root/.config/rclone/rclone.conf",
  file_exists: true,
  source: "file",
  file_differs_from_saved: true,
  remotes: ["a", "b"],
};

describe("describeRcloneStatus", () => {
  it("describes a mounted file", () => {
    expect(describeRcloneStatus(base)).toBe(
      "Using config file at /root/.config/rclone/rclone.conf: remotes: a, b",
    );
  });
  it("describes a UI config", () => {
    expect(describeRcloneStatus({ ...base, source: "ui", file_differs_from_saved: false })).toContain(
      "saved in Settings",
    );
  });
  it("describes no config", () => {
    expect(describeRcloneStatus({ ...base, source: "none", file_exists: false, remotes: [] })).toContain("No rclone config");
  });
});

describe("needsRcloneOverwriteConfirm", () => {
  it("asks when new text would replace a foreign file", () => {
    expect(needsRcloneOverwriteConfirm("[x]\ntype=s3", "", base)).toBe(true);
  });
  it("does not ask when the text is unchanged or masked", () => {
    expect(needsRcloneOverwriteConfirm("********", "********", base)).toBe(false);
    expect(needsRcloneOverwriteConfirm("same", "same", base)).toBe(false);
  });
  it("does not ask when there is no foreign file", () => {
    expect(needsRcloneOverwriteConfirm("new", "", { ...base, file_exists: false })).toBe(false);
    expect(needsRcloneOverwriteConfirm("new", "old", { ...base, file_differs_from_saved: false })).toBe(false);
  });
});
