import { useState } from "react";
import { Plus, Calendar, Clock, Edit, Trash2, MoreVertical } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
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
import { fetchSchedules, createSchedule, updateSchedule, deleteSchedule } from "@/api";
import type { Schedule } from "@/api/types";

export default function Schedules() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [form, setForm] = useState({ name: "", cron: "", description: "" });

  const { data: schedules = [], isLoading } = useQuery({ queryKey: ["schedules"], queryFn: fetchSchedules });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["schedules"] });

  const createMut = useMutation({
    mutationFn: () => createSchedule({ name: form.name, cron: form.cron, description: form.description || undefined }),
    onSuccess: () => { toast.success(`Schedule "${form.name}" created`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateMut = useMutation({
    mutationFn: (id: number) => updateSchedule(id, { name: form.name, cron: form.cron, description: form.description || undefined }),
    onSuccess: () => { toast.success(`Schedule updated`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteMut = useMutation({
    mutationFn: deleteSchedule,
    onSuccess: () => { toast.success("Schedule deleted"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", cron: "", description: "" });
    setDialogOpen(true);
  };

  const openEdit = (s: Schedule) => {
    setEditing(s);
    setForm({ name: s.name, cron: s.cron, description: s.description || "" });
    setDialogOpen(true);
  };

  const handleSave = () => {
    if (!form.name || !form.cron) return;
    if (editing) {
      updateMut.mutate(editing.id);
    } else {
      createMut.mutate();
    }
    setDialogOpen(false);
    setEditing(null);
  };

  return (
    <div>
      <PageHeader
        title="Schedules"
        description="Configure backup schedules using cron expressions"
        action={
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setEditing(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2" onClick={openCreate}><Plus className="h-4 w-4" />New Schedule</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{editing ? "Edit Schedule" : "Create Schedule"}</DialogTitle>
                <DialogDescription>Define a cron-based schedule for backup jobs.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label htmlFor="schedule-name">Schedule Name</Label>
                  <Input id="schedule-name" placeholder="e.g. Daily Backup" className="bg-background border-border" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cron">Cron Expression</Label>
                  <Input id="cron" placeholder="0 23 * * *" className="bg-background border-border font-mono" value={form.cron} onChange={(e) => setForm((p) => ({ ...p, cron: e.target.value }))} />
                  <p className="text-xs text-muted-foreground">Format: minute hour day month weekday</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Input id="description" placeholder="e.g. Every day at 11:00 PM" className="bg-background border-border" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleSave}>{editing ? "Save Changes" : "Create Schedule"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {isLoading ? (
        <div className="text-center text-muted-foreground py-12">Loading schedules...</div>
      ) : schedules.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">No schedules yet. Create one to get started.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {schedules.map((schedule) => (
            <Card key={schedule.id} className="glass-panel border-border animate-fade-in hover:border-primary/30 transition-colors">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Calendar className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{schedule.name}</CardTitle>
                      <code className="text-xs text-muted-foreground font-mono">{schedule.cron}</code>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="bg-popover border-border">
                      <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => openEdit(schedule)}>
                        <Edit className="h-4 w-4" /> Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator className="bg-border" />
                      <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive" onClick={() => setDeleteId(schedule.id)}>
                        <Trash2 className="h-4 w-4" /> Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{schedule.description || "—"}</p>
                <div className="flex items-center justify-between pt-2 border-t border-border">
                  <div className="flex items-center gap-4">
                    <div className="text-sm">
                      <span className="text-muted-foreground">Jobs: </span>
                      <span className="font-medium">{schedule.job_count}</span>
                    </div>
                    <StatusBadge status={schedule.enabled ? "active" : "idle"} />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
            <AlertDialogDescription>This will remove this schedule. Jobs using it will no longer run automatically.</AlertDialogDescription>
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
