import { useState } from "react";
import { Plus, MoreVertical, Play, Pause, Trash2, Edit, Database } from "lucide-react";
import { toast } from "sonner";
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

type Job = {
  id: number; name: string; label: string; containers: string; storage: string;
  schedule: string; rotation: string; status: "active" | "running" | "error" | "idle"; lastRun: string; nextRun: string;
};

const initialJobs: Job[] = [
  { id: 1, name: "postgres-data", label: "Backup=postgres-data", containers: "postgres-main, postgres-replica", storage: "S3", schedule: "Daily @ 23:00", rotation: "Keep 7 days", status: "active", lastRun: "2 hours ago", nextRun: "In 22 hours" },
  { id: 2, name: "redis-cache", label: "Backup=redis-cache", containers: "redis-primary", storage: "Local FS", schedule: "Hourly", rotation: "Keep 24 hours", status: "running", lastRun: "Running now", nextRun: "-" },
  { id: 3, name: "mysql-production", label: "Backup=mysql-production", containers: "mysql-db, mysql-sidecar", storage: "S3", schedule: "Every 6 hours", rotation: "Keep 14 days", status: "error", lastRun: "3 hours ago (failed)", nextRun: "In 3 hours" },
  { id: 4, name: "grafana-data", label: "Backup=grafana-data", containers: "grafana", storage: "Backblaze", schedule: "Daily @ 02:00", rotation: "Keep 30 days", status: "active", lastRun: "6 hours ago", nextRun: "In 18 hours" },
  { id: 5, name: "nginx-configs", label: "Backup=nginx-configs", containers: "nginx-proxy, nginx-web", storage: "FTP", schedule: "Weekly", rotation: "Keep 12 weeks", status: "idle", lastRun: "3 days ago", nextRun: "In 4 days" },
];

const scheduleMap: Record<string, string> = { hourly: "Hourly", daily: "Daily", "6hours": "Every 6 hours", weekly: "Weekly" };
const rotationMap: Record<string, string> = { "24h": "Keep 24 hours", "7d": "Keep 7 days", "14d": "Keep 14 days", "30d": "Keep 30 days", "12w": "Keep 12 weeks" };
const storageMap: Record<string, string> = { localfs: "Local FS", s3: "S3", backblaze: "Backblaze", ftp: "FTP" };

export default function BackupJobs() {
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [newJob, setNewJob] = useState({ name: "", storage: "", schedule: "", rotation: "" });

  const handleCreate = () => {
    if (!newJob.name || !newJob.storage || !newJob.schedule || !newJob.rotation) return;
    setJobs((prev) => [...prev, {
      id: Date.now(), name: newJob.name, label: `Backup=${newJob.name}`, containers: "—",
      storage: storageMap[newJob.storage], schedule: scheduleMap[newJob.schedule],
      rotation: rotationMap[newJob.rotation], status: "idle", lastRun: "Never", nextRun: "Pending",
    }]);
    toast.success(`Job "${newJob.name}" created`);
    setNewJob({ name: "", storage: "", schedule: "", rotation: "" });
    setDialogOpen(false);
  };

  const handleDelete = (id: number) => {
    const job = jobs.find((j) => j.id === id);
    setJobs((prev) => prev.filter((j) => j.id !== id));
    setDeleteId(null);
    if (job) toast.success(`Job "${job.name}" deleted`);
  };

  return (
    <div>
      <PageHeader
        title="Backup Jobs"
        description="Containers with matching Docker labels are stopped during backup, then restarted"
        action={
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2"><Plus className="h-4 w-4" />New Backup Job</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Backup Job</DialogTitle>
                <DialogDescription>Containers with the matching Docker label will be stopped during backup.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label htmlFor="job-name">Job Name</Label>
                  <Input id="job-name" placeholder="e.g. postgres-data" className="bg-background border-border" value={newJob.name} onChange={(e) => setNewJob((p) => ({ ...p, name: e.target.value }))} />
                  <p className="text-xs text-muted-foreground">Containers with label <code className="text-foreground">Backup={newJob.name || "job-name"}</code> will be matched</p>
                </div>
                <div className="space-y-2">
                  <Label>Storage Backend</Label>
                  <Select value={newJob.storage} onValueChange={(v) => setNewJob((p) => ({ ...p, storage: v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Select storage" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="localfs">Local FS</SelectItem><SelectItem value="s3">S3</SelectItem>
                      <SelectItem value="backblaze">Backblaze</SelectItem><SelectItem value="ftp">FTP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Schedule</Label>
                  <Select value={newJob.schedule} onValueChange={(v) => setNewJob((p) => ({ ...p, schedule: v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Select schedule" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="hourly">Hourly</SelectItem><SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="6hours">Every 6 hours</SelectItem><SelectItem value="weekly">Weekly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Rotation Policy</Label>
                  <Select value={newJob.rotation} onValueChange={(v) => setNewJob((p) => ({ ...p, rotation: v }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue placeholder="Select rotation" /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="24h">Keep 24 hours</SelectItem><SelectItem value="7d">Keep 7 days</SelectItem>
                      <SelectItem value="14d">Keep 14 days</SelectItem><SelectItem value="30d">Keep 30 days</SelectItem>
                      <SelectItem value="12w">Keep 12 weeks</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleCreate}>Create Job</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
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
              {jobs.map((job) => (
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
                        <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-popover border-border">
                        <DropdownMenuItem className="gap-2 cursor-pointer"><Play className="h-4 w-4" /> Run Now</DropdownMenuItem>
                        <DropdownMenuItem className="gap-2 cursor-pointer"><Pause className="h-4 w-4" /> Pause Job</DropdownMenuItem>
                        <DropdownMenuItem className="gap-2 cursor-pointer"><Edit className="h-4 w-4" /> Edit</DropdownMenuItem>
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
