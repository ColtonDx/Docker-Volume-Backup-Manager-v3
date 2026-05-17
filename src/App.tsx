import { lazy, Suspense } from "react";
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

const Index = lazy(() => import("./pages/Index"));
const BackupJobs = lazy(() => import("./pages/BackupJobs"));
const Schedules = lazy(() => import("./pages/Schedules"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Storages = lazy(() => import("./pages/Storages"));
const Rotations = lazy(() => import("./pages/Rotations"));
const Logs = lazy(() => import("./pages/Logs"));
const Restore = lazy(() => import("./pages/Restore"));
const Settings = lazy(() => import("./pages/Settings"));
const JobDetail = lazy(() => import("./pages/JobDetail"));
const NotFound = lazy(() => import("./pages/NotFound"));

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
      <Suspense fallback={null}>
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
      </Suspense>
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
