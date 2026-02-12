import { useState, useMemo } from "react";
import { RotateCcw, Search, RefreshCw, CheckCircle, Clock, Database, CalendarIcon, X } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { fetchBackups, restoreBackup, fetchJobs } from "@/api";
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
  const [search, setSearch] = useState("");
  const [jobFilter, setJobFilter] = useState("all");
  const [volumeFilter, setVolumeFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [restoreId, setRestoreId] = useState<number | null>(null);

  // Only fetch restorable backups (success + warning)
  const { data: successBackups = [], isLoading: loadingSuccess, refetch: refetchSuccess } = useQuery({
    queryKey: ["backups", "success"],
    queryFn: () => fetchBackups({ status: "success", limit: 500 }),
  });
  const { data: warningBackups = [], isLoading: loadingWarning, refetch: refetchWarning } = useQuery({
    queryKey: ["backups", "warning"],
    queryFn: () => fetchBackups({ status: "warning", limit: 500 }),
  });
  const isLoading = loadingSuccess || loadingWarning;
  const backups = useMemo(() =>
    [...successBackups, ...warningBackups].sort((a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    ), [successBackups, warningBackups]);

  const refetch = () => { refetchSuccess(); refetchWarning(); };

  // Get jobs list for the filter dropdown
  const { data: jobs = [] } = useQuery({ queryKey: ["jobs"], queryFn: fetchJobs });

  // Derive unique job names and volume names from the backup data
  const jobNames = useMemo(() => [...new Set(backups.map((b) => b.job_name))].sort(), [backups]);
  const allVolumes = useMemo(() => {
    const set = new Set<string>();
    backups.forEach((b) => b.volumes_backed_up.forEach((v) => set.add(v)));
    return [...set].sort();
  }, [backups]);

  const restoreMutation = useMutation({
    mutationFn: restoreBackup,
    onSuccess: (_, id) => {
      toast.success(`Restore initiated from backup #${id}`);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const filtered = useMemo(() => backups.filter((b) => {
    // Text search
    if (search) {
      const s = search.toLowerCase();
      if (!b.job_name.toLowerCase().includes(s) && !b.storage_path?.toLowerCase().includes(s)) {
        return false;
      }
    }
    // Job filter
    if (jobFilter !== "all" && b.job_name !== jobFilter) return false;
    // Volume filter
    if (volumeFilter && !b.volumes_backed_up.some((v) => v.toLowerCase().includes(volumeFilter.toLowerCase()))) return false;
    // Date from
    if (dateFrom) {
      const from = new Date(dateFrom);
      if (new Date(b.started_at) < from) return false;
    }
    // Date to
    if (dateTo) {
      const to = new Date(dateTo);
      to.setHours(23, 59, 59, 999);
      if (new Date(b.started_at) > to) return false;
    }
    return true;
  }), [backups, search, jobFilter, volumeFilter, dateFrom, dateTo]);

  const hasActiveFilters = search || jobFilter !== "all" || volumeFilter || dateFrom || dateTo;
  const clearFilters = () => { setSearch(""); setJobFilter("all"); setVolumeFilter(""); setDateFrom(""); setDateTo(""); };

  return (
    <div>
      <PageHeader
        title="Restore"
        description="Browse restorable backups and restore volumes from previous backups"
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
                <p className="text-sm text-muted-foreground">Restorable Backups</p>
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
                <p className="text-2xl font-semibold">{jobNames.length}</p>
                <p className="text-sm text-muted-foreground">Jobs With Backups</p>
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
          <div className="space-y-4">
            {/* Row 1: Search + refresh */}
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
                {hasActiveFilters && (
                  <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={clearFilters}>
                    <X className="h-3.5 w-3.5" /> Clear
                  </Button>
                )}
                <Button variant="outline" size="icon" className="border-border" onClick={() => refetch()}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {/* Row 2: Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="space-y-1 flex-1">
                <Label className="text-xs text-muted-foreground">Job</Label>
                <Select value={jobFilter} onValueChange={setJobFilter}>
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue placeholder="All Jobs" />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="all">All Jobs</SelectItem>
                    {jobNames.map((name) => (
                      <SelectItem key={name} value={name}>{name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1 flex-1">
                <Label className="text-xs text-muted-foreground">Volume</Label>
                <Select value={volumeFilter || "__all__"} onValueChange={(v) => setVolumeFilter(v === "__all__" ? "" : v)}>
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue placeholder="All Volumes" />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="__all__">All Volumes</SelectItem>
                    {allVolumes.map((vol) => (
                      <SelectItem key={vol} value={vol}>{vol}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">From</Label>
                <Input type="date" className="bg-background border-border w-[160px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">To</Label>
                <Input type="date" className="bg-background border-border w-[160px]" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading backups...</div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              {backups.length === 0 ? "No restorable backups found. Run a backup job first." : "No backups match the current filters."}
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
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5 border-border"
                        disabled={restoreMutation.isPending}
                        onClick={() => setRestoreId(backup.id)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Restore
                      </Button>
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
