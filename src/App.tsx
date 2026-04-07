import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ColorThemeProvider } from "@/contexts/ColorThemeContext";
import { AutoRefreshProvider } from "@/contexts/AutoRefreshContext";
import { MainLayout } from "@/components/layout/MainLayout";
import Login from "./pages/Login";
import Index from "./pages/Index";
import BackupJobs from "./pages/BackupJobs";
import Schedules from "./pages/Schedules";
import Notifications from "./pages/Notifications";
import Storages from "./pages/Storages";
import Rotations from "./pages/Rotations";
import Logs from "./pages/Logs";
import Restore from "./pages/Restore";
import Settings from "./pages/Settings";
import JobDetail from "./pages/JobDetail";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data stays fresh for 30 seconds — navigating between pages reuses the
      // cache rather than re-fetching on every mount. The dashboard's own
      // refetchInterval handles live updates independently of this setting.
      staleTime: 30_000,
    },
  },
});

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<Index />} />
        <Route path="/jobs" element={<BackupJobs />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/storages" element={<Storages />} />
        <Route path="/rotations" element={<Rotations />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/restore" element={<Restore />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </MainLayout>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
      <ColorThemeProvider>
        <AutoRefreshProvider>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <AuthProvider>
              <BrowserRouter>
                <AppRoutes />
              </BrowserRouter>
            </AuthProvider>
          </TooltipProvider>
        </AutoRefreshProvider>
      </ColorThemeProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
