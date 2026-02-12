import { useState } from "react";
import { Plus, RotateCcw, Clock, Archive, Edit, Trash2, MoreVertical } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { fetchRotations, createRotation, updateRotation, deleteRotation, runCleanup } from "@/api";
import type { RetentionPolicy } from "@/api/types";

export default function Rotations() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editing, setEditing] = useState<RetentionPolicy | null>(null);
  const [form, setForm] = useState({ name: "", description: "", retention_days: 7, min_backups: 1, max_backups: 0 });

  const { data: policies = [], isLoading } = useQuery({ queryKey: ["rotations"], queryFn: fetchRotations });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["rotations"] });

  const createMut = useMutation({
    mutationFn: () => createRotation({ name: form.name, description: form.description || undefined, retention_days: form.retention_days, min_backups: form.min_backups, max_backups: form.max_backups || undefined }),
    onSuccess: () => { toast.success(`Policy "${form.name}" created`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const updateMut = useMutation({
    mutationFn: (id: number) => updateRotation(id, { name: form.name, description: form.description || undefined, retention_days: form.retention_days, min_backups: form.min_backups, max_backups: form.max_backups || undefined }),
    onSuccess: () => { toast.success("Policy updated"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const deleteMut = useMutation({
    mutationFn: deleteRotation,
    onSuccess: () => { toast.success("Policy deleted"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const cleanupMut = useMutation({
    mutationFn: runCleanup,
    onSuccess: (r) => toast.success(r.message),
    onError: (err: Error) => toast.error(err.message),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", description: "", retention_days: 7, min_backups: 1, max_backups: 0 });
    setDialogOpen(true);
  };
  const openEdit = (p: RetentionPolicy) => {
    setEditing(p);
    setForm({ name: p.name, description: p.description || "", retention_days: p.retention_days, min_backups: p.min_backups, max_backups: p.max_backups || 0 });
    setDialogOpen(true);
  };
  const handleSave = () => {
    if (!form.name || form.retention_days < 1) return;
    if (editing) updateMut.mutate(editing.id);
    else createMut.mutate();
    setDialogOpen(false);
    setEditing(null);
  };

  return (
    <div>
      <PageHeader
        title="Retention Policies"
        description="Configure backup rotation and retention rules"
        action={
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setEditing(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2" onClick={openCreate}><Plus className="h-4 w-4" />New Policy</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{editing ? "Edit Policy" : "Create Retention Policy"}</DialogTitle>
                <DialogDescription>Define how long backups are kept and rotation limits.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2"><Label>Name</Label><Input className="bg-background border-border" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} /></div>
                <div className="space-y-2"><Label>Description</Label><Input className="bg-background border-border" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} /></div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2"><Label>Retention (days)</Label><Input type="number" min={1} className="bg-background border-border" value={form.retention_days} onChange={(e) => setForm((p) => ({ ...p, retention_days: Number(e.target.value) }))} /></div>
                  <div className="space-y-2"><Label>Min Backups</Label><Input type="number" min={0} className="bg-background border-border" value={form.min_backups} onChange={(e) => setForm((p) => ({ ...p, min_backups: Number(e.target.value) }))} /></div>
                  <div className="space-y-2"><Label>Max Backups</Label><Input type="number" min={0} className="bg-background border-border" placeholder="0 = unlimited" value={form.max_backups || ""} onChange={(e) => setForm((p) => ({ ...p, max_backups: Number(e.target.value) }))} /></div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleSave}>{editing ? "Save Changes" : "Create Policy"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center"><Archive className="h-6 w-6 text-primary" /></div>
              <div>
                <p className="text-2xl font-semibold">{policies.length}</p>
                <p className="text-sm text-muted-foreground">Total Policies</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-success/10 flex items-center justify-center"><RotateCcw className="h-6 w-6 text-success" /></div>
              <div>
                <p className="text-2xl font-semibold">{policies.reduce((s, p) => s + p.job_count, 0)}</p>
                <p className="text-sm text-muted-foreground">Connected Jobs</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-warning/10 flex items-center justify-center"><Clock className="h-6 w-6 text-warning" /></div>
              <div>
                <p className="text-2xl font-semibold">{policies.filter((p) => p.max_backups).length}</p>
                <p className="text-sm text-muted-foreground">With Max Cap</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {isLoading ? (
        <div className="text-center text-muted-foreground py-12">Loading policies...</div>
      ) : policies.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">No retention policies yet.</div>
      ) : (
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">Policy Name</TableHead>
                  <TableHead className="text-muted-foreground">Retention</TableHead>
                  <TableHead className="text-muted-foreground">Min / Max Backups</TableHead>
                  <TableHead className="text-muted-foreground">Jobs</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {policies.map((policy) => (
                  <TableRow key={policy.id} className="border-border hover:bg-muted/30">
                    <TableCell>
                      <div>
                        <p className="font-medium">{policy.name}</p>
                        <p className="text-xs text-muted-foreground">{policy.description || "—"}</p>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{policy.retention_days} days</TableCell>
                    <TableCell className="text-sm">{policy.min_backups} / {policy.max_backups || "∞"}</TableCell>
                    <TableCell>{policy.job_count}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="bg-popover border-border">
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => cleanupMut.mutate(policy.id)}>
                            <RotateCcw className="h-4 w-4" /> Run Cleanup
                          </DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => openEdit(policy)}>
                            <Edit className="h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator className="bg-border" />
                          <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive" onClick={() => setDeleteId(policy.id)}>
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
      )}

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Retention Policy</AlertDialogTitle>
            <AlertDialogDescription>Jobs using this policy will no longer have automatic rotation.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => { if (deleteId) { deleteMut.mutate(deleteId); setDeleteId(null); } }} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
