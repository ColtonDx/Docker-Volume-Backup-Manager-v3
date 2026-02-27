import { useState } from "react";
import { Plus, Mail, MessageSquare, Webhook, Edit, Trash2, MoreVertical, TestTube, MessageCircle, Bell, BellRing } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
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
import { fetchNotifications, createNotification, updateNotification, deleteNotification, testNotification } from "@/api";
import type { NotificationChannel } from "@/api/types";

const typeIcons: Record<string, typeof Mail> = { email: Mail, slack: MessageSquare, discord: MessageCircle, gotify: Bell, ntfy: BellRing, webhook: Webhook };
const eventLabels: Record<string, { label: string; color: string }> = {
  failure: { label: "Failure", color: "bg-destructive/20 text-destructive" },
  warning: { label: "Warning", color: "bg-warning/20 text-warning" },
  success: { label: "Success", color: "bg-success/20 text-success" },
};
const allEvents = ["failure", "warning", "success"];

export default function Notifications() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [form, setForm] = useState({ name: "", type: "email", config: {} as Record<string, unknown>, events: ["failure"] as string[] });

  const { data: channels = [], isLoading } = useQuery({ queryKey: ["notifications"], queryFn: fetchNotifications });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const createMut = useMutation({
    mutationFn: () => createNotification({ name: form.name, type: form.type, config: form.config, events: form.events }),
    onSuccess: () => { toast.success(`Channel "${form.name}" created`); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const updateMut = useMutation({
    mutationFn: (id: number) => updateNotification(id, { name: form.name, type: form.type, config: form.config, events: form.events }),
    onSuccess: () => { toast.success("Channel updated"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const deleteMut = useMutation({
    mutationFn: deleteNotification,
    onSuccess: () => { toast.success("Channel deleted"); invalidate(); },
    onError: (err: Error) => toast.error(err.message),
  });
  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateNotification(id, { enabled }),
    onSuccess: () => invalidate(),
    onError: (err: Error) => toast.error(err.message),
  });
  const testMut = useMutation({
    mutationFn: testNotification,
    onSuccess: (r) => toast[r.success ? "success" : "error"](r.message),
    onError: (err: Error) => toast.error(err.message),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", type: "email", config: {}, events: ["failure"] });
    setDialogOpen(true);
  };
  const openEdit = (ch: NotificationChannel) => {
    setEditing(ch);
    setForm({ name: ch.name, type: ch.type, config: { ...ch.config }, events: [...ch.events] });
    setDialogOpen(true);
  };
  const handleSave = () => {
    if (!form.name) return;
    if (editing) updateMut.mutate(editing.id);
    else createMut.mutate();
    setDialogOpen(false);
    setEditing(null);
  };
  const toggleEvent = (ev: string) => {
    setForm((p) => ({ ...p, events: p.events.includes(ev) ? p.events.filter((e) => e !== ev) : [...p.events, ev] }));
  };
  const setConfigField = (key: string, value: unknown) => setForm((p) => ({ ...p, config: { ...p.config, [key]: value } }));

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Configure alerts for backup events"
        action={
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setEditing(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2" onClick={openCreate}><Plus className="h-4 w-4" />Add Notification</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{editing ? "Edit Channel" : "Add Notification Channel"}</DialogTitle>
                <DialogDescription>Configure where and when to receive alerts.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2"><Label>Name</Label><Input className="bg-background border-border" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} /></div>
                <div className="space-y-2">
                  <Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm((p) => ({ ...p, type: v, config: {} }))}>
                    <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-popover border-border">
                      <SelectItem value="email">Email</SelectItem>
                      <SelectItem value="slack">Slack</SelectItem>
                      <SelectItem value="discord">Discord</SelectItem>
                      <SelectItem value="gotify">Gotify</SelectItem>
                      <SelectItem value="ntfy">ntfy</SelectItem>
                      <SelectItem value="webhook">Webhook</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {form.type === "email" && (
                  <>
                    <div className="space-y-2"><Label>SMTP Host</Label><Input className="bg-background border-border" value={(form.config.smtp_host as string) || ""} onChange={(e) => setConfigField("smtp_host", e.target.value)} /></div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2"><Label>SMTP Port</Label><Input type="number" className="bg-background border-border" value={String(form.config.smtp_port || 587)} onChange={(e) => setConfigField("smtp_port", Number(e.target.value))} /></div>
                      <div className="space-y-2"><Label>From</Label><Input className="bg-background border-border" value={(form.config.from_email as string) || ""} onChange={(e) => setConfigField("from_email", e.target.value)} /></div>
                    </div>
                    <div className="space-y-2"><Label>To (comma separated)</Label><Input className="bg-background border-border" value={(form.config.to_emails as string) || ""} onChange={(e) => setConfigField("to_emails", e.target.value)} /></div>
                  </>
                )}
                {form.type === "slack" && (
                  <div className="space-y-2">
                    <Label>Webhook URL</Label>
                    <Input className="bg-background border-border font-mono text-sm" placeholder="https://hooks.slack.com/services/..." value={(form.config.webhook_url as string) || ""} onChange={(e) => setConfigField("webhook_url", e.target.value)} />
                  </div>
                )}
                {form.type === "discord" && (
                  <>
                    <div className="space-y-2">
                      <Label>Webhook URL</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="https://discord.com/api/webhooks/..." value={(form.config.webhook_url as string) || ""} onChange={(e) => setConfigField("webhook_url", e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>Bot Username (optional)</Label>
                      <Input className="bg-background border-border" placeholder="Backup Buddy" value={(form.config.username as string) || ""} onChange={(e) => setConfigField("username", e.target.value)} />
                    </div>
                  </>
                )}
                {form.type === "webhook" && (
                  <>
                    <div className="space-y-2"><Label>URL</Label><Input className="bg-background border-border font-mono text-sm" value={(form.config.url as string) || ""} onChange={(e) => setConfigField("url", e.target.value)} /></div>
                    <div className="space-y-2"><Label>Method</Label>
                      <Select value={(form.config.method as string) || "POST"} onValueChange={(v) => setConfigField("method", v)}>
                        <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                        <SelectContent className="bg-popover border-border">
                          <SelectItem value="POST">POST</SelectItem>
                          <SelectItem value="PUT">PUT</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </>
                )}
                {form.type === "gotify" && (
                  <>
                    <div className="space-y-2">
                      <Label>Server URL</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="https://gotify.example.com" value={(form.config.server_url as string) || ""} onChange={(e) => setConfigField("server_url", e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>Application Token</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="A..." value={(form.config.app_token as string) || ""} onChange={(e) => setConfigField("app_token", e.target.value)} />
                    </div>
                  </>
                )}
                {form.type === "ntfy" && (
                  <>
                    <div className="space-y-2">
                      <Label>Server URL</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="https://ntfy.sh" value={(form.config.server_url as string) || "https://ntfy.sh"} onChange={(e) => setConfigField("server_url", e.target.value)} />
                      <p className="text-xs text-muted-foreground">Default: https://ntfy.sh (public server)</p>
                    </div>
                    <div className="space-y-2">
                      <Label>Topic</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="backup-buddy-alerts" value={(form.config.topic as string) || ""} onChange={(e) => setConfigField("topic", e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>Access Token (optional)</Label>
                      <Input className="bg-background border-border font-mono text-sm" placeholder="tk_..." value={(form.config.access_token as string) || ""} onChange={(e) => setConfigField("access_token", e.target.value)} />
                      <p className="text-xs text-muted-foreground">Required if topic needs authentication</p>
                    </div>
                  </>
                )}
                <div className="space-y-2">
                  <Label>Events</Label>
                  <div className="flex items-center gap-4">
                    {allEvents.map((ev) => (
                      <label key={ev} className="flex items-center gap-2 text-sm">
                        <Checkbox checked={form.events.includes(ev)} onCheckedChange={() => toggleEvent(ev)} />
                        <span className="capitalize">{ev}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleSave}>{editing ? "Save Changes" : "Create Channel"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {isLoading ? (
        <div className="text-center text-muted-foreground py-12">Loading channels...</div>
      ) : channels.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">No notification channels configured.</div>
      ) : (
        <div className="space-y-4">
          {channels.map((ch) => {
            const Icon = typeIcons[ch.type] || Mail;
            return (
              <Card key={ch.id} className="glass-panel border-border animate-fade-in">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Icon className="h-6 w-6 text-primary" />
                      </div>
                      <div>
                        <h3 className="font-medium">{ch.name}</h3>
                        <p className="text-sm text-muted-foreground font-mono truncate max-w-xs">{ch.type}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="flex items-center gap-2">
                        {ch.events.map((event) => {
                          const ev = eventLabels[event];
                          return ev ? (
                            <span key={event} className={`px-2 py-0.5 rounded text-xs font-medium ${ev.color}`}>{ev.label}</span>
                          ) : null;
                        })}
                      </div>
                      <div className="text-sm text-muted-foreground w-28">
                        <span className="text-xs">Last: </span>
                        {ch.last_triggered_at ? new Date(ch.last_triggered_at).toLocaleDateString() : "Never"}
                      </div>
                      <div className="flex items-center gap-2">
                        <Switch checked={ch.enabled} onCheckedChange={(enabled) => toggleMut.mutate({ id: ch.id, enabled })} />
                        <span className="text-sm text-muted-foreground w-16">{ch.enabled ? "Enabled" : "Disabled"}</span>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8"><MoreVertical className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="bg-popover border-border">
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => testMut.mutate(ch.id)}>
                            <TestTube className="h-4 w-4" /> Send Test
                          </DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 cursor-pointer" onClick={() => openEdit(ch)}>
                            <Edit className="h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator className="bg-border" />
                          <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive" onClick={() => setDeleteId(ch.id)}>
                            <Trash2 className="h-4 w-4" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
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
            <AlertDialogTitle>Delete Notification Channel</AlertDialogTitle>
            <AlertDialogDescription>You will no longer receive alerts through this channel.</AlertDialogDescription>
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
