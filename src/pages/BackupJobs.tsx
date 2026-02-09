import { Plus, MoreVertical, Play, Pause, Trash2, Edit, Database } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const backupJobs = [
  { 
    id: 1, 
    name: "postgres-data", 
    label: "Backup=postgres-data",
    containers: "postgres-main, postgres-replica",
    storage: "S3", 
    schedule: "Daily @ 23:00",
    rotation: "Keep 7 days",
    status: "active" as const,
    lastRun: "2 hours ago",
    nextRun: "In 22 hours"
  },
  { 
    id: 2, 
    name: "redis-cache", 
    label: "Backup=redis-cache",
    containers: "redis-primary",
    storage: "Local FS", 
    schedule: "Hourly",
    rotation: "Keep 24 hours",
    status: "running" as const,
    lastRun: "Running now",
    nextRun: "-"
  },
  { 
    id: 3, 
    name: "mysql-production", 
    label: "Backup=mysql-production",
    containers: "mysql-db, mysql-sidecar",
    storage: "S3", 
    schedule: "Every 6 hours",
    rotation: "Keep 14 days",
    status: "error" as const,
    lastRun: "3 hours ago (failed)",
    nextRun: "In 3 hours"
  },
  { 
    id: 4, 
    name: "grafana-data", 
    label: "Backup=grafana-data",
    containers: "grafana",
    storage: "Backblaze", 
    schedule: "Daily @ 02:00",
    rotation: "Keep 30 days",
    status: "active" as const,
    lastRun: "6 hours ago",
    nextRun: "In 18 hours"
  },
  { 
    id: 5, 
    name: "nginx-configs", 
    label: "Backup=nginx-configs",
    containers: "nginx-proxy, nginx-web",
    storage: "FTP", 
    schedule: "Weekly",
    rotation: "Keep 12 weeks",
    status: "idle" as const,
    lastRun: "3 days ago",
    nextRun: "In 4 days"
  },
];

export default function BackupJobs() {
  return (
    <div>
      <PageHeader 
        title="Backup Jobs" 
        description="Containers with matching Docker labels are stopped during backup, then restarted"
        action={
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            New Backup Job
          </Button>
        }
      />

      <Card className="glass-panel border-border animate-fade-in">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">Job Name</TableHead>
                <TableHead className="text-muted-foreground">Docker Label</TableHead>
                <TableHead className="text-muted-foreground">Matched Containers</TableHead>
                <TableHead className="text-muted-foreground">Storage</TableHead>
                <TableHead className="text-muted-foreground">Schedule</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-muted-foreground">Last Run</TableHead>
                <TableHead className="text-muted-foreground text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {backupJobs.map((job) => (
                <TableRow key={job.id} className="border-border hover:bg-muted/30">
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center">
                        <Database className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <span className="font-medium">{job.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">{job.label}</TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-48 truncate">{job.containers}</TableCell>
                  <TableCell>{job.storage}</TableCell>
                  <TableCell className="text-sm">{job.schedule}</TableCell>
                  <TableCell><StatusBadge status={job.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">{job.lastRun}</TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-popover border-border">
                        <DropdownMenuItem className="gap-2 cursor-pointer">
                          <Play className="h-4 w-4" /> Run Now
                        </DropdownMenuItem>
                        <DropdownMenuItem className="gap-2 cursor-pointer">
                          <Pause className="h-4 w-4" /> Pause Job
                        </DropdownMenuItem>
                        <DropdownMenuItem className="gap-2 cursor-pointer">
                          <Edit className="h-4 w-4" /> Edit
                        </DropdownMenuItem>
                        <DropdownMenuSeparator className="bg-border" />
                        <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive">
                          <Trash2 className="h-4 w-4" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
