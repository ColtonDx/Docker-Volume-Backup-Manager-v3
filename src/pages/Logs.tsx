import { useState } from "react";
import { FileText, Download, Filter, Search, RefreshCw, AlertTriangle, CheckCircle, Info, XCircle } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type LogLevel = "info" | "success" | "warning" | "error";

interface LogEntry {
  id: number;
  timestamp: string;
  level: LogLevel;
  job: string;
  message: string;
  details?: string;
}

const logs: LogEntry[] = [
  {
    id: 1,
    timestamp: "2024-02-08 14:32:15",
    level: "success",
    job: "postgres-data",
    message: "Backup completed successfully",
    details: "Size: 2.4 GB | Duration: 4m 23s | Storage: AWS S3",
  },
  {
    id: 2,
    timestamp: "2024-02-08 14:28:00",
    level: "info",
    job: "redis-backup",
    message: "Backup job started",
    details: "Volume: redis_data | Target: Local NFS",
  },
  {
    id: 3,
    timestamp: "2024-02-08 14:15:42",
    level: "warning",
    job: "mysql-production",
    message: "Backup completed with warnings",
    details: "Some tables were locked during backup. Duration: 12m 45s",
  },
  {
    id: 4,
    timestamp: "2024-02-08 11:00:00",
    level: "error",
    job: "mysql-production",
    message: "Backup failed - Connection timeout",
    details: "Error: Unable to connect to MySQL server. Connection timed out after 30s.",
  },
  {
    id: 5,
    timestamp: "2024-02-08 10:45:00",
    level: "info",
    job: "System",
    message: "Rotation policy 'Standard Daily' executed",
    details: "Removed 12 old backups | Reclaimed: 8.2 GB",
  },
  {
    id: 6,
    timestamp: "2024-02-08 08:00:00",
    level: "success",
    job: "grafana-data",
    message: "Backup completed successfully",
    details: "Size: 890 MB | Duration: 1m 12s | Storage: AWS S3",
  },
  {
    id: 7,
    timestamp: "2024-02-08 02:00:15",
    level: "success",
    job: "Weekly Full Backup",
    message: "8 backup jobs completed",
    details: "Total size: 12.4 GB | Duration: 45m 23s",
  },
  {
    id: 8,
    timestamp: "2024-02-07 23:00:00",
    level: "info",
    job: "nginx-configs",
    message: "Backup job started",
    details: "Volume: nginx_config | Target: Backblaze B2",
  },
];

const levelConfig: Record<LogLevel, { icon: typeof Info; color: string; bg: string }> = {
  info: { icon: Info, color: "text-primary", bg: "bg-primary/10" },
  success: { icon: CheckCircle, color: "text-success", bg: "bg-success/10" },
  warning: { icon: AlertTriangle, color: "text-warning", bg: "bg-warning/10" },
  error: { icon: XCircle, color: "text-destructive", bg: "bg-destructive/10" },
};

export default function Logs() {
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const filteredLogs = logs.filter((log) => {
    if (filter !== "all" && log.level !== filter) return false;
    if (search && !log.message.toLowerCase().includes(search.toLowerCase()) && 
        !log.job.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <PageHeader 
        title="Logs" 
        description="View backup job logs and system events"
        action={
          <Button variant="outline" className="gap-2 border-border">
            <Download className="h-4 w-4" />
            Export Logs
          </Button>
        }
      />

      <Card className="glass-panel border-border animate-fade-in">
        <CardHeader className="border-b border-border">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search logs..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-background border-border"
              />
            </div>
            <div className="flex gap-2">
              <Select value={filter} onValueChange={setFilter}>
                <SelectTrigger className="w-[140px] bg-background border-border">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" className="border-border">
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border font-mono text-sm">
            {filteredLogs.map((log) => {
              const config = levelConfig[log.level];
              const Icon = config.icon;
              
              return (
                <div key={log.id} className="p-4 hover:bg-muted/30 transition-colors">
                  <div className="flex items-start gap-4">
                    <div className={cn("h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0", config.bg)}>
                      <Icon className={cn("h-4 w-4", config.color)} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1">
                        <span className="text-muted-foreground text-xs">{log.timestamp}</span>
                        <span className={cn("px-2 py-0.5 rounded text-xs font-medium uppercase", config.bg, config.color)}>
                          {log.level}
                        </span>
                        <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded">
                          {log.job}
                        </span>
                      </div>
                      <p className="text-foreground">{log.message}</p>
                      {log.details && (
                        <p className="text-xs text-muted-foreground mt-1">{log.details}</p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
