import { useState, useEffect } from "react";
import { Save, Shield, Database, Bell, Clock, Server, CloudCog, Terminal, Palette, Check } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { fetchSettings, updateSettings, resetSettings, clearLogs } from "@/api";
import { useColorTheme, type ColorTheme } from "@/contexts/ColorThemeContext";

export default function Settings() {
  const queryClient = useQueryClient();
  const { colorTheme, setColorTheme } = useColorTheme();
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const s = (data?.settings ?? {}) as Record<string, unknown>;

  const [form, setForm] = useState<Record<string, unknown>>({});

  // Sync fetched settings into form
  useEffect(() => {
    if (data?.settings) setForm({ ...data.settings });
  }, [data]);

  const set = (key: string, val: unknown) => setForm((p) => ({ ...p, [key]: val }));

  const saveMut = useMutation({
    mutationFn: () => updateSettings(form),
    onSuccess: () => { toast.success("Settings saved"); queryClient.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (err: Error) => toast.error(err.message),
  });
  const resetMut = useMutation({
    mutationFn: resetSettings,
    onSuccess: () => { toast.success("Settings reset to defaults"); queryClient.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (err: Error) => toast.error(err.message),
  });
  const clearMut = useMutation({
    mutationFn: () => clearLogs(),
    onSuccess: () => { toast.success("Logs cleared"); queryClient.invalidateQueries({ queryKey: ["logs"] }); },
    onError: (err: Error) => toast.error(err.message),
  });

  if (isLoading) return <div className="text-center text-muted-foreground py-12">Loading settings...</div>;

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Configure global system settings"
        action={
          <Button className="gap-2" onClick={() => saveMut.mutate()}>
            <Save className="h-4 w-4" />
            Save Changes
          </Button>
        }
      />

      <div className="space-y-6">
        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Palette className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Appearance</CardTitle><CardDescription>Choose a color theme for the interface</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {([
                { id: "cyan" as ColorTheme, label: "Cyan", swatch: "bg-[hsl(192,91%,36%)]" },
                { id: "purple" as ColorTheme, label: "Purple", swatch: "bg-[hsl(270,65%,50%)]" },
                { id: "red" as ColorTheme, label: "Red", swatch: "bg-[hsl(0,72%,51%)]" },
                { id: "green" as ColorTheme, label: "Green", swatch: "bg-[hsl(152,69%,36%)]" },
              ]).map((t) => (
                <button
                  key={t.id}
                  onClick={() => setColorTheme(t.id)}
                  className={`relative flex flex-col items-center gap-3 rounded-lg border-2 p-4 transition-all hover:border-primary/60 ${
                    colorTheme === t.id
                      ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                      : "border-border bg-card"
                  }`}
                >
                  <div className={`h-10 w-10 rounded-full ${t.swatch} shadow-md`} />
                  <span className="text-sm font-medium">{t.label}</span>
                  {colorTheme === t.id && (
                    <div className="absolute top-2 right-2 h-5 w-5 rounded-full bg-primary flex items-center justify-center">
                      <Check className="h-3 w-3 text-primary-foreground" />
                    </div>
                  )}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Server className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">General</CardTitle><CardDescription>Basic system configuration</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Instance Name</Label>
                <Input className="bg-background border-border" value={(form.instance_name as string) || ""} onChange={(e) => set("instance_name", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Default Timezone</Label>
                <Select value={(form.timezone as string) || "utc"} onValueChange={(v) => set("timezone", v)}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="utc">UTC</SelectItem>
                    <SelectItem value="est">Eastern Time (EST)</SelectItem>
                    <SelectItem value="pst">Pacific Time (PST)</SelectItem>
                    <SelectItem value="cet">Central European Time (CET)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Maintenance Mode</Label>
                <p className="text-sm text-muted-foreground">Pause all backup operations</p>
              </div>
              <Switch checked={!!form.maintenance_mode} onCheckedChange={(v) => set("maintenance_mode", v)} />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><CloudCog className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Rclone Configuration</CardTitle><CardDescription>Configure rclone for additional storage backends</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div><Label>Enable Rclone</Label><p className="text-sm text-muted-foreground">Use rclone for advanced storage operations</p></div>
              <Switch checked={!!form.rclone_enabled} onCheckedChange={(v) => set("rclone_enabled", v)} />
            </div>
            <Separator className="bg-border" />
            <div className="space-y-2">
              <Label>Rclone Binary Path</Label>
              <Input className="bg-background border-border font-mono text-sm" value={(form.rclone_binary as string) || "/usr/bin/rclone"} onChange={(e) => set("rclone_binary", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Rclone Config File</Label>
              <Input className="bg-background border-border font-mono text-sm" value={(form.rclone_config_path as string) || "/root/.config/rclone/rclone.conf"} onChange={(e) => set("rclone_config_path", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Additional Rclone Flags</Label>
              <Input className="bg-background border-border font-mono text-sm" placeholder="--transfers=4 --checkers=8" value={(form.rclone_flags as string) || ""} onChange={(e) => set("rclone_flags", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Rclone Config (Optional)</Label>
              <Textarea
                placeholder={`[remote-name]\ntype = s3\nprovider = AWS\naccess_key_id = xxx\nsecret_access_key = xxx`}
                className="bg-background border-border font-mono text-sm min-h-32"
                value={(form.rclone_config_inline as string) || ""}
                onChange={(e) => set("rclone_config_inline", e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Database className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Backup Defaults</CardTitle><CardDescription>Default settings for new backup jobs</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Default Compression</Label>
                <Select value={(form.compression as string) || "gzip"} onValueChange={(v) => set("compression", v)}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="gzip">Gzip</SelectItem>
                    <SelectItem value="lz4">LZ4 (Fast)</SelectItem>
                    <SelectItem value="zstd">Zstandard</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Default Encryption</Label>
                <Select value={(form.encryption as string) || "none"} onValueChange={(v) => set("encryption", v)}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="aes128">AES-128</SelectItem>
                    <SelectItem value="aes256">AES-256</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div><Label>Verify Backups</Label><p className="text-sm text-muted-foreground">Automatically verify backup integrity</p></div>
              <Switch checked={form.verify_backups !== false} onCheckedChange={(v) => set("verify_backups", v)} />
            </div>
            <div className="flex items-center justify-between">
              <div><Label>Parallel Uploads</Label><p className="text-sm text-muted-foreground">Enable multi-threaded uploads</p></div>
              <Switch checked={form.parallel_uploads !== false} onCheckedChange={(v) => set("parallel_uploads", v)} />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Bell className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Notification Defaults</CardTitle><CardDescription>Global notification preferences</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div><Label>Notify on Success</Label><p className="text-sm text-muted-foreground">Send notifications for successful backups</p></div>
              <Switch checked={!!form.notify_success} onCheckedChange={(v) => set("notify_success", v)} />
            </div>
            <div className="flex items-center justify-between">
              <div><Label>Notify on Warning</Label><p className="text-sm text-muted-foreground">Send notifications for backups with warnings</p></div>
              <Switch checked={form.notify_warning !== false} onCheckedChange={(v) => set("notify_warning", v)} />
            </div>
            <div className="flex items-center justify-between">
              <div><Label>Notify on Failure</Label><p className="text-sm text-muted-foreground">Send notifications for failed backups</p></div>
              <Switch checked={form.notify_failure !== false} onCheckedChange={(v) => set("notify_failure", v)} />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Clock className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Log Retention</CardTitle><CardDescription>Configure how long to keep logs</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Backup Logs</Label>
                <Select value={String(form.backup_log_days || 30)} onValueChange={(v) => set("backup_log_days", Number(v))}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="7">7 days</SelectItem>
                    <SelectItem value="14">14 days</SelectItem>
                    <SelectItem value="30">30 days</SelectItem>
                    <SelectItem value="90">90 days</SelectItem>
                    <SelectItem value="365">1 year</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>System Logs</Label>
                <Select value={String(form.system_log_days || 14)} onValueChange={(v) => set("system_log_days", Number(v))}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="7">7 days</SelectItem>
                    <SelectItem value="14">14 days</SelectItem>
                    <SelectItem value="30">30 days</SelectItem>
                    <SelectItem value="90">90 days</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border border-destructive/30 animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-destructive/10 flex items-center justify-center"><Shield className="h-5 w-5 text-destructive" /></div>
              <div><CardTitle className="text-lg text-destructive">Danger Zone</CardTitle><CardDescription>Irreversible actions</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div><Label>Reset All Settings</Label><p className="text-sm text-muted-foreground">Reset all settings to default values</p></div>
              <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground" onClick={() => setConfirmReset(true)}>Reset</Button>
            </div>
            <Separator className="bg-border" />
            <div className="flex items-center justify-between">
              <div><Label>Clear All Logs</Label><p className="text-sm text-muted-foreground">Permanently delete all log entries</p></div>
              <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground" onClick={() => setConfirmClear(true)}>Clear Logs</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset All Settings?</AlertDialogTitle>
            <AlertDialogDescription>All settings will revert to their default values. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => resetMut.mutate()} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Reset</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear All Logs?</AlertDialogTitle>
            <AlertDialogDescription>All log entries will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => clearMut.mutate()} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Clear</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
