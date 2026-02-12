import { useState } from "react";
import { RotateCcw, Download, Search, Filter, RefreshCw, CheckCircle, Clock, AlertTriangle, Database } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { fetchBackups, restoreBackup, deleteBackup } from "@/api";
import type { BackupRecord } from "@/api/types";

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds)}s`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString();
}

export default function Restore() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [restoreId, setRestoreId] = useState<number | null>(null);

  const { data: backups = [], isLoading, refetch } = useQuery({
    queryKey: ["backups", statusFilter],
    queryFn: () => fetchBackups({
      status: statusFilter !== "all" ? statusFilter : undefined,
      limit: 200,
    }),
  });

  const restoreMutation = useMutation({
    mutationFn: restoreBackup,
    onSuccess: (_, id) => {
      toast.success(`Restore initiated from backup #${id}`);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const filtered = backups.filter((b) => {
    if (search) {
      const s = search.toLowerCase();
      if (!b.job_name.toLowerCase().includes(s) && !b.storage_path?.toLowerCase().includes(s)) {
        return false;
      }
    }
    return true;
  });

  const successCount = backups.filter((b) => b.status === "success").length;

  return (
    <div>
      <PageHeader
        title="Restore"
        description="Browse backup history and restore volumes from previous backups"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                <Database className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-semibold">{backups.length}</p>
                <p className="text-sm text-muted-foreground">Total Backups</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-success/10 flex items-center justify-center">
                <CheckCircle className="h-6 w-6 text-success" />
              </div>
              <div>
                <p className="text-2xl font-semibold">{successCount}</p>
                <p className="text-sm text-muted-foreground">Restorable Backups</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-warning/10 flex items-center justify-center">
                <Clock className="h-6 w-6 text-warning" />
              </div>
              <div>
                <p className="text-2xl font-semibold">
                  {backups.length > 0 ? formatDate(backups[0]?.started_at) : "—"}
                </p>
                <p className="text-sm text-muted-foreground">Latest Backup</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="glass-panel border-border animate-fade-in">
        <CardHeader className="border-b border-border">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by job name or path..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-background border-border"
              />
            </div>
            <div className="flex gap-2">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[140px] bg-background border-border">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" className="border-border" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading backups...</div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No backups found. Run a backup job first.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">ID</TableHead>
                  <TableHead className="text-muted-foreground">Job</TableHead>
                  <TableHead className="text-muted-foreground">Status</TableHead>
                  <TableHead className="text-muted-foreground">Size</TableHead>
                  <TableHead className="text-muted-foreground">Duration</TableHead>
                  <TableHead className="text-muted-foreground">Volumes</TableHead>
                  <TableHead className="text-muted-foreground">Date</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((backup) => (
                  <TableRow key={backup.id} className="border-border hover:bg-muted/30">
                    <TableCell className="font-mono text-sm">#{backup.id}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center">
                          <Database className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <span className="font-medium">{backup.job_name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={backup.status} />
                    </TableCell>
                    <TableCell className="font-mono text-sm">{formatSize(backup.size_bytes)}</TableCell>
                    <TableCell className="text-sm">{formatDuration(backup.duration_seconds)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {backup.volumes_backed_up.length > 0
                        ? backup.volumes_backed_up.join(", ")
                        : "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(backup.started_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5 border-border"
                          disabled={backup.status !== "success" || restoreMutation.isPending}
                          onClick={() => setRestoreId(backup.id)}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Restore
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={restoreId !== null} onOpenChange={(open) => !open && setRestoreId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore Backup</AlertDialogTitle>
            <AlertDialogDescription>
              This will stop the matching containers, restore the volume data from this backup,
              and restart the containers. This action will overwrite current volume data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (restoreId) {
                  restoreMutation.mutate(restoreId);
                  setRestoreId(null);
                }
              }}
            >
              Restore
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
