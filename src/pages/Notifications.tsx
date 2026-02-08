import { Plus, Bell, Mail, MessageSquare, Webhook, Edit, Trash2, MoreVertical, TestTube } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const notifications = [
  {
    id: 1,
    name: "Email - DevOps Team",
    type: "email",
    icon: Mail,
    destination: "devops@company.com",
    events: ["failure", "warning"],
    enabled: true,
    lastTriggered: "3 hours ago",
  },
  {
    id: 2,
    name: "Slack - #alerts",
    type: "slack",
    icon: MessageSquare,
    destination: "#infrastructure-alerts",
    events: ["failure", "success"],
    enabled: true,
    lastTriggered: "1 day ago",
  },
  {
    id: 3,
    name: "Webhook - PagerDuty",
    type: "webhook",
    icon: Webhook,
    destination: "https://events.pagerduty.com/...",
    events: ["failure"],
    enabled: true,
    lastTriggered: "5 days ago",
  },
  {
    id: 4,
    name: "Email - Admin",
    type: "email",
    icon: Mail,
    destination: "admin@company.com",
    events: ["failure", "warning", "success"],
    enabled: false,
    lastTriggered: "Never",
  },
];

const eventLabels: Record<string, { label: string; color: string }> = {
  failure: { label: "Failure", color: "bg-destructive/20 text-destructive" },
  warning: { label: "Warning", color: "bg-warning/20 text-warning" },
  success: { label: "Success", color: "bg-success/20 text-success" },
};

export default function Notifications() {
  return (
    <div>
      <PageHeader 
        title="Notifications" 
        description="Configure alerts for backup events"
        action={
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Notification
          </Button>
        }
      />

      <div className="space-y-4">
        {notifications.map((notification) => (
          <Card key={notification.id} className="glass-panel border-border animate-fade-in">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                    <notification.icon className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-medium">{notification.name}</h3>
                    <p className="text-sm text-muted-foreground font-mono truncate max-w-xs">
                      {notification.destination}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2">
                    {notification.events.map((event) => (
                      <span 
                        key={event}
                        className={`px-2 py-0.5 rounded text-xs font-medium ${eventLabels[event].color}`}
                      >
                        {eventLabels[event].label}
                      </span>
                    ))}
                  </div>

                  <div className="text-sm text-muted-foreground w-28">
                    <span className="text-xs">Last: </span>
                    {notification.lastTriggered}
                  </div>

                  <div className="flex items-center gap-2">
                    <Switch checked={notification.enabled} />
                    <span className="text-sm text-muted-foreground w-16">
                      {notification.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="bg-popover border-border">
                      <DropdownMenuItem className="gap-2 cursor-pointer">
                        <TestTube className="h-4 w-4" /> Send Test
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2 cursor-pointer">
                        <Edit className="h-4 w-4" /> Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator className="bg-border" />
                      <DropdownMenuItem className="gap-2 cursor-pointer text-destructive focus:text-destructive">
                        <Trash2 className="h-4 w-4" /> Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
