import { useState } from "react";
import { Plus, Calendar, Clock, Edit, Trash2, MoreVertical } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const schedules = [
  {
    id: 1,
    name: "Daily Backup",
    cron: "0 23 * * *",
    description: "Every day at 11:00 PM",
    jobs: 4,
    status: "active" as const,
    nextRun: "Today, 23:00",
  },
  {
    id: 2,
    name: "Hourly Snapshot",
    cron: "0 * * * *",
    description: "Every hour",
    jobs: 2,
    status: "active" as const,
    nextRun: "In 45 minutes",
  },
  {
    id: 3,
    name: "Weekly Full Backup",
    cron: "0 2 * * 0",
    description: "Every Sunday at 2:00 AM",
    jobs: 8,
    status: "active" as const,
    nextRun: "Sunday, 02:00",
  },
  {
    id: 4,
    name: "Monthly Archive",
    cron: "0 3 1 * *",
    description: "First day of month at 3:00 AM",
    jobs: 3,
    status: "idle" as const,
    nextRun: "Mar 1, 03:00",
  },
  {
    id: 5,
    name: "Every 6 Hours",
    cron: "0 */6 * * *",
    description: "Every 6 hours",
    jobs: 2,
    status: "active" as const,
    nextRun: "In 3 hours",
  },
];

export default function Schedules() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div>
      <PageHeader 
        title="Schedules" 
        description="Configure backup schedules using cron expressions"
        action={
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                New Schedule
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Schedule</DialogTitle>
                <DialogDescription>
                  Define a cron-based schedule for backup jobs.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label htmlFor="schedule-name">Schedule Name</Label>
                  <Input id="schedule-name" placeholder="e.g. Daily Backup" className="bg-background border-border" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cron">Cron Expression</Label>
                  <Input id="cron" placeholder="0 23 * * *" className="bg-background border-border font-mono" />
                  <p className="text-xs text-muted-foreground">
                    Format: minute hour day month weekday
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Input id="description" placeholder="e.g. Every day at 11:00 PM" className="bg-background border-border" />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={() => setDialogOpen(false)}>Create Schedule</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

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
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="bg-popover border-border">
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
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{schedule.description}</p>
              
              <div className="flex items-center justify-between pt-2 border-t border-border">
                <div className="flex items-center gap-4">
                  <div className="text-sm">
                    <span className="text-muted-foreground">Jobs: </span>
                    <span className="font-medium">{schedule.jobs}</span>
                  </div>
                  <StatusBadge status={schedule.status} />
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>Next: {schedule.nextRun}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
