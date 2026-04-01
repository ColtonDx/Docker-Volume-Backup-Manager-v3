import { useState } from "react";
import { Download, Filter, Search, RefreshCw, AlertTriangle, CheckCircle, Info, XCircle } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { fetchLogs } from "@/api";
import type { LogEntry } from "@/api/types";

type LogLevel = "info" | "success" | "warning" | "error";

const levelConfig: Record<LogLevel, { icon: typeof Info; color: string; bg: string }> = {
  info: { icon: Info, color: "text-primary", bg: "bg-primary/10" },
  success: { icon: CheckCircle, color: "text-success", bg: "bg-success/10" },
  warning: { icon: AlertTriangle, color: "text-warning", bg: "bg-warning/10" },
  error: { icon: XCircle, color: "text-destructive", bg: "bg-destructive/10" },
};

export default function Logs() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ["logs", filter, search],
    queryFn: () => fetchLogs({ level: filter !== "all" ? filter : undefined, search: search || undefined, limit: 200 }),
  });

  return (
    <div>
      <PageHeader
        title="Logs"
        description="View backup job logs and system events"
        action={
          <Button variant="outline" className="gap-2 border-border" onClick={() => {
            const text = logs.map((l) => `[${l.created_at}] [${l.level.toUpperCase()}] ${l.job_name || "system"}: ${l.message}`).join("\n");
            const blob = new Blob([text], { type: "text/plain" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "dvbm-logs.txt";
            a.click();
          }}>
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
              <Button variant="outline" size="icon" className="border-border" onClick={() => queryClient.invalidateQueries({ queryKey: ["logs"] })}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="text-center text-muted-foreground py-12">Loading logs...</div>
          ) : logs.length === 0 ? (
            <div className="text-center text-muted-foreground py-12">No log entries found.</div>
          ) : (
            <div className="divide-y divide-border font-mono text-sm">
              {logs.map((log) => {
                const config = levelConfig[log.level] || levelConfig.info;
                const Icon = config.icon;
                return (
                  <div key={log.id} className="p-4 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start gap-4">
                      <div className={cn("h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0", config.bg)}>
                        <Icon className={cn("h-4 w-4", config.color)} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-muted-foreground text-xs">{new Date(log.created_at).toLocaleString()}</span>
                          <span className={cn("px-2 py-0.5 rounded text-xs font-medium uppercase", config.bg, config.color)}>
                            {log.level}
                          </span>
                          {log.job_name && (
                            <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded">
                              {log.job_name}
                            </span>
                          )}
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
