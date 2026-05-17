import { useNavigate } from "react-router-dom";
import { Activity } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { fetchJobs } from "@/api";

export default function ActiveJobs() {
  const navigate = useNavigate();

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some((j) => j.status === "running" || j.status === "queued");
      return hasActive ? 3000 : 5000;
    },
  });

  const activeJobs = jobs.filter((j) => j.status === "running" || j.status === "queued");

  return (
    <div>
      <PageHeader
        title="Job Queue"
        description="Jobs currently running or waiting in the queue"
      />

      <Card className="glass-panel border-border animate-fade-in">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : activeJobs.length === 0 ? (
            <div className="p-8 text-center">
              <Activity className="h-8 w-8 text-muted-foreground mx-auto mb-3 opacity-40" />
              <p className="text-muted-foreground text-sm">No jobs are currently running or queued.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">Job Name</TableHead>
                  <TableHead className="text-muted-foreground">Storage</TableHead>
                  <TableHead className="text-muted-foreground">Schedule</TableHead>
                  <TableHead className="text-muted-foreground">Status</TableHead>
                  <TableHead className="text-muted-foreground">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {activeJobs.map((job) => (
                  <TableRow
                    key={job.id}
                    className="border-border hover:bg-muted/30 cursor-pointer"
                    onClick={() => navigate(`/jobs/${job.id}`)}
                  >
                    <TableCell className="font-medium">{job.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{job.storage?.name || "—"}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {job.schedule ? job.schedule.name : "Manual"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={job.status as "running" | "queued"} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {job.last_run ? new Date(job.last_run).toLocaleString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
