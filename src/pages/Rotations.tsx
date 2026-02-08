import { Plus, RotateCcw, Clock, Archive, Edit, Trash2, MoreVertical } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const rotationPolicies = [
  {
    id: 1,
    name: "Standard Daily",
    description: "Keep daily backups for 7 days",
    retention: "7 days",
    minBackups: 7,
    maxBackups: 14,
    jobs: 8,
    status: "active" as const,
    lastCleanup: "Today, 00:15",
    spaceReclaimed: "12.4 GB",
  },
  {
    id: 2,
    name: "Weekly Extended",
    description: "Keep weekly backups for 12 weeks",
    retention: "12 weeks",
    minBackups: 12,
    maxBackups: 24,
    jobs: 4,
    status: "active" as const,
    lastCleanup: "Yesterday",
    spaceReclaimed: "45.2 GB",
  },
  {
    id: 3,
    name: "Monthly Archive",
    description: "Keep monthly backups for 1 year",
    retention: "365 days",
    minBackups: 12,
    maxBackups: 24,
    jobs: 3,
    status: "active" as const,
    lastCleanup: "Feb 1, 2024",
    spaceReclaimed: "156 GB",
  },
  {
    id: 4,
    name: "Hourly Critical",
    description: "Keep hourly backups for 24 hours",
    retention: "24 hours",
    minBackups: 24,
    maxBackups: 48,
    jobs: 2,
    status: "active" as const,
    lastCleanup: "1 hour ago",
    spaceReclaimed: "2.1 GB",
  },
  {
    id: 5,
    name: "Compliance Archive",
    description: "Regulatory compliance - 7 year retention",
    retention: "7 years",
    minBackups: 84,
    maxBackups: 168,
    jobs: 1,
    status: "idle" as const,
    lastCleanup: "Never",
    spaceReclaimed: "-",
  },
];

export default function Rotations() {
  return (
    <div>
      <PageHeader 
        title="Retention Policies" 
        description="Configure backup rotation and retention rules"
        action={
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            New Policy
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                <Archive className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-semibold">215.7 GB</p>
                <p className="text-sm text-muted-foreground">Total Space Reclaimed</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-success/10 flex items-center justify-center">
                <RotateCcw className="h-6 w-6 text-success" />
              </div>
              <div>
                <p className="text-2xl font-semibold">1,247</p>
                <p className="text-sm text-muted-foreground">Backups Rotated (30d)</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="glass-panel border-border animate-fade-in">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-warning/10 flex items-center justify-center">
                <Clock className="h-6 w-6 text-warning" />
              </div>
              <div>
                <p className="text-2xl font-semibold">5</p>
                <p className="text-sm text-muted-foreground">Active Policies</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="glass-panel border-border animate-fade-in">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">Policy Name</TableHead>
                <TableHead className="text-muted-foreground">Retention</TableHead>
                <TableHead className="text-muted-foreground">Min / Max Backups</TableHead>
                <TableHead className="text-muted-foreground">Jobs</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-muted-foreground">Last Cleanup</TableHead>
                <TableHead className="text-muted-foreground">Space Reclaimed</TableHead>
                <TableHead className="text-muted-foreground text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rotationPolicies.map((policy) => (
                <TableRow key={policy.id} className="border-border hover:bg-muted/30">
                  <TableCell>
                    <div>
                      <p className="font-medium">{policy.name}</p>
                      <p className="text-xs text-muted-foreground">{policy.description}</p>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-sm">{policy.retention}</TableCell>
                  <TableCell className="text-sm">
                    {policy.minBackups} / {policy.maxBackups}
                  </TableCell>
                  <TableCell>{policy.jobs}</TableCell>
                  <TableCell><StatusBadge status={policy.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">{policy.lastCleanup}</TableCell>
                  <TableCell className="font-mono text-sm">{policy.spaceReclaimed}</TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-popover border-border">
                        <DropdownMenuItem className="gap-2 cursor-pointer">
                          <RotateCcw className="h-4 w-4" /> Run Cleanup
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
