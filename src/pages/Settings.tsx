import { useState, useEffect, useRef } from "react";
import { Save, Shield, Database, Clock, Server, CloudCog, Terminal, Palette, Check, Download, Upload } from "lucide-react";
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
import { useColorTheme, THEMES, type ThemeId } from "@/contexts/ColorThemeContext";

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

  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirmImport, setConfirmImport] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImportConfig = async (file: File) => {
    setImporting(true);
    try {
      const token = sessionStorage.getItem("dvbm_token");
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/settings/import", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Import failed" }));
        throw new Error(err.detail || "Import failed");
      }
      const result = await res.json();
      const counts = Object.entries(result.imported || {}).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ");
      toast.success(`Config imported: ${counts}`);
      queryClient.invalidateQueries();
    } catch (err: any) {
      toast.error(err.message || "Import failed");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };
  const handleExportConfig = async () => {
    setExporting(true);
    try {
      const token = sessionStorage.getItem("dvbm_token");
      const res = await fetch("/api/settings/export", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="(.+)"/);
      a.download = match ? match[1] : "backup_buddy_config.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Config exported");
    } catch (err: any) {
      toast.error(err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  };

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
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setColorTheme(t.id)}
                  className={`relative flex flex-col items-center gap-3 rounded-lg border-2 p-4 transition-all hover:border-primary/60 ${
                    colorTheme === t.id
                      ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                      : "border-border bg-card"
                  }`}
                >
                  {/* Mini preview: dark bg circle with accent dot */}
                  <div className={`h-12 w-12 rounded-full ${t.previewBg} flex items-center justify-center shadow-md`}>
                    <div className={`h-5 w-5 rounded-full ${t.swatch}`} />
                  </div>
                  <span className="text-sm font-medium text-center leading-tight">{t.label}</span>
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
                <Select value={(form.timezone as string) || "UTC"} onValueChange={(v) => set("timezone", v)}>
                  <SelectTrigger className="bg-background border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border max-h-64">
                    <SelectItem value="UTC">UTC</SelectItem>
                    <SelectItem value="US/Eastern">US / Eastern (ET)</SelectItem>
                    <SelectItem value="US/Central">US / Central (CT)</SelectItem>
                    <SelectItem value="US/Mountain">US / Mountain (MT)</SelectItem>
                    <SelectItem value="US/Pacific">US / Pacific (PT)</SelectItem>
                    <SelectItem value="US/Alaska">US / Alaska (AKT)</SelectItem>
                    <SelectItem value="US/Hawaii">US / Hawaii (HST)</SelectItem>
                    <SelectItem value="Canada/Atlantic">Canada / Atlantic (AT)</SelectItem>
                    <SelectItem value="Canada/Newfoundland">Canada / Newfoundland (NT)</SelectItem>
                    <SelectItem value="America/Mexico_City">America / Mexico City (CST)</SelectItem>
                    <SelectItem value="America/Sao_Paulo">America / São Paulo (BRT)</SelectItem>
                    <SelectItem value="America/Argentina/Buenos_Aires">America / Buenos Aires (ART)</SelectItem>
                    <SelectItem value="Europe/London">Europe / London (GMT/BST)</SelectItem>
                    <SelectItem value="Europe/Paris">Europe / Paris (CET)</SelectItem>
                    <SelectItem value="Europe/Berlin">Europe / Berlin (CET)</SelectItem>
                    <SelectItem value="Europe/Amsterdam">Europe / Amsterdam (CET)</SelectItem>
                    <SelectItem value="Europe/Madrid">Europe / Madrid (CET)</SelectItem>
                    <SelectItem value="Europe/Rome">Europe / Rome (CET)</SelectItem>
                    <SelectItem value="Europe/Zurich">Europe / Zurich (CET)</SelectItem>
                    <SelectItem value="Europe/Stockholm">Europe / Stockholm (CET)</SelectItem>
                    <SelectItem value="Europe/Helsinki">Europe / Helsinki (EET)</SelectItem>
                    <SelectItem value="Europe/Athens">Europe / Athens (EET)</SelectItem>
                    <SelectItem value="Europe/Bucharest">Europe / Bucharest (EET)</SelectItem>
                    <SelectItem value="Europe/Moscow">Europe / Moscow (MSK)</SelectItem>
                    <SelectItem value="Europe/Istanbul">Europe / Istanbul (TRT)</SelectItem>
                    <SelectItem value="Asia/Dubai">Asia / Dubai (GST)</SelectItem>
                    <SelectItem value="Asia/Kolkata">Asia / Kolkata (IST)</SelectItem>
                    <SelectItem value="Asia/Bangkok">Asia / Bangkok (ICT)</SelectItem>
                    <SelectItem value="Asia/Singapore">Asia / Singapore (SGT)</SelectItem>
                    <SelectItem value="Asia/Hong_Kong">Asia / Hong Kong (HKT)</SelectItem>
                    <SelectItem value="Asia/Shanghai">Asia / Shanghai (CST)</SelectItem>
                    <SelectItem value="Asia/Seoul">Asia / Seoul (KST)</SelectItem>
                    <SelectItem value="Asia/Tokyo">Asia / Tokyo (JST)</SelectItem>
                    <SelectItem value="Australia/Sydney">Australia / Sydney (AEST)</SelectItem>
                    <SelectItem value="Australia/Melbourne">Australia / Melbourne (AEST)</SelectItem>
                    <SelectItem value="Australia/Perth">Australia / Perth (AWST)</SelectItem>
                    <SelectItem value="Australia/Adelaide">Australia / Adelaide (ACST)</SelectItem>
                    <SelectItem value="Pacific/Auckland">Pacific / Auckland (NZST)</SelectItem>
                    <SelectItem value="Pacific/Fiji">Pacific / Fiji (FJT)</SelectItem>
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

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center"><Download className="h-5 w-5 text-primary" /></div>
              <div><CardTitle className="text-lg">Config Backup</CardTitle><CardDescription>Export all jobs, schedules, storages, notifications and settings as a .zip file</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div><Label>Download Configuration</Label><p className="text-sm text-muted-foreground">Includes backup jobs, schedules, retention policies, storage backends, notification channels, and all settings</p></div>
              <Button variant="outline" className="gap-2" onClick={handleExportConfig} disabled={exporting}>
                <Download className="h-4 w-4" />{exporting ? "Exporting..." : "Export .zip"}
              </Button>
            </div>
            <Separator className="bg-border" />
            <div className="flex items-center justify-between">
              <div><Label>Import Configuration</Label><p className="text-sm text-muted-foreground">Restore settings from a previously exported .zip file. Existing entries with the same IDs will be overwritten.</p></div>
              <input ref={fileInputRef} type="file" accept=".zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) setConfirmImport(f); }} />
              <Button variant="outline" className="gap-2" onClick={() => fileInputRef.current?.click()} disabled={importing}>
                <Upload className="h-4 w-4" />{importing ? "Importing..." : "Import .zip"}
              </Button>
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

      <AlertDialog open={!!confirmImport} onOpenChange={(open) => { if (!open) { setConfirmImport(null); if (fileInputRef.current) fileInputRef.current.value = ""; } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Import Configuration?</AlertDialogTitle>
            <AlertDialogDescription>This will merge the uploaded config into your current setup. Existing items with matching IDs will be overwritten. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => { if (confirmImport) handleImportConfig(confirmImport); setConfirmImport(null); }}>Import</AlertDialogAction>
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
