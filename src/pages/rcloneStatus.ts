import type { RcloneStatus } from "@/api/types";

const MASK = "********";

/** One-line, read-only description of where the rclone config comes from. */
export function describeRcloneStatus(status?: RcloneStatus): string {
  if (!status) return "";
  const remotes = status.remotes.length ? `remotes: ${status.remotes.join(", ")}` : "no remotes found";
  if (status.source === "file") return `Using config file at ${status.config_path}: ${remotes}`;
  if (status.source === "ui") {
    return status.file_exists
      ? `Using the config saved in Settings (written to ${status.config_path}): ${remotes}`
      : `Using the config saved in Settings (will be written to ${status.config_path})`;
  }
  return `No rclone config found at ${status.config_path}`;
}

/**
 * True when saving would replace an rclone config file that was not written by
 * Settings (for example a mounted file), so the user must confirm first.
 */
export function needsRcloneOverwriteConfirm(
  formText: unknown,
  savedText: unknown,
  status?: RcloneStatus,
): boolean {
  if (!status?.file_exists || !status.file_differs_from_saved) return false;
  if (typeof formText !== "string" || !formText.trim() || formText === MASK) return false;
  return formText !== savedText;
}
