import { Database, HardDrive, CheckCircle, AlertTriangle, Clock, Activity, Gauge } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataCard } from "@/components/ui/DataCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const recentJobs = [
  { id: 1, name: "postgres-data", volume: "postgres_data", status: "success" as const, time: "2 min ago", size: "2.4 GB" },
  { id: 2, name: "redis-backup", volume: "redis_data", status: "running" as const, time: "Now", size: "156 MB" },
  { id: 3, name: "nginx-configs", volume: "nginx_config", status: "success" as const, time: "1 hour ago", size: "12 MB" },
  { id: 4, name: "mysql-production", volume: "mysql_data", status: "error" as const, time: "3 hours ago", size: "Failed" },
  { id: 5, name: "grafana-data", volume: "grafana_storage", status: "success" as const, time: "6 hours ago", size: "890 MB" },
];

const upcomingSchedules = [
  { id: 1, name: "Daily PostgreSQL", nextRun: "Today, 23:00", frequency: "Daily" },
  { id: 2, name: "Weekly Full Backup", nextRun: "Sunday, 02:00", frequency: "Weekly" },
  { id: 3, name: "Hourly Redis Snapshot", nextRun: "In 45 minutes", frequency: "Hourly" },
];

const storageBackends = [
  { name: "Local FS", used: 450, total: 1000, color: "bg-chart-1" },
  { name: "S3", used: 856, total: 2000, color: "bg-chart-2" },
  { name: "Backblaze", used: 1890, total: 2000, color: "bg-chart-3" },
  { name: "FTP", used: 234, total: 500, color: "bg-chart-4" },
];

interface GaugeDisplayProps {
  value: number;
  max: number;
  label: string;
  color: string;
}

function GaugeDisplay({ value, max, label, color }: GaugeDisplayProps) {
  const percentage = Math.round((value / max) * 100);
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset = circumference - (percentage / 100) * circumference * 0.75;
  
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-[135deg]" viewBox="0 0 100 100">
          {/* Background arc */}
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            strokeLinecap="round"
            className="text-muted"
            strokeDasharray={`${circumference * 0.75} ${circumference}`}
          />
          {/* Foreground arc */}
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            strokeLinecap="round"
            className={color}
            strokeDasharray={`${circumference * 0.75} ${circumference}`}
            strokeDashoffset={strokeDashoffset}
            style={{ transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold">{percentage}%</span>
        </div>
      </div>
      <span className="text-sm text-muted-foreground mt-2">{label}</span>
    </div>
  );
}

export default function Dashboard() {
  const totalStorage = storageBackends.reduce((acc, s) => acc + s.total, 0);
  const usedStorage = storageBackends.reduce((acc, s) => acc + s.used, 0);
  
  return (
    <div>
      <PageHeader 
        title="Dashboard" 
        description="Overview of your Docker volume backup system"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <DataCard
          title="Total Backup Jobs"
          value={24}
          subtitle="8 active, 16 scheduled"
          icon={Database}
        />
        <DataCard
          title="Storage Used"
          value="3.4 TB"
          subtitle="Across 4 backends"
          icon={HardDrive}
          trend={{ value: 12, isPositive: true }}
        />
        <DataCard
          title="Success Rate"
          value="98.5%"
          subtitle="Last 30 days"
          icon={CheckCircle}
          trend={{ value: 2.3, isPositive: true }}
        />
        <DataCard
          title="Active Alerts"
          value={2}
          subtitle="1 critical, 1 warning"
          icon={AlertTriangle}
        />
      </div>

      {/* Gauges Section */}
      <Card className="glass-panel border-border mb-6">
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Gauge className="h-5 w-5 text-primary" />
            Storage Backend Usage
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {storageBackends.map((backend) => (
              <GaugeDisplay
                key={backend.name}
                value={backend.used}
                max={backend.total}
                label={backend.name}
                color={backend.color.replace('bg-', 'text-')}
              />
            ))}
          </div>
          <div className="mt-6 pt-4 border-t border-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-muted-foreground">Total Storage</span>
              <span className="text-sm font-medium">
                {(usedStorage / 1000).toFixed(1)} TB / {(totalStorage / 1000).toFixed(1)} TB
              </span>
            </div>
            <Progress value={(usedStorage / totalStorage) * 100} className="h-2" />
          </div>
        </CardContent>
      </Card>

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
              {recentJobs.map((job) => (
                <div key={job.id} className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-4">
                    <div className="h-9 w-9 rounded-lg bg-secondary flex items-center justify-center">
                      <Database className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{job.name}</p>
                      <p className="text-xs text-muted-foreground font-mono">{job.volume}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-muted-foreground font-mono">{job.size}</span>
                    <StatusBadge status={job.status} />
                    <span className="text-xs text-muted-foreground w-20 text-right">{job.time}</span>
                  </div>
                </div>
              ))}
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
              {upcomingSchedules.map((schedule) => (
                <div key={schedule.id} className="p-4 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <p className="font-medium text-sm">{schedule.name}</p>
                    <span className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground">
                      {schedule.frequency}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{schedule.nextRun}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
