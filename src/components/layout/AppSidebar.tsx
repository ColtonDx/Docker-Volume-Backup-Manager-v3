import { 
  Database, 
  Calendar, 
  Bell, 
  HardDrive, 
  RotateCcw, 
  FileText, 
  Settings,
  Container,
  LayoutDashboard,
  LogOut,
  ArchiveRestore,
  RefreshCw
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useAutoRefresh, REFRESH_OPTIONS } from "@/contexts/AutoRefreshContext";
import { useQuery } from "@tanstack/react-query";
import { fetchSettings } from "@/api";
import { NavLink } from "@/components/NavLink";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar";

const mainNavItems = [
  { title: "Overview", url: "/", icon: LayoutDashboard },
  { title: "Backup Jobs", url: "/jobs", icon: Database },
];

const configNavItems = [
  { title: "Schedules", url: "/schedules", icon: Calendar },
  { title: "Notifications", url: "/notifications", icon: Bell },
  { title: "Storages", url: "/storages", icon: HardDrive },
  { title: "Retention", url: "/rotations", icon: RotateCcw },
];

const systemNavItems = [
  { title: "Logs", url: "/logs", icon: FileText },
  { title: "Restore", url: "/restore", icon: ArchiveRestore },
  { title: "Settings", url: "/settings", icon: Settings },
];

export function AppSidebar() {
  const { logout } = useAuth();
  const { interval, setInterval } = useAutoRefresh();
  const { data: settingsData } = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const instanceName = (settingsData?.settings as Record<string, unknown>)?.instance_name as string || "Docker Volume Backup Manager";
  
  return (
    <Sidebar>
      <SidebarHeader className="border-b border-border p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 glow-primary">
            <Container className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="font-semibold text-foreground text-sm leading-tight">{instanceName}</h1>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs uppercase tracking-wider text-muted-foreground/70">
            Overview
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink 
                      to={item.url} 
                      end={item.url === "/"}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
                      activeClassName="bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-xs uppercase tracking-wider text-muted-foreground/70">
            Configuration
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {configNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink 
                      to={item.url}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
                      activeClassName="bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-xs uppercase tracking-wider text-muted-foreground/70">
            System
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {systemNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink 
                      to={item.url}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
                      activeClassName="bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-border p-4 space-y-3">
        <div className="flex items-center gap-2">
          <RefreshCw className={`h-3.5 w-3.5 text-muted-foreground${interval ? ' animate-spin' : ''}`} style={interval ? { animationDuration: '3s' } : undefined} />
          <span className="text-xs text-muted-foreground">Auto Refresh</span>
          <div className="ml-auto flex gap-1">
            {REFRESH_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setInterval(opt.value)}
                className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${
                  interval === opt.value
                    ? 'bg-primary/15 text-primary font-semibold'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="status-dot status-dot-active" />
            <span className="text-xs text-muted-foreground">v{__APP_VERSION__}</span>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            title="Sign out"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
