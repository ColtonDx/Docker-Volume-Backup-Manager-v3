/* ---------------------------------------------------------------
 * TypeScript types matching backend Pydantic schemas
 * --------------------------------------------------------------- */

// Auth
export interface LoginRequest {
  password: string;
}

export interface TokenResponse {
  token: string;
}

// Storage Backends
export interface StorageBackendConfig {
  path?: string;
  bucket?: string;
  region?: string;
  access_key_id?: string;
  secret_access_key?: string;
  endpoint_url?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  use_tls?: boolean;
  use_sftp?: boolean;
  remote_name?: string;
  flags?: string;
  [key: string]: unknown;
}

export interface StorageBackend {
  id: number;
  name: string;
  type: "localfs" | "s3" | "ftp" | "rclone";
  config: StorageBackendConfig;
  created_at: string;
  updated_at: string;
}

export interface StorageBackendCreate {
  name: string;
  type: string;
  config: StorageBackendConfig;
}

export interface StorageBackendUpdate {
  name?: string;
  type?: string;
  config?: StorageBackendConfig;
}

// Schedules
export interface Schedule {
  id: number;
  name: string;
  cron: string;
  description: string | null;
  enabled: boolean;
  job_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCreate {
  name: string;
  cron: string;
  description?: string;
  enabled?: boolean;
}

export interface ScheduleUpdate {
  name?: string;
  cron?: string;
  description?: string;
  enabled?: boolean;
}

// Retention Policies
export interface RetentionPolicy {
  id: number;
  name: string;
  description: string | null;
  retention_days: number;
  min_backups: number;
  max_backups: number | null;
  job_count: number;
  created_at: string;
  updated_at: string;
}

export interface RetentionPolicyCreate {
  name: string;
  description?: string;
  retention_days: number;
  min_backups?: number;
  max_backups?: number;
}

export interface RetentionPolicyUpdate {
  name?: string;
  description?: string;
  retention_days?: number;
  min_backups?: number;
  max_backups?: number;
}

// Backup Jobs
export interface BackupJob {
  id: number;
  name: string;
  label: string;
  enabled: boolean;
  storage: StorageBackend | null;
  schedule: Schedule | null;
  retention: RetentionPolicy | null;
  containers: string[];
  status: "active" | "running" | "error" | "idle";
  last_run: string | null;
  next_run: string | null;
  created_at: string;
  updated_at: string;
}

export interface BackupJobCreate {
  name: string;
  storage_id: number;
  schedule_id?: number | null;
  retention_id?: number | null;
  enabled?: boolean;
}

export interface BackupJobUpdate {
  name?: string;
  storage_id?: number;
  schedule_id?: number | null;
  retention_id?: number | null;
  enabled?: boolean;
}

// Backup Records
export interface BackupRecord {
  id: number;
  job_id: number;
  job_name: string;
  status: "running" | "success" | "error" | "warning";
  size_bytes: number | null;
  duration_seconds: number | null;
  file_path: string | null;
  storage_path: string | null;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  containers_stopped: string[];
  volumes_backed_up: string[];
}

// Log Entries
export interface LogEntry {
  id: number;
  level: "info" | "success" | "warning" | "error";
  job_name: string | null;
  message: string;
  details: string | null;
  created_at: string;
}

// Notification Channels
export interface NotificationChannel {
  id: number;
  name: string;
  type: "email" | "slack" | "discord" | "gotify" | "ntfy" | "webhook";
  config: Record<string, unknown>;
  events: string[];
  enabled: boolean;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationChannelCreate {
  name: string;
  type: string;
  config: Record<string, unknown>;
  events: string[];
  enabled?: boolean;
}

export interface NotificationChannelUpdate {
  name?: string;
  type?: string;
  config?: Record<string, unknown>;
  events?: string[];
  enabled?: boolean;
}

// Settings
export interface SettingsBundle {
  settings: Record<string, unknown>;
}

// Dashboard
export interface DashboardStats {
  total_jobs: number;
  active_jobs: number;
  total_storage_used_bytes: number;
  storage_backends_count: number;
  success_rate_30d: number;
  active_alerts: number;
  recent_jobs: BackupRecord[];
  upcoming_schedules: Array<{
    id: number;
    name: string;
    cron: string;
    description: string | null;
    next_run: string | null;
    job_names: string[];
  }>;
  storage_usage: Array<{
    name: string;
    used: number;
    total: number;
  }>;
}

// Docker
export interface ContainerInfo {
  id: string;
  name: string;
  image: string;
  status: string;
  labels: Record<string, string>;
  volumes: string[];
}

// Generic message response
export interface MessageResponse {
  message: string;
}

export interface TestResponse {
  success: boolean;
  message: string;
}

export interface ImportBackupsResponse {
  imported: number;
  skipped: number;
  total_found: number;
  message: string;
}

export interface JobDetailStats {
  job: BackupJob;
  success_rate_30d: number;
  total_backups: number;
  total_size_bytes: number;
  avg_duration_seconds: number | null;
  errors_24h: number;
  recent_backups: BackupRecord[];
  logs: LogEntry[];
  schedule_info: { name: string; cron: string; next_run: string | null } | null;
}
