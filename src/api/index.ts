/**
 * API functions – thin wrappers around the fetch client.
 */
import { api, setToken } from "./client";
import type {
  BackupJob,
  BackupJobCreate,
  BackupJobUpdate,
  BackupRecord,
  DashboardStats,
  ImportBackupsResponse,
  JobDetailStats,
  LogEntry,
  MessageResponse,
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelUpdate,
  RetentionPolicy,
  RetentionPolicyCreate,
  RetentionPolicyUpdate,
  Schedule,
  ScheduleCreate,
  ScheduleUpdate,
  SettingsBundle,
  StorageBackend,
  StorageBackendCreate,
  StorageBackendUpdate,
  TestResponse,
  TokenResponse,
  UptimeKumaTestResponse,
  UptimeKumaMonitorsResponse,
} from "./types";

// Re-export for convenience
export { setToken } from "./client";
export type * from "./types";

// ---- Auth ---------------------------------------------------------------
export async function login(password: string): Promise<string> {
  const res = await api.post<TokenResponse>("/auth/login", { password });
  setToken(res.token);
  return res.token;
}

export function logout() {
  setToken(null);
}

// ---- Dashboard ----------------------------------------------------------
export const fetchDashboard = () => api.get<DashboardStats>("/dashboard");

// ---- Backup Jobs --------------------------------------------------------
export const fetchJobs = () => api.get<BackupJob[]>("/jobs");
export const fetchJob = (id: number) => api.get<BackupJob>(`/jobs/${id}`);
export const fetchJobStats = (id: number) => api.get<JobDetailStats>(`/jobs/${id}/stats`);
export const createJob = (data: BackupJobCreate) => api.post<BackupJob>("/jobs", data);
export const updateJob = (id: number, data: BackupJobUpdate) => api.put<BackupJob>(`/jobs/${id}`, data);
export const deleteJob = (id: number) => api.delete<void>(`/jobs/${id}`);
export const runJob = (id: number) => api.post<MessageResponse>(`/jobs/${id}/run`);
export const pauseJob = (id: number) => api.post<MessageResponse>(`/jobs/${id}/pause`);
export const resumeJob = (id: number) => api.post<MessageResponse>(`/jobs/${id}/resume`);

// ---- Schedules ----------------------------------------------------------
export const fetchSchedules = () => api.get<Schedule[]>("/schedules");
export const fetchSchedule = (id: number) => api.get<Schedule>(`/schedules/${id}`);
export const createSchedule = (data: ScheduleCreate) => api.post<Schedule>("/schedules", data);
export const updateSchedule = (id: number, data: ScheduleUpdate) => api.put<Schedule>(`/schedules/${id}`, data);
export const deleteSchedule = (id: number) => api.delete<void>(`/schedules/${id}`);

// ---- Storage Backends ---------------------------------------------------
export const fetchStorages = () => api.get<StorageBackend[]>("/storages");
export const fetchStorage = (id: number) => api.get<StorageBackend>(`/storages/${id}`);
export const createStorage = (data: StorageBackendCreate) => api.post<StorageBackend>("/storages", data);
export const updateStorage = (id: number, data: StorageBackendUpdate) => api.put<StorageBackend>(`/storages/${id}`, data);
export const deleteStorage = (id: number) => api.delete<void>(`/storages/${id}`);
export const testStorage = (id: number) => api.post<TestResponse>(`/storages/${id}/test`);
export const fetchRcloneRemotes = () => api.get<{ remotes: string[]; error?: string }>("/storages/rclone/remotes");

// ---- Retention Policies -------------------------------------------------
export const fetchRotations = () => api.get<RetentionPolicy[]>("/rotations");
export const fetchRotation = (id: number) => api.get<RetentionPolicy>(`/rotations/${id}`);
export const createRotation = (data: RetentionPolicyCreate) => api.post<RetentionPolicy>("/rotations", data);
export const updateRotation = (id: number, data: RetentionPolicyUpdate) => api.put<RetentionPolicy>(`/rotations/${id}`, data);
export const deleteRotation = (id: number) => api.delete<void>(`/rotations/${id}`);
export const runCleanup = (id: number) => api.post<MessageResponse>(`/rotations/${id}/run`);

// ---- Backup Records -----------------------------------------------------
export const fetchBackups = (params?: { job_id?: number; status?: string; limit?: number; offset?: number }) => {
  const q = new URLSearchParams();
  if (params?.job_id) q.set("job_id", String(params.job_id));
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return api.get<BackupRecord[]>(`/backups${qs ? `?${qs}` : ""}`);
};
export const fetchBackup = (id: number) => api.get<BackupRecord>(`/backups/${id}`);
export const restoreBackup = (id: number) => api.post<MessageResponse>(`/backups/${id}/restore`);
export const deleteBackup = (id: number) => api.delete<void>(`/backups/${id}`);
export const importBackups = (jobId: number) => api.post<ImportBackupsResponse>(`/backups/import?job_id=${jobId}`);

// ---- Logs ---------------------------------------------------------------
export const fetchLogs = (params?: { level?: string; job_name?: string; search?: string; limit?: number }) => {
  const q = new URLSearchParams();
  if (params?.level && params.level !== "all") q.set("level", params.level);
  if (params?.job_name) q.set("job_name", params.job_name);
  if (params?.search) q.set("search", params.search);
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return api.get<LogEntry[]>(`/logs${qs ? `?${qs}` : ""}`);
};
export const clearLogs = (level?: string) => {
  const q = level ? `?level=${level}` : "";
  return api.delete<void>(`/logs${q}`);
};

// ---- Notifications ------------------------------------------------------
export const fetchNotifications = () => api.get<NotificationChannel[]>("/notifications");
export const fetchNotification = (id: number) => api.get<NotificationChannel>(`/notifications/${id}`);
export const createNotification = (data: NotificationChannelCreate) => api.post<NotificationChannel>("/notifications", data);
export const updateNotification = (id: number, data: NotificationChannelUpdate) => api.put<NotificationChannel>(`/notifications/${id}`, data);
export const deleteNotification = (id: number) => api.delete<void>(`/notifications/${id}`);
export const testNotification = (id: number) => api.post<TestResponse>(`/notifications/${id}/test`);

// ---- Settings -----------------------------------------------------------
export const fetchSettings = () => api.get<SettingsBundle>("/settings");
export const updateSettings = (settings: Record<string, unknown>) => api.put<SettingsBundle>("/settings", { settings });
export const resetSettings = () => api.post<SettingsBundle>("/settings/reset");

// ---- Uptime Kuma --------------------------------------------------------
export const testUptimeKuma = () => api.post<UptimeKumaTestResponse>("/settings/uptime-kuma/test");
export const fetchUptimeKumaMonitors = () => api.get<UptimeKumaMonitorsResponse>("/settings/uptime-kuma/monitors");
