import { Plus, HardDrive, Cloud, Server, Edit, Trash2, MoreVertical, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const storages = [
  {
    id: 1,
    name: "AWS S3 Production",
    type: "s3",
    provider: "Amazon S3",
    icon: Cloud,
    bucket: "company-backups-prod",
    region: "us-east-1",
    used: 856,
    total: 1000,
    status: "active" as const,
    jobs: 12,
  },
  {
    id: 2,
    name: "Local NFS Storage",
    type: "nfs",
    provider: "NFS Mount",
    icon: Server,
    bucket: "/mnt/backup-storage",
    region: "On-premise",
    used: 2100,
    total: 5000,
    status: "active" as const,
    jobs: 4,
  },
  {
    id: 3,
    name: "Google Cloud Storage",
    type: "gcs",
    provider: "Google Cloud",
    icon: Cloud,
    bucket: "company-backups-gcp",
    region: "us-central1",
    used: 234,
    total: 500,
    status: "active" as const,
    jobs: 3,
  },
  {
    id: 4,
    name: "Backblaze B2",
    type: "b2",
    provider: "Backblaze B2",
    icon: HardDrive,
    bucket: "company-archives",
    region: "US West",
    used: 1890,
    total: 2000,
    status: "warning" as const,
    jobs: 5,
  },
];

function formatStorage(gb: number): string {
  if (gb >= 1000) {
    return `${(gb / 1000).toFixed(1)} TB`;
  }
  return `${gb} GB`;
}

export default function Storages() {
  return (
    <div>
      <PageHeader 
        title="Backend Storages" 
        description="Configure storage backends for your backups"
        action={
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Storage
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {storages.map((storage) => {
          const usagePercent = (storage.used / storage.total) * 100;
          const isHighUsage = usagePercent > 80;
          
          return (
            <Card key={storage.id} className="glass-panel border-border animate-fade-in hover:border-primary/30 transition-colors">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                      <storage.icon className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{storage.name}</CardTitle>
                      <p className="text-sm text-muted-foreground">{storage.provider}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={storage.status} />
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-popover border-border">
                        <DropdownMenuItem className="gap-2 cursor-pointer">
                          <RefreshCw className="h-4 w-4" /> Test Connection
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
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Bucket/Path</span>
                    <p className="font-mono text-xs truncate mt-0.5">{storage.bucket}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Region</span>
                    <p className="mt-0.5">{storage.region}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Storage Usage</span>
                    <span className={isHighUsage ? "text-warning" : ""}>
                      {formatStorage(storage.used)} / {formatStorage(storage.total)}
                    </span>
                  </div>
                  <Progress 
                    value={usagePercent} 
                    className="h-2"
                  />
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border text-sm">
                  <span className="text-muted-foreground">Connected Jobs</span>
                  <span className="font-medium">{storage.jobs}</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
