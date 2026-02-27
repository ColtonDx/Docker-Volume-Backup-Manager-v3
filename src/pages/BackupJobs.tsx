import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MoreVertical, Play, Pause, Trash2, Edit, Database, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { toast } from "sonner";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { fetchJobs, createJob, updateJob, deleteJob, runJob, pauseJob, resumeJob, fetchStorages, fetchSchedules, fetchRotations, fetchSettings } from "@/api";
import type { BackupJob } from "@/api/types";

type SortKey = "name" | "label" | "containers" | "storage" | "schedule" | "status" | "last_run";
type SortDir = "asc" | "desc";

export default function BackupJobs() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editingJob, setEditingJob] = useState<BackupJob | null>(null);
  const [formData, setFormData] = useState({ name: "", label_key: "", label_value: "", storage_id: "", schedule_id: "", retention_id: "" });
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const { data: jobs = [], isLoading } = useQuery({ queryKey: ["jobs"], queryFn: fetchJobs });
  const { data: storages = [] } = useQuery({ queryKey: ["storages"], queryFn: fetchStorages });
  const { data: schedules = [] } = useQuery({ queryKey: ["schedules"], queryFn: fetchSchedules });
  const { data: rotations = [] } = useQuery({ queryKey: ["rotations"], queryFn: fetchRotations });
  const { data: settingsData } = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const defaultLabelKey = (settingsData?.settings as Record<string, unknown> | undefined)?.default_label_key as string || "backup-buddy.job";

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ArrowUpDown className="h-3 w-3 ml-1 inline opacity-40" />;
    return sortDir === "asc"
      ? <ArrowUp className="h-3 w-3 ml-1 inline" />
      : <ArrowDown className="h-3 w-3 ml-1 inline" />;
  };

  const sortedJobs = useMemo(() => {
    const m = sortDir === "asc" ? 1 : -1;
    return [...jobs].sort((a, b) => {
      let av: string, bv: string;
      switch (sortKey) {
        case "name":      av = a.name.toLowerCase(); bv = b.name.toLowerCase(); break;
        case "label":     av = a.label.toLowerCase(); bv = b.label.toLowerCase(); break;
        case "containers": av = a.containers.join(", ").toLowerCase(); bv = b.containers.join(", ").toLowerCase(); break;
        case "storage":   av = (a.storage?.name || "").toLowerCase(); bv = (b.storage?.name || "").toLowerCase(); break;
        case "schedule":  av = (a.schedule?.name || "zzz").toLowerCase(); bv = (b.schedule?.name || "zzz").toLowerCase(); break;
        case "status":    av = a.status; bv = b.status; break;
        case "last_run":  av = a.last_run || ""; bv = b.last_run || ""; break;
        default:          av = ""; bv = "";
      }
      return av < bv ? -m : av > bv ? m : 0;
    });
  }, [jobs, sortKey, sortDir]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) => createJob({
      name: data.name,
      label_key: data.label_key || defaultLabelKey,
      label_value: data.label_value || data.name,
      storage_id: Number(data.storage_id),
      schedule_id: data.schedule_id ? Number(data.schedule_id) : null,
      retention_id: data.retention_id ? Number(data.retention_id) : null,
    }),
    onSuccess: (_, data) => { toast.success(`Job "${data.name}" created`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof formData }) => updateJob(id, {
      name: data.name,
      label_key: data.label_key || defaultLabelKey,
      label_value: data.label_value || data.name,
      storage_id: Number(data.storage_id),
      schedule_id: data.schedule_id ? Number(data.schedule_id) : null,
      retention_id: data.retention_id ? Number(data.retention_id) : null,
    }),
    onSuccess: (_, { data }) => { toast.success(`Job "${data.name}" updated`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: () => { toast.success("Job deleted"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const runMutation = useMutation({
    mutationFn: runJob,
    onSuccess: (res) => { toast.success(res.message); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const pauseMutation = useMutation({
    mutationFn: pauseJob,
    onSuccess: (res) => { toast.success(res.message); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const resumeMutation = useMutation({
    mutationFn: resumeJob,
    onSuccess: (res) => { toast.success(res.message); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const openCreate = () => {
    setEditingJob(null);
    setFormData({ name: "", label_key: defaultLabelKey, label_value: "", storage_id: "", schedule_id: "", retention_id: "" });
    setDialogOpen(true);
  };

  const openEdit = (job: BackupJob) => {
    setEditingJob(job);
    setFormData({
      name: job.name,
      label_key: job.label_key || defaultLabelKey,
      label_value: job.label_value || "",
      storage_id: job.storage?.id?.toString() || "",
      schedule_id: job.schedule?.id?.toString() || "",
      retention_id: job.retention?.id?.toString() || "",
    });
    setDialogOpen(true);
  };

  const handleSave = () => {
    if (!formData.name || !formData.storage_id) return;
    // Prevent duplicate names (case-insensitive)
    const nameTaken = jobs.some((j) => j.name.toLowerCase() === formData.name.trim().toLowerCase() && j.id !== editingJob?.id);
    if (nameTaken) return;
    if (editingJob) {
      updateMutation.mutate({ id: editingJob.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
    setDialogOpen(false);
    setEditingJob(null);
  };

  const handleDelete = (id: number) => {
    deleteMutation.mutate(id);
    setDeleteId(null);
  };

  const isDuplicateName = formData.name.trim() !== "" && jobs.some((j) => j.name.toLowerCase() === formData.name.trim().toLowerCase() && j.id !== editingJob?.id);

  return (
    <div>
      <PageHeader
        title="Backup Jobs"
        description="Containers with matching Docker labels are stopped during backup, then restarted"
        action={
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setEditingJob(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2" onClick={openCreate}><Plus className="h-4 w-4" />New Backup Job</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{editingJob ? "Edit Backup Job" : "Create Backup Job"}</DialogTitle>
                <DialogDescription>Containers with the matching Docker label will be stopped during backup.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label htmlFor="job-name">Job Name</Label>
                  <Input id="job-name" placeholder="e.g. postgres-nightly" className={`bg-background border-border ${isDuplicateName ? "border-destructive focus-visible:ring-destructive" : ""}`} value={formData.name} onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))} />
                  {isDuplicateName && <p className="text-xs text-destructive">A job with this name already exists</p>}
                </div>
                <div className="space-y-2">
                  <Label>Docker Label</Label>
                  <div className="flex items-center gap-1">
                    <Input className="bg-background border-border font-mono flex-1" placeholder={defaultLabelKey} value={formData.label_key} onChange={(e) => setFormData((p) => ({ ...p, label_key: e.target.value }))} />
                    <span className="text-muted-foreground font-mono text-lg px-1">=</span>
                    <Input className="bg-background border-border font-mono flex-1" placeholder={formData.name || "value"} value={formData.label_value} onChange={(e) => setFormData((p) => ({ ...p, label_value: e.target.value }))} />
                  </div>
                  <p className="text-xs text-muted-foreground">Containers with label <code className="text-foreground">{formData.label_key || defaultLabelKey}={formData.label_value || formData.name || "value"}</code> will be matched. Leave value empty to use the job name.</p>
                </div>
                <div className="space-y-2">
                  <Label>Storage Backend</Label>
                  <Select value={formData.storage_id} onValueChange={(v) => setFormData((p) => ({ ...p, storage_id: v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Select storage" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      {storages.map((s) => (
                        <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.type})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Schedule</Label>
                  <Select value={formData.schedule_id || "__manual__"} onValueChange={(v) => setFormData((p) => ({ ...p, schedule_id: v === "__manual__" ? "" : v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Manual (no schedule)" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="__manual__">Manual (no schedule)</SelectItem>
                      {schedules.map((s) => (
                        <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.cron})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Retention Policy</Label>
                  <Select value={formData.retention_id || "__none__"} onValueChange={(v) => setFormData((p) => ({ ...p, retention_id: v === "__none__" ? "" : v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="None (keep all)" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="__none__">None (keep all)</SelectItem>
                      {rotations.map((r) => (
                        <SelectItem key={r.id} value={r.id.toString()}>{r.name} ({r.retention_days}d)</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleSave} disabled={isDuplicateName}>{editingJob ? "Save Changes" : "Create Job"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="glass-panel border-border animate-fade-in">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading jobs...</div>
          ) : jobs.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">No backup jobs yet. Create one to get started.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("name")}>Job Name <SortIcon col="name" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("label")}>Docker Label <SortIcon col="label" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("containers")}>Matched Containers <SortIcon col="containers" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("storage")}>Storage <SortIcon col="storage" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("schedule")}>Schedule <SortIcon col="schedule" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("status")}>Status <SortIcon col="status" /></TableHead>
                  <TableHead className="text-muted-foreground cursor-pointer select-none" onClick={() => toggleSort("last_run")}>Last Run <SortIcon col="last_run" /></TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedJobs.map((job) => (
                  <TableRow key={job.id} className="border-border hover:bg-muted/30 cursor-pointer" onClick={() => navigate(`/jobs/${job.id}`)}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center">
                          <Database className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <span className="font-medium">{job.name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">{job.label}</TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-48 truncate">
                      {job.containers.length > 0 ? job.containers.join(", ") : "—"}
                    </TableCell>
                    <TableCell>{job.storage?.name || "—"}</TableCell>
                    <TableCell className="text-sm">{job.schedule ? `${job.schedule.name} (${job.schedule.cron})` : "Manual"}</TableCell>
                    <TableCell><StatusBadge status={job.status} /></TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {job.last_run ? new Date(job.last_run).toLocaleString() : "Never"}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="bg-popover border-border">
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => runMutation.mutate(job.id)}>
                            <Play className="h-4 w-4" /> Run Now
                          </DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => job.enabled ? pauseMutation.mutate(job.id) : resumeMutation.mutate(job.id)}>
                            <Pause className="h-4 w-4" /> {job.enabled ? "Pause Job" : "Resume Job"}
                          </DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => openEdit(job)}>
                            <Edit className="h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator className="bg-border" />
                          <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive" onClick={() => setDeleteId(job.id)}>
                            <Trash2 className="h-4 w-4" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Backup Job</AlertDialogTitle>
            <AlertDialogDescription>This will permanently remove this backup job. This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteId && handleDelete(deleteId)} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
