import { useState } from "react";
import { Plus, Cloud, Server, Edit, Trash2, MoreVertical, RefreshCw, FolderOpen, Database } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import { fetchStorages, createStorage, updateStorage, deleteStorage, testStorage, fetchRcloneRemotes } from "@/api";
import type { StorageBackend, StorageBackendConfig } from "@/api/types";

const typeIcons: Record<string, typeof FolderOpen> = {
  localfs: FolderOpen,
  s3: Cloud,
  ftp: Server,
  rclone: Database,
};
const typeLabels: Record<string, string> = { localfs: "Local FS", s3: "S3", ftp: "FTP/SFTP", rclone: "Rclone" };

function primaryPath(s: StorageBackend): string {
  const c = s.config || {};
  if (s.type === "localfs") return (c.path as string) || "/backups";
  if (s.type === "s3") return (c.bucket as string) || "";
  if (s.type === "ftp") return `${c.host || ""}:${c.port || 21}`;
  if (s.type === "rclone") return (c.remote_name as string) || "";
  return "";
}

const defaultConfig = (type: string): StorageBackendConfig => {
  switch (type) {
    case "localfs": return { path: "/backups" };
    case "s3": return { bucket: "", region: "us-east-1", access_key_id: "", secret_access_key: "" };
    case "ftp": return { host: "", port: 21, username: "", password: "", use_tls: false, use_sftp: false };
    case "rclone": return { remote_name: "", flags: "" };
    default: return {};
  }
};

export default function Storages() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editing, setEditing] = useState<StorageBackend | null>(null);
  const [form, setForm] = useState({ name: "", type: "localfs", config: defaultConfig("localfs") });

  const { data: storages = [], isLoading } = useQuery({ queryKey: ["storages"], queryFn: fetchStorages });
  const { data: rcloneData } = useQuery({
    queryKey: ["rclone-remotes"],
    queryFn: fetchRcloneRemotes,
    enabled: form.type === "rclone",
  });
  const rcloneRemotes = rcloneData?.remotes ?? [];
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["storages"] });

  const createMut = useMutation({
    mutationFn: () => createStorage({ name: form.name, type: form.type, config: form.config }),
    onSuccess: () => { toast.success(`Storage "${form.name}" created`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const updateMut = useMutation({
    mutationFn: (id: number) => updateStorage(id, { name: form.name, type: form.type, config: form.config }),
    onSuccess: () => { toast.success("Storage updated"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const deleteMut = useMutation({
    mutationFn: deleteStorage,
    onSuccess: () => { toast.success("Storage deleted"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const testMut = useMutation({
    mutationFn: testStorage,
    onSuccess: (r) => toast[r.success ? "success" : "error"](r.message),
    onError: (err: Error) => toast.error(err.message),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", type: "localfs", config: defaultConfig("localfs") });
    setDialogOpen(true);
  };
  const openEdit = (s: StorageBackend) => {
    setEditing(s);
    setForm({ name: s.name, type: s.type, config: { ...s.config } });
    setDialogOpen(true);
  };
  const handleSave = () => {
    if (!form.name) return;
    if (editing) updateMut.mutate(editing.id);
    else createMut.mutate();
    setDialogOpen(false);
  };

  const setConfigField = (key: string, value: unknown) =>
    setForm((p) => ({ ...p, config: { ...p.config, [key]: value } }));

  return (
    <div>
      <PageHeader
        title="Backend Storages"
        description="Configure storage backends: Local FS, S3, FTP, or Rclone"
        action={
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setEditing(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2" onClick={openCreate}><Plus className="h-4 w-4" />Add Storage</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editing ? "Edit Storage" : "Add Storage"}</DialogTitle>
                <DialogDescription>Configure a storage backend for your backups.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input className="bg-background border-border" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
                </div>
                <div className="space-y-2">
                  <Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm((p) => ({ ...p, type: v, config: defaultConfig(v) }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="localfs">Local Filesystem</SelectItem>
                      <SelectItem value="s3">S3-compatible</SelectItem>
                      <SelectItem value="ftp">FTP / SFTP</SelectItem>
                      <SelectItem value="rclone">Rclone Remote</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {form.type === "localfs" && (
                  <div className="space-y-2">
                    <Label>Path</Label>
                    <Input className="bg-background border-border font-mono text-sm" value={(form.config.path as string) || ""} onChange={(e) => setConfigField("path", e.target.value)} />
                  </div>
                )}
                {form.type === "s3" && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2"><Label>Bucket</Label><Input className="bg-background border-border" value={(form.config.bucket as string) || ""} onChange={(e) => setConfigField("bucket", e.target.value)} /></div>
                      <div className="space-y-2"><Label>Region</Label><Input className="bg-background border-border" value={(form.config.region as string) || ""} onChange={(e) => setConfigField("region", e.target.value)} /></div>
                    </div>
                    <div className="space-y-2"><Label>Access Key ID</Label><Input className="bg-background border-border font-mono text-sm" value={(form.config.access_key_id as string) || ""} onChange={(e) => setConfigField("access_key_id", e.target.value)} /></div>
                    <div className="space-y-2"><Label>Secret Access Key</Label><Input type="password" className="bg-background border-border font-mono text-sm" value={(form.config.secret_access_key as string) || ""} onChange={(e) => setConfigField("secret_access_key", e.target.value)} /></div>
                    <div className="space-y-2"><Label>Endpoint URL (optional)</Label><Input className="bg-background border-border font-mono text-sm" placeholder="https://s3.amazonaws.com" value={(form.config.endpoint_url as string) || ""} onChange={(e) => setConfigField("endpoint_url", e.target.value)} /></div>
                  </>
                )}
                {form.type === "ftp" && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2"><Label>Host</Label><Input className="bg-background border-border" value={(form.config.host as string) || ""} onChange={(e) => setConfigField("host", e.target.value)} /></div>
                      <div className="space-y-2"><Label>Port</Label><Input type="number" className="bg-background border-border" value={String(form.config.port || 21)} onChange={(e) => setConfigField("port", Number(e.target.value))} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2"><Label>Username</Label><Input className="bg-background border-border" value={(form.config.username as string) || ""} onChange={(e) => setConfigField("username", e.target.value)} /></div>
                      <div className="space-y-2"><Label>Password</Label><Input type="password" className="bg-background border-border" value={(form.config.password as string) || ""} onChange={(e) => setConfigField("password", e.target.value)} /></div>
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="flex items-center gap-2"><Switch checked={!!form.config.use_sftp} onCheckedChange={(v) => setConfigField("use_sftp", v)} /><Label>Use SFTP</Label></div>
                      <div className="flex items-center gap-2"><Switch checked={!!form.config.use_tls} onCheckedChange={(v) => setConfigField("use_tls", v)} /><Label>Use TLS</Label></div>
                    </div>
                  </>
                )}
                {form.type === "rclone" && (
                  <>
                    <div className="space-y-2">
                      <Label>Remote Name</Label>
                      {rcloneRemotes.length > 0 ? (
                        <Select
                          value={(form.config.remote_name as string) || ""}
                          onValueChange={(v) => setConfigField("remote_name", v)}
                        >
                          <SelectTrigger className="bg-background border-border font-mono text-sm">
                            <SelectValue placeholder="Select a remote" />
                          </SelectTrigger>
                          <SelectContent className="bg-popover border-border">
                            {rcloneRemotes.map((r) => (
                              <SelectItem key={r} value={r}>{r}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input className="bg-background border-border font-mono text-sm" placeholder="myremote" value={(form.config.remote_name as string) || ""} onChange={(e) => setConfigField("remote_name", e.target.value)} />
                      )}
                      {rcloneRemotes.length === 0 && rcloneData && (
                        <p className="text-xs text-muted-foreground">No remotes found. Paste your rclone config in Settings and save first.</p>
                      )}
                    </div>
                    <div className="space-y-2"><Label>Remote Path</Label><Input className="bg-background border-border font-mono text-sm" placeholder="/backups" value={(form.config.path as string) || ""} onChange={(e) => setConfigField("path", e.target.value)} /></div>
                    <div className="space-y-2"><Label>Extra Flags</Label><Input className="bg-background border-border font-mono text-sm" placeholder="--transfers=4" value={(form.config.flags as string) || ""} onChange={(e) => setConfigField("flags", e.target.value)} /></div>
                  </>
                )}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleSave}>{editing ? "Save Changes" : "Add Storage"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {isLoading ? (
        <div className="text-center text-muted-foreground py-12">Loading storages...</div>
      ) : storages.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">No storage backends configured yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {storages.map((storage) => {
            const Icon = typeIcons[storage.type] || FolderOpen;
            return (
              <Card key={storage.id} className="glass-panel border-border animate-fade-in hover:border-primary/30 transition-colors">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Icon className="h-6 w-6 text-primary" />
                      </div>
                      <div>
                        <CardTitle className="text-base">{storage.name}</CardTitle>
                        <p className="text-sm text-muted-foreground">{typeLabels[storage.type] || storage.type}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground font-mono">
                        {typeLabels[storage.type] || storage.type}
                      </span>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="bg-popover border-border">
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => testMut.mutate(storage.id)}>
                            <RefreshCw className="h-4 w-4" /> Test Connection
                          </DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => openEdit(storage)}>
                            <Edit className="h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator className="bg-border" />
                          <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive" onClick={() => setDeleteId(storage.id)}>
                            <Trash2 className="h-4 w-4" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="text-sm">
                    <span className="text-muted-foreground">Path/Bucket: </span>
                    <span className="font-mono text-xs">{primaryPath(storage)}</span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Created {new Date(storage.created_at).toLocaleDateString()}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Storage Backend</AlertDialogTitle>
            <AlertDialogDescription>This will remove this storage backend. Existing backups on this storage will NOT be deleted.</AlertDialogDescription>
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
