import { cn } from "@/lib/utils";

type Status = "active" | "running" | "success" | "warning" | "error" | "idle" | "pending";

interface StatusBadgeProps {
  status: Status;
  label?: string;
  className?: string;
}

const statusConfig: Record<Status, { dot: string; bg: string; text: string; defaultLabel: string }> = {
  active: {
    dot: "bg-success",
    bg: "bg-success/10",
    text: "text-success",
    defaultLabel: "Active",
  },
  running: {
    dot: "bg-primary animate-pulse",
    bg: "bg-primary/10",
    text: "text-primary",
    defaultLabel: "Running",
  },
  success: {
    dot: "bg-success",
    bg: "bg-success/10",
    text: "text-success",
    defaultLabel: "Success",
  },
  warning: {
    dot: "bg-warning",
    bg: "bg-warning/10",
    text: "text-warning",
    defaultLabel: "Warning",
  },
  error: {
    dot: "bg-destructive",
    bg: "bg-destructive/10",
    text: "text-destructive",
    defaultLabel: "Error",
  },
  idle: {
    dot: "bg-muted-foreground",
    bg: "bg-muted",
    text: "text-muted-foreground",
    defaultLabel: "Idle",
  },
  pending: {
    dot: "bg-warning animate-pulse",
    bg: "bg-warning/10",
    text: "text-warning",
    defaultLabel: "Pending",
  },
};

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const config = statusConfig[status];
  
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
      config.bg,
      config.text,
      className
    )}>
      <span className={cn("w-1.5 h-1.5 rounded-full", config.dot)} />
      {label || config.defaultLabel}
    </span>
  );
}
