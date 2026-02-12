import { Database, HardDrive, CheckCircle, AlertTriangle, Clock, Activity, Gauge } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataCard } from "@/components/ui/DataCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { fetchDashboard } from "@/api";

interface GaugeDisplayProps {
  value: number;
  max: number;
  label: string;
  color: string;
}

function GaugeDisplay({ value, max, label, color }: GaugeDisplayProps) {
  const percentage = max > 0 ? Math.round((value / max) * 100) : 0;
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset = circumference - (percentage / 100) * circumference * 0.75;
  
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-[135deg]" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" className="text-muted" strokeDasharray={`${circumference * 0.75} ${circumference}`} />
          <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" className={color} strokeDasharray={`${circumference * 0.75} ${circumference}`} strokeDashoffset={strokeDashoffset} style={{ transition: 'stroke-dashoffset 0.5s ease' }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold">{percentage}%</span>
        </div>
      </div>
      <span className="text-sm text-muted-foreground mt-2">{label}</span>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes >= 1_099_511_627_776) return `${(bytes / 1_099_511_627_776).toFixed(1)} TB`;
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  return `${bytes} B`;
}

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    refetchInterval: 30000,
  });

  if (isLoading || !stats) {
    return (
      <div>
        <PageHeader title="Dashboard" description="Overview of your Docker container backup system" />
        <div className="text-center text-muted-foreground py-12">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Dashboard" description="Overview of your Docker container backup system" />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <DataCard title="Total Backup Jobs" value={stats.total_jobs} subtitle={`${stats.active_jobs} active`} icon={Database} href="/jobs" />
        <DataCard title="Storage Backends" value={stats.storage_backends_count} subtitle="Configured backends" icon={HardDrive} href="/storages" />
        <DataCard title="Success Rate" value={`${stats.success_rate_30d}%`} subtitle="Last 30 days" icon={CheckCircle} href="/logs" />
        <DataCard title="Active Alerts" value={stats.active_alerts} subtitle="Last 24 hours" icon={AlertTriangle} href="/logs" />
      </div>

      {stats.storage_usage.length > 0 && (
        <Card className="glass-panel border-border mb-6">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Gauge className="h-5 w-5 text-primary" />
              Storage Backend Usage
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {stats.storage_usage.map((backend, idx) => (
                <GaugeDisplay
                  key={backend.name}
                  value={backend.used}
                  max={backend.total}
                  label={backend.name}
                  color={`text-chart-${(idx % 4) + 1}`}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 glass-panel border-border">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Activity className="h-5 w-5 text-primary" />
              Recent Backup Jobs
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {stats.recent_jobs.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground">No recent backups</div>
              ) : (
                stats.recent_jobs.map((job) => (
                  <div key={job.id} className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="h-9 w-9 rounded-lg bg-secondary flex items-center justify-center">
                        <Database className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div>
                        <p className="font-medium text-sm">{job.job_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {job.volumes_backed_up?.join(", ") || "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-muted-foreground font-mono">
                        {job.size_bytes ? formatSize(job.size_bytes) : "—"}
                      </span>
                      <StatusBadge status={job.status} />
                      <span className="text-xs text-muted-foreground w-28 text-right">
                        {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Clock className="h-5 w-5 text-primary" />
              Upcoming Schedules
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {stats.upcoming_schedules.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground">No schedules configured</div>
              ) : (
                stats.upcoming_schedules.map((schedule) => (
                  <div key={schedule.id} className="p-4 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between mb-1">
                      <p className="font-medium text-sm">{schedule.name}</p>
                      <code className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground">
                        {schedule.cron}
                      </code>
                    </div>
                    <p className="text-xs text-muted-foreground">{schedule.description || "—"}</p>
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
