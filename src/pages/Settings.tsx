import { Save, Shield, Database, Bell, Clock, Server, CloudCog, Terminal } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function Settings() {
  return (
    <div>
      <PageHeader 
        title="Settings" 
        description="Configure global system settings"
        action={
          <Button className="gap-2">
            <Save className="h-4 w-4" />
            Save Changes
          </Button>
        }
      />

      <div className="space-y-6">
        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Server className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">General</CardTitle>
                <CardDescription>Basic system configuration</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Instance Name</Label>
                <Input defaultValue="Docker Volume Backup Manager" className="bg-background border-border" />
              </div>
              <div className="space-y-2">
                <Label>Default Timezone</Label>
                <Select defaultValue="utc">
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue />
                  </SelectTrigger>
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
              <Switch />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <CloudCog className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Rclone Configuration</CardTitle>
                <CardDescription>Configure rclone for additional storage backends</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label>Enable Rclone</Label>
                <p className="text-sm text-muted-foreground">Use rclone for advanced storage operations</p>
              </div>
              <Switch />
            </div>
            <Separator className="bg-border" />
            <div className="space-y-2">
              <Label>Rclone Binary Path</Label>
              <Input defaultValue="/usr/bin/rclone" className="bg-background border-border font-mono text-sm" />
              <p className="text-xs text-muted-foreground">Path to the rclone executable</p>
            </div>
            <div className="space-y-2">
              <Label>Rclone Config File</Label>
              <Input defaultValue="/root/.config/rclone/rclone.conf" className="bg-background border-border font-mono text-sm" />
              <p className="text-xs text-muted-foreground">Path to the rclone configuration file</p>
            </div>
            <div className="space-y-2">
              <Label>Additional Rclone Flags</Label>
              <Input placeholder="--transfers=4 --checkers=8" className="bg-background border-border font-mono text-sm" />
              <p className="text-xs text-muted-foreground">Extra flags to pass to rclone commands</p>
            </div>
            <div className="space-y-2">
              <Label>Rclone Config (Optional)</Label>
              <Textarea 
                placeholder={`[remote-name]\ntype = s3\nprovider = AWS\naccess_key_id = xxx\nsecret_access_key = xxx`}
                className="bg-background border-border font-mono text-sm min-h-32"
              />
              <p className="text-xs text-muted-foreground">Paste rclone configuration directly (will be merged with config file)</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="gap-2">
                <Terminal className="h-4 w-4" />
                Test Rclone
              </Button>
              <Button variant="outline" className="gap-2">
                <CloudCog className="h-4 w-4" />
                List Remotes
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Database className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Backup Defaults</CardTitle>
                <CardDescription>Default settings for new backup jobs</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Default Compression</Label>
                <Select defaultValue="gzip">
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue />
                  </SelectTrigger>
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
                <Select defaultValue="aes256">
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="aes128">AES-128</SelectItem>
                    <SelectItem value="aes256">AES-256</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Verify Backups</Label>
                <p className="text-sm text-muted-foreground">Automatically verify backup integrity</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Parallel Uploads</Label>
                <p className="text-sm text-muted-foreground">Enable multi-threaded uploads</p>
              </div>
              <Switch defaultChecked />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Bell className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Notification Defaults</CardTitle>
                <CardDescription>Global notification preferences</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label>Notify on Success</Label>
                <p className="text-sm text-muted-foreground">Send notifications for successful backups</p>
              </div>
              <Switch />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Notify on Warning</Label>
                <p className="text-sm text-muted-foreground">Send notifications for backups with warnings</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Notify on Failure</Label>
                <p className="text-sm text-muted-foreground">Send notifications for failed backups</p>
              </div>
              <Switch defaultChecked />
            </div>
          </CardContent>
        </Card>

        <Card className="glass-panel border-border animate-fade-in">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Clock className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg">Log Retention</CardTitle>
                <CardDescription>Configure how long to keep logs</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Backup Logs</Label>
                <Select defaultValue="30">
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue />
                  </SelectTrigger>
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
                <Select defaultValue="14">
                  <SelectTrigger className="bg-background border-border">
                    <SelectValue />
                  </SelectTrigger>
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
              <div className="h-10 w-10 rounded-lg bg-destructive/10 flex items-center justify-center">
                <Shield className="h-5 w-5 text-destructive" />
              </div>
              <div>
                <CardTitle className="text-lg text-destructive">Danger Zone</CardTitle>
                <CardDescription>Irreversible actions</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label>Reset All Settings</Label>
                <p className="text-sm text-muted-foreground">Reset all settings to default values</p>
              </div>
              <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground">
                Reset
              </Button>
            </div>
            <Separator className="bg-border" />
            <div className="flex items-center justify-between">
              <div>
                <Label>Clear All Logs</Label>
                <p className="text-sm text-muted-foreground">Permanently delete all log entries</p>
              </div>
              <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground">
                Clear Logs
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
