import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Database, CheckCircle, AlertTriangle, Clock, Activity, HardDrive, Timer, Calendar, FileText,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataCard } from "@/components/ui/DataCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchJobStats } from "@/api";

function formatSize(bytes: number): string {
  if (bytes >= 1_099_511_627_776) return `${(bytes / 1_099_511_627_776).toFixed(1)} TB`;
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1_024) return `${(bytes / 1_024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

const logLevelStyles: Record<string, string> = {
  info: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  error: "text-destructive",
};

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const jobId = Number(id);

  const { data: stats, isLoading, isError, error } = useQuery({
    queryKey: ["job-stats", jobId],
    queryFn: () => fetchJobStats(jobId),
    enabled: !isNaN(jobId),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div>
        <PageHeader
          title="Job Details"
          description="Loading..."
          action={
            <Button variant="outline" className="gap-2" onClick={() => navigate("/jobs")}>
              <ArrowLeft className="h-4 w-4" /> Back to Jobs
            </Button>
          }
        />
        <div className="text-center text-muted-foreground py-12">Loading job details...</div>
      </div>
    );
  }

  if (isError || !stats) {
    return (
      <div>
        <PageHeader
          title="Job Details"
          description="Failed to load"
          action={
            <Button variant="outline" className="gap-2" onClick={() => navigate("/jobs")}>
              <ArrowLeft className="h-4 w-4" /> Back to Jobs
            </Button>
          }
        />
        <div className="text-center text-destructive py-12">
          {error instanceof Error ? error.message : "Could not load job details. The job may have been deleted."}
        </div>
      </div>
    );
  }

  const { job } = stats;

  return (
    <div>
      <PageHeader
        title={job.name}
        description={`${job.label} — ${job.containers?.length ?? 0} container(s) matched`}
        action={
          <Button variant="outline" className="gap-2" onClick={() => navigate("/jobs")}>
            <ArrowLeft className="h-4 w-4" /> Back to Jobs
          </Button>
        }
      />

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <DataCard
          title="Success Rate"
          value={stats.success_rate_30d < 0 ? "No runs" : `${stats.success_rate_30d}%`}
          subtitle="Last 30 days"
          icon={CheckCircle}
        />
        <DataCard
          title="Total Backups"
          value={stats.total_backups}
          subtitle={formatSize(stats.total_size_bytes)}
          icon={Database}
        />
        <DataCard
          title="Avg Duration"
          value={stats.avg_duration_seconds != null ? formatDuration(stats.avg_duration_seconds) : "—"}
          subtitle="Per backup"
          icon={Timer}
        />
        <DataCard
          title="Alerts (24h)"
          value={stats.errors_24h}
          subtitle="Errors & warnings"
          icon={AlertTriangle}
        />
      </div>

      {/* Job info strip */}
      <Card className="glass-panel border-border mb-6">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Status:</span>
              <StatusBadge status={job.status as "active" | "running" | "error" | "idle"} />
            </div>
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">Storage:</span>
              <span>{job.storage?.name ?? "None"}</span>
            </div>
            {stats.schedule_info && (
              <>
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Schedule:</span>
                  <span>{stats.schedule_info.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">({stats.schedule_info.cron})</span>
                </div>
                {stats.schedule_info.next_run && (
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Next run:</span>
                    <span>{new Date(stats.schedule_info.next_run).toLocaleString()}</span>
                  </div>
                )}
              </>
            )}
            {job.retention && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Retention:</span>
                <span>{job.retention.name}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Backup history */}
        <Card className="lg:col-span-2 glass-panel border-border">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Activity className="h-5 w-5 text-primary" />
              Backup History
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border max-h-[480px] overflow-auto">
              {stats.recent_backups.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground">No backups recorded yet</div>
              ) : (
                stats.recent_backups.map((record) => (
                  <div key={record.id} className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="h-9 w-9 rounded-lg bg-secondary flex items-center justify-center">
                        <Database className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div>
                        <p className="font-medium text-sm">
                          {record.volumes_backed_up?.length
                            ? record.volumes_backed_up.join(", ")
                            : record.storage_path || "Backup"
                          }
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {record.containers_stopped?.length
                            ? `Containers: ${record.containers_stopped.join(", ")}`
                            : "—"
                          }
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-muted-foreground font-mono">
                        {record.size_bytes ? formatSize(record.size_bytes) : "—"}
                      </span>
                      {record.duration_seconds != null && (
                        <span className="text-sm text-muted-foreground font-mono">
                          {formatDuration(record.duration_seconds)}
                        </span>
                      )}
                      <StatusBadge status={record.status as "success" | "warning" | "error" | "running"} />
                      <span className="text-xs text-muted-foreground w-32 text-right">
                        {record.started_at ? new Date(record.started_at).toLocaleString() : "—"}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Job log */}
        <Card className="glass-panel border-border">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5 text-primary" />
              Job Log
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border max-h-[480px] overflow-auto">
              {stats.logs.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground">No log entries</div>
              ) : (
                stats.logs.map((log) => (
                  <div key={log.id} className="p-3 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-xs font-semibold uppercase ${logLevelStyles[log.level] ?? "text-muted-foreground"}`}>
                        {log.level}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm">{log.message}</p>
                    {log.details && (
                      <p className="text-xs text-muted-foreground mt-1 font-mono whitespace-pre-wrap break-all">{log.details}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
