import { useState, useMemo, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Play, Pause, PlayCircle, Trash2, Edit, Database, ArrowUp, ArrowDown, ArrowUpDown, X } from "lucide-react";
import { toast } from "sonner";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";
import { fetchJobs, createJob, updateJob, deleteJob, runJob, pauseJob, resumeJob, fetchStorages, fetchSchedules, fetchRotations, fetchSettings } from "@/api";
import type { BackupJob } from "@/api/types";

type SortKey = "name" | "label" | "containers" | "storage" | "schedule" | "status" | "last_run";
type SortDir = "asc" | "desc";

export default function BackupJobs() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Single-job dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editingJob, setEditingJob] = useState<BackupJob | null>(null);
  const [formData, setFormData] = useState({ name: "", label_key: "", label_value: "", storage_id: "", schedule_id: "", retention_id: "" });
  const [submitted, setSubmitted] = useState(false);

  // Sort state
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [bulkForm, setBulkForm] = useState({
    changeStorage: false, storage_id: "",
    changeSchedule: false, schedule_id: "",
    changeRetention: false, retention_id: "",
    changeLabel: false, label_key: "", label_value: "",
  });

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
  });
  const { data: storages = [] } = useQuery({ queryKey: ["storages"], queryFn: fetchStorages });
  const { data: schedules = [] } = useQuery({ queryKey: ["schedules"], queryFn: fetchSchedules });
  const { data: rotations = [] } = useQuery({ queryKey: ["rotations"], queryFn: fetchRotations });
  const { data: settingsData } = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const defaultLabelKey = (settingsData?.settings as Record<string, unknown> | undefined)?.default_label_key as string || "dvbm.job";

  // Handle ?edit=<id> from JobDetail page
  useEffect(() => {
    const editId = searchParams.get("edit");
    if (editId && jobs.length > 0) {
      const job = jobs.find((j) => j.id === Number(editId));
      if (job) openEdit(job);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, jobs]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
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
        case "name":       av = a.name.toLowerCase(); bv = b.name.toLowerCase(); break;
        case "label":      av = a.label.toLowerCase(); bv = b.label.toLowerCase(); break;
        case "containers": av = a.containers.join(", ").toLowerCase(); bv = b.containers.join(", ").toLowerCase(); break;
        case "storage":    av = (a.storage?.name || "").toLowerCase(); bv = (b.storage?.name || "").toLowerCase(); break;
        case "schedule":   av = (a.schedule?.name || "zzz").toLowerCase(); bv = (b.schedule?.name || "zzz").toLowerCase(); break;
        case "status":     av = a.status; bv = b.status; break;
        case "last_run":   av = a.last_run || ""; bv = b.last_run || ""; break;
        default:           av = ""; bv = "";
      }
      return av < bv ? -m : av > bv ? m : 0;
    });
  }, [jobs, sortKey, sortDir]);

  // Selection helpers
  const allSelected = sortedJobs.length > 0 && sortedJobs.every((j) => selectedIds.has(j.id));
  const someSelected = sortedJobs.some((j) => selectedIds.has(j.id));
  const selectionCount = selectedIds.size;
  const selectedJobs = jobs.filter((j) => selectedIds.has(j.id));

  const toggleSelectAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(sortedJobs.map((j) => j.id)));
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearSelection = () => setSelectedIds(new Set());

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  // Single-job mutations
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

  // Bulk action handlers
  const handleBulkRun = () => {
    const ids = Array.from(selectedIds);
    Promise.all(ids.map((id) => runJob(id)))
      .then(() => { toast.success(`Triggered ${ids.length} job(s)`); invalidate(); clearSelection(); })
      .catch((err: Error) => toast.error(err.message));
  };

  const handleBulkEnable = () => {
    const ids = Array.from(selectedIds);
    Promise.all(ids.map((id) => resumeJob(id)))
      .then(() => { toast.success(`Enabled ${ids.length} job(s)`); invalidate(); clearSelection(); })
      .catch((err: Error) => toast.error(err.message));
  };

  const handleBulkDisable = () => {
    const ids = Array.from(selectedIds);
    Promise.all(ids.map((id) => pauseJob(id)))
      .then(() => { toast.success(`Disabled ${ids.length} job(s)`); invalidate(); clearSelection(); })
      .catch((err: Error) => toast.error(err.message));
  };

  const handleBulkDelete = () => {
    const ids = Array.from(selectedIds);
    Promise.all(ids.map((id) => deleteJob(id)))
      .then(() => { toast.success(`Deleted ${ids.length} job(s)`); invalidate(); clearSelection(); setBulkDeleteOpen(false); })
      .catch((err: Error) => toast.error(err.message));
  };

  const openBulkEdit = () => {
    setBulkForm({
      changeStorage: false, storage_id: "",
      changeSchedule: false, schedule_id: "",
      changeRetention: false, retention_id: "",
      changeLabel: false, label_key: defaultLabelKey, label_value: "",
    });
    setBulkEditOpen(true);
  };

  const handleBulkSave = () => {
    const patch: Record<string, unknown> = {};
    if (bulkForm.changeStorage && bulkForm.storage_id) {
      patch.storage_id = Number(bulkForm.storage_id);
    }
    if (bulkForm.changeSchedule) {
      patch.schedule_id = bulkForm.schedule_id ? Number(bulkForm.schedule_id) : null;
    }
    if (bulkForm.changeRetention) {
      patch.retention_id = bulkForm.retention_id ? Number(bulkForm.retention_id) : null;
    }
    if (bulkForm.changeLabel) {
      patch.label_key = bulkForm.label_key || defaultLabelKey;
      patch.label_value = bulkForm.label_value || "";
    }
    if (Object.keys(patch).length === 0) {
      setBulkEditOpen(false);
      return;
    }
    const ids = Array.from(selectedIds);
    Promise.all(ids.map((id) => updateJob(id, patch)))
      .then(() => { toast.success(`Updated ${ids.length} job(s)`); invalidate(); clearSelection(); setBulkEditOpen(false); })
      .catch((err: Error) => toast.error(err.message));
  };

  // Single-job form helpers
  const openCreate = () => {
    setEditingJob(null);
    setSubmitted(false);
    setFormData({ name: "", label_key: defaultLabelKey, label_value: "", storage_id: "", schedule_id: "", retention_id: "" });
    setDialogOpen(true);
  };

  const openEdit = (job: BackupJob) => {
    setEditingJob(job);
    setSubmitted(false);
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
    setSubmitted(true);
    const nameTaken = jobs.some((j) => j.name.toLowerCase() === formData.name.trim().toLowerCase() && j.id !== editingJob?.id);
    if (!formData.name.trim() || !formData.storage_id || nameTaken) return;
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
  const missingName = submitted && !formData.name.trim();
  const missingStorage = submitted && !formData.storage_id;
  const bulkEditHasChanges = bulkForm.changeStorage || bulkForm.changeSchedule || bulkForm.changeRetention || bulkForm.changeLabel;

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
                  <Label htmlFor="job-name">Job Name <span className="text-destructive">*</span></Label>
                  <Input
                    id="job-name"
                    placeholder="e.g. postgres-nightly"
                    className={`bg-background border-border ${(missingName || isDuplicateName) ? "border-destructive focus-visible:ring-destructive" : ""}`}
                    value={formData.name}
                    onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                  />
                  {missingName && <p className="text-xs text-destructive">Job name is required</p>}
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
                  <Label>Storage Backend <span className="text-destructive">*</span></Label>
                  <Select value={formData.storage_id} onValueChange={(v) => setFormData((p) => ({ ...p, storage_id: v }))}>
                    <SelectTrigger className={`bg-background border-border ${missingStorage ? "border-destructive focus-visible:ring-destructive" : ""}`}>
                      <SelectValue placeholder="Select storage" />
                    </SelectTrigger>
                    <SelectContent portal={false} className="bg-popover border-border">
                      {storages.length === 0
                        ? <SelectItem value="__none__" disabled>No storage backends configured</SelectItem>
                        : storages.map((s) => <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.type})</SelectItem>)
                      }
                    </SelectContent>
                  </Select>
                  {missingStorage && <p className="text-xs text-destructive">A storage backend is required</p>}
                  {storages.length === 0 && !missingStorage && (
                    <p className="text-xs text-muted-foreground">No storage backends yet — add one in the <a href="/storages" className="underline text-foreground">Storages</a> page first</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label>Schedule</Label>
                  <Select value={formData.schedule_id || "__manual__"} onValueChange={(v) => setFormData((p) => ({ ...p, schedule_id: v === "__manual__" ? "" : v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Manual (no schedule)" /></SelectTrigger>
                    <SelectContent portal={false} className="bg-popover border-border">
                      <SelectItem value="__manual__">Manual (no schedule)</SelectItem>
                      {schedules.map((s) => <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.cron})</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Retention Policy</Label>
                  <Select value={formData.retention_id || "__none__"} onValueChange={(v) => setFormData((p) => ({ ...p, retention_id: v === "__none__" ? "" : v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="None (keep all)" /></SelectTrigger>
                    <SelectContent portal={false} className="bg-popover border-border">
                      <SelectItem value="__none__">None (keep all)</SelectItem>
                      {rotations.map((r) => <SelectItem key={r.id} value={r.id.toString()}>{r.name} ({r.retention_days}d)</SelectItem>)}
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

      {/* Bulk action toolbar */}
      {selectionCount > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-2.5 animate-fade-in">
          <span className="text-sm font-medium text-foreground mr-1">{selectionCount} selected</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={clearSelection}>
            <X className="h-3.5 w-3.5" />
          </Button>
          <div className="mx-2 h-4 w-px bg-border" />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 h-8" onClick={handleBulkRun}>
                  <Play className="h-3.5 w-3.5" />Run
                </Button>
              </TooltipTrigger>
              <TooltipContent>Run all selected jobs now</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 h-8" onClick={handleBulkEnable}>
                  <PlayCircle className="h-3.5 w-3.5" />Enable
                </Button>
              </TooltipTrigger>
              <TooltipContent>Enable all selected jobs</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 h-8" onClick={handleBulkDisable}>
                  <Pause className="h-3.5 w-3.5" />Disable
                </Button>
              </TooltipTrigger>
              <TooltipContent>Disable all selected jobs</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 h-8" onClick={openBulkEdit}>
                  <Edit className="h-3.5 w-3.5" />Edit
                </Button>
              </TooltipTrigger>
              <TooltipContent>Edit selected jobs</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 h-8 text-destructive hover:text-destructive border-destructive/40 hover:border-destructive" onClick={() => setBulkDeleteOpen(true)}>
                  <Trash2 className="h-3.5 w-3.5" />Delete
                </Button>
              </TooltipTrigger>
              <TooltipContent>Delete all selected jobs</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      )}

      <TooltipProvider>
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
                  <TableHead className="w-10 pl-4" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={toggleSelectAll}
                      aria-label="Select all"
                    />
                  </TableHead>
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
                  <TableRow
                    key={job.id}
                    className={`border-border hover:bg-muted/30 cursor-pointer ${selectedIds.has(job.id) ? "bg-muted/20" : ""}`}
                    onClick={() => navigate(`/jobs/${job.id}`)}
                  >
                    <TableCell className="pl-4" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.has(job.id)}
                        onCheckedChange={() => toggleSelect(job.id)}
                        aria-label={`Select ${job.name}`}
                      />
                    </TableCell>
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
                      <div className="flex items-center justify-end gap-1.5">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => runMutation.mutate(job.id)} disabled={runMutation.isPending}>
                              <Play className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Run Now</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => job.enabled ? pauseMutation.mutate(job.id) : resumeMutation.mutate(job.id)}>
                              {job.enabled ? <Pause className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>{job.enabled ? "Pause Job" : "Resume Job"}</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(job)}>
                              <Edit className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Edit Job</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => setDeleteId(job.id)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete Job</TooltipContent>
                        </Tooltip>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      </TooltipProvider>

      {/* Single-job delete confirm */}
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

      {/* Bulk delete confirm */}
      <AlertDialog open={bulkDeleteOpen} onOpenChange={setBulkDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectionCount} Job{selectionCount !== 1 ? "s" : ""}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div>
                <p className="mb-2">The following jobs will be permanently deleted:</p>
                <ul className="list-disc list-inside space-y-0.5 text-sm text-foreground">
                  {selectedJobs.map((j) => <li key={j.id}>{j.name}</li>)}
                </ul>
                <p className="mt-2">This action cannot be undone.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete {selectionCount} Job{selectionCount !== 1 ? "s" : ""}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk edit dialog */}
      <Dialog open={bulkEditOpen} onOpenChange={setBulkEditOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit {selectionCount} Job{selectionCount !== 1 ? "s" : ""}</DialogTitle>
            <DialogDescription>
              Check a field to change it for all selected jobs. Job names cannot be changed in bulk.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-5 py-2">
            {/* Storage */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="bulk-change-storage"
                  checked={bulkForm.changeStorage}
                  onCheckedChange={(v) => setBulkForm((p) => ({ ...p, changeStorage: !!v, storage_id: "" }))}
                />
                <Label htmlFor="bulk-change-storage" className="cursor-pointer">Change storage backend</Label>
              </div>
              {bulkForm.changeStorage && (
                <Select value={bulkForm.storage_id} onValueChange={(v) => setBulkForm((p) => ({ ...p, storage_id: v }))}>
                  <SelectTrigger className="bg-background border-border ml-6">
                    <SelectValue placeholder="Select storage" />
                  </SelectTrigger>
                  <SelectContent portal={false} className="bg-popover border-border">
                    {storages.map((s) => <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.type})</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Schedule */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="bulk-change-schedule"
                  checked={bulkForm.changeSchedule}
                  onCheckedChange={(v) => setBulkForm((p) => ({ ...p, changeSchedule: !!v, schedule_id: "" }))}
                />
                <Label htmlFor="bulk-change-schedule" className="cursor-pointer">Change schedule</Label>
              </div>
              {bulkForm.changeSchedule && (
                <Select value={bulkForm.schedule_id || "__manual__"} onValueChange={(v) => setBulkForm((p) => ({ ...p, schedule_id: v === "__manual__" ? "" : v }))}>
                  <SelectTrigger className="bg-background border-border ml-6">
                    <SelectValue placeholder="Manual (no schedule)" />
                  </SelectTrigger>
                  <SelectContent portal={false} className="bg-popover border-border">
                    <SelectItem value="__manual__">Manual (no schedule)</SelectItem>
                    {schedules.map((s) => <SelectItem key={s.id} value={s.id.toString()}>{s.name} ({s.cron})</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Retention */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="bulk-change-retention"
                  checked={bulkForm.changeRetention}
                  onCheckedChange={(v) => setBulkForm((p) => ({ ...p, changeRetention: !!v, retention_id: "" }))}
                />
                <Label htmlFor="bulk-change-retention" className="cursor-pointer">Change retention policy</Label>
              </div>
              {bulkForm.changeRetention && (
                <Select value={bulkForm.retention_id || "__none__"} onValueChange={(v) => setBulkForm((p) => ({ ...p, retention_id: v === "__none__" ? "" : v }))}>
                  <SelectTrigger className="bg-background border-border ml-6">
                    <SelectValue placeholder="None (keep all)" />
                  </SelectTrigger>
                  <SelectContent portal={false} className="bg-popover border-border">
                    <SelectItem value="__none__">None (keep all)</SelectItem>
                    {rotations.map((r) => <SelectItem key={r.id} value={r.id.toString()}>{r.name} ({r.retention_days}d)</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Label */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="bulk-change-label"
                  checked={bulkForm.changeLabel}
                  onCheckedChange={(v) => setBulkForm((p) => ({ ...p, changeLabel: !!v, label_key: defaultLabelKey, label_value: "" }))}
                />
                <Label htmlFor="bulk-change-label" className="cursor-pointer">Change Docker label</Label>
              </div>
              {bulkForm.changeLabel && (
                <div className="ml-6 flex items-center gap-1">
                  <Input
                    className="bg-background border-border font-mono flex-1"
                    placeholder={defaultLabelKey}
                    value={bulkForm.label_key}
                    onChange={(e) => setBulkForm((p) => ({ ...p, label_key: e.target.value }))}
                  />
                  <span className="text-muted-foreground font-mono text-lg px-1">=</span>
                  <Input
                    className="bg-background border-border font-mono flex-1"
                    placeholder="value (leave blank to use job name)"
                    value={bulkForm.label_value}
                    onChange={(e) => setBulkForm((p) => ({ ...p, label_value: e.target.value }))}
                  />
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkEditOpen(false)}>Cancel</Button>
            <Button onClick={handleBulkSave} disabled={!bulkEditHasChanges}>
              Apply to {selectionCount} Job{selectionCount !== 1 ? "s" : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
